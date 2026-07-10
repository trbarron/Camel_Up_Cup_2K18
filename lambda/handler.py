"""
handler.py — Camel Up Cup tournament Lambda.

Invoked async by tylerbarron.com when a bot is submitted. Validates the
submission (AST allowlist + smoke test), then runs a full tournament of
CAMEL_TOTAL_GAMES games across the whole roster (built-in bots + previously
accepted uploads + the new bot). A full run takes ~1h of CPU, far beyond one
Lambda invocation, so the handler runs games until ~2 minutes before its own
timeout, then re-invokes itself to continue.

Accumulated stats (agg + per-game log) are checkpointed to S3 each round, not
carried in the self-invoke payload — a 2000-game glog plus the bot source can
exceed Lambda's 256 KB async-payload limit, which silently drops the
continuation. The self-invoke therefore carries only {"id", "resume": true};
the successor rehydrates from the checkpoint. Because state survives in S3, a
lost continuation is recoverable by re-invoking with the same resume payload.

Payloads:
  submission:   {"id", "botName", "author", "code", "className"?}
  continuation: {"id", "resume": true}    (self-invoke only; state in S3)
  reseed:       {"op": "rerun", "id"?}     rebuild leaderboard, no new bot

Results are published to S3 (see storage.py): a public leaderboard.json and
per-submission status.json the site polls. The submitted code itself never
receives secrets: this function's env has none, and its IAM role only allows
the camel-up S3 prefixes plus re-invoking itself.
"""

import json
import multiprocessing as mp
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sandbox import BotValidationError, TimedBot, load_bot_class, validate_bot_source
from storage import Storage
from tournament_core import BOT_INFO, BOT_REGISTRY, init_stats, run_game

TOTAL_GAMES = int(os.environ.get("CAMEL_TOTAL_GAMES", "500"))
SMOKE_GAMES = int(os.environ.get("CAMEL_SMOKE_GAMES", "3"))
MOVE_LIMIT_S = float(os.environ.get("CAMEL_MOVE_LIMIT_S", "5"))
MOVE_LIMIT_MS = MOVE_LIMIT_S * 1000
# Stop starting new rounds when this close to the invocation timeout; a round
# runs ~60-90s, so 2.5 min leaves ample room to finish one and checkpoint.
SAFETY_MS = 150_000

# Games run in parallel worker processes — Lambda vCPUs scale with memory
# (~1 vCPU per 1769 MB), and one game is single-threaded, so parallelism is
# the only way memory buys speed. Lambda supports mp.Process+Pipe but NOT
# mp.Pool/Queue (no /dev/shm).
WORKERS = int(os.environ.get("CAMEL_WORKERS", "0")) or (os.cpu_count() or 1)
# A round is WORKERS * this many games, and the SAFETY_MS check only fires
# *between* rounds — so the whole round must fit inside that buffer. Kept small
# (2 -> 8 games/round at 4 workers) so even a pathologically slow but non-DQ'd
# bot (moves just under MOVE_LIMIT_S) can't make one round blow past the hard
# timeout, which loses the round's work and triggers an async retry.
GAMES_PER_WORKER_ROUND = int(os.environ.get("CAMEL_GAMES_PER_WORKER_ROUND", "2"))

# Tournament house roster — explicit, so the experimental lab registry
# (tournament_core imports every test bot) never leaks into the Cup.
# 2026-07-04: Player0/1/2 removed from play (filler matchups redistribute
# win% by seating luck — the noise the win%-ranking exists to avoid), but
# still serve as the submission smoke-test opponents.
HOUSE_ROSTER = [
    "tb-HandcodedHenry",
    "tb-ClaudeCamel",
    "tb-GeminiGerry",
    "tb-OpusOmul",
    "tb-FabelFelix",
]

# Baselines the smoke test seats a submission against.
SMOKE_OPPONENTS = ["tb-Player0", "tb-Player1", "tb-Player2"]

# Names a submission may not take, and that _load_roster skips if an upload
# duplicates one. Only the bots the Cup actually uses — NOT set(BOT_REGISTRY):
# tournament_core imports the entire local experimental lab (~20 dev bots), and
# reserving those wrongly rejects legitimate submissions AND drops an already
# accepted upload whose name later collides with a lab bot (e.g. tb-PortfolioPam).
RESERVED_NAMES = set(HOUSE_ROSTER) | set(SMOKE_OPPONENTS)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty_agg():
    return {"wins": 0.0, "games": 0, "coins": 0, "moves": 0,
            "timeSum": 0.0, "timeMax": 0.0, "actions": {}}


def _merge_stats_into_agg(stats, agg):
    for name, s in stats.items():
        a = agg.setdefault(name, _empty_agg())
        a["wins"] += s["wins"]
        a["games"] += s["games"]
        a["coins"] += s["coins_total"]
        a["moves"] += len(s["times_ms"])
        a["timeSum"] += sum(s["times_ms"])
        a["timeMax"] = max(a["timeMax"], max(s["times_ms"], default=0.0))
        for k, v in s["actions"].items():
            a["actions"][k] = a["actions"].get(k, 0) + v


def _fit_elo(glog):
    """Bradley-Terry ratings from the per-game log, on the Elo scale.

    Winner-take-all, matching the game's objective: each game yields only
    winner-vs-loser pairwise results (the winner beats each of the other
    three; a tie for first splits the point between the tied winners).
    Non-winners exchange nothing among themselves — second place earns
    zero. Batch maximum-likelihood via the standard MM iteration —
    order-independent and K-free, unlike sequential Elo. A virtual
    half-win/half-loss against a fixed 1500-anchor regularizes
    undefeated/winless bots. Returns {name: elo}.
    """
    wins = {}     # wins[a][b] = pairwise score of a over b
    def add(a, b, s):
        wins.setdefault(a, {})[b] = wins.get(a, {}).get(b, 0.0) + s

    players = set()
    for game in glog:
        players.update(n for n, _c in game)
        best = max(c for _n, c in game)
        winners = [n for n, c in game if c == best]
        losers = [n for n, c in game if c < best]
        for i, a in enumerate(winners):
            for b in winners[i + 1:]:       # tie for first: split the point
                add(a, b, 0.5), add(b, a, 0.5)
            for b in losers:
                add(a, b, 1.0), add(b, a, 0.0)
    if not players:
        return {}

    ANCHOR = "__anchor__"
    for p in players:
        add(p, ANCHOR, 0.5), add(ANCHOR, p, 0.5)
    ps = {p: 1.0 for p in players}
    ps[ANCHOR] = 1.0
    for _ in range(100):
        new = {}
        for p in ps:
            if p == ANCHOR:
                new[p] = 1.0   # fixed reference point = Elo 1500
                continue
            w_tot = sum(wins.get(p, {}).values())
            denom = sum(
                (wins.get(p, {}).get(q, 0.0) + wins.get(q, {}).get(p, 0.0))
                / (ps[p] + ps[q])
                for q in ps if q != p
            )
            new[p] = (w_tot / denom) if denom > 0 else 1.0
        ps = new

    import math
    return {p: round(1500 + 400 * math.log10(ps[p]), 1) for p in players}


def _build_leaderboard(agg, total_games, authors, submission=None, glog=None,
                       submitted=None):
    elo = _fit_elo(glog or [])
    bots = []
    for name, a in agg.items():
        games, moves = a["games"], a["moves"]
        actions_pct = {
            k: round(100 * v / moves, 1) for k, v in sorted(a["actions"].items())
        } if moves else {}
        info = BOT_INFO.get(name, {})
        bots.append({
            "name": name,
            "author": info.get("author") or authors.get(name),
            "model": info.get("model"),
            "note": info.get("note"),
            "year": info.get("year"),
            "builtin": name in RESERVED_NAMES,
            "elo": elo.get(name),
            "submitted": (submitted or {}).get(name),
            "wins": round(a["wins"], 2),
            "games": games,
            "winPct": round(100 * a["wins"] / games, 1) if games else 0.0,
            "avgCoins": round(a["coins"] / games, 1) if games else 0.0,
            "avgMoveMs": round(a["timeSum"] / moves, 1) if moves else 0.0,
            "maxMoveMs": round(a["timeMax"], 1),
            "actions": actions_pct,
        })
    bots.sort(key=lambda b: b["wins"], reverse=True)
    board = {"updated": _now(), "totalGames": total_games, "bots": bots}
    if submission:
        board["lastSubmission"] = submission
    return board


def _load_roster(storage):
    """
    Returns (bots, names, authors, submitted, timed_wrappers). Built-ins run
    unwrapped; every bot that arrived as an upload runs behind a per-move
    timer. `submitted` maps upload names to their accepted timestamp.
    """
    bots, names, authors, submitted, wrappers = [], [], {}, {}, {}
    for name in HOUSE_ROSTER:
        bots.append(BOT_REGISTRY[name])
        names.append(name)
    for name, code, meta in storage.load_accepted_bots():
        if name in RESERVED_NAMES:
            continue
        try:
            class_name = meta.get("className") or validate_bot_source(code)
            wrapped = TimedBot(load_bot_class(code, class_name), MOVE_LIMIT_S)
        except BotValidationError:
            continue  # a bad historical bot shouldn't sink new submissions
        bots.append(wrapped)
        names.append(name)
        authors[name] = meta.get("author")
        submitted[name] = meta.get("accepted")
        wrappers[name] = wrapped
    return bots, names, authors, submitted, wrappers


def _smoke_test(bot, name):
    """A few games against the baseline bots; DQ on any move over the limit."""
    baseline_names = SMOKE_OPPONENTS
    baseline = [BOT_REGISTRY[n] for n in baseline_names]
    names = [name, *baseline_names]
    stats = init_stats(names)
    seat_stats = {i: {"wins": 0.0, "games": 0, "coins_total": 0} for i in range(4)}
    for _ in range(SMOKE_GAMES):
        run_game([bot] + baseline, names, stats, seat_stats)
        if bot.timeouts or max(stats[name]["times_ms"], default=0) > MOVE_LIMIT_MS:
            raise BotValidationError(
                f"a move exceeded the {MOVE_LIMIT_S:g}s time limit during the smoke test"
            )
    moves = stats[name]["times_ms"]
    if not moves:
        raise BotValidationError("bot never got to move during the smoke test")


def _plain_stats(stats):
    """init_stats structure → picklable plain dicts (drops the profile slot)."""
    return {
        name: {
            "wins": s["wins"], "games": s["games"], "coins_total": s["coins_total"],
            "times_ms": s["times_ms"], "actions": dict(s["actions"]),
        }
        for name, s in stats.items()
    }


def _play_games(bots, names, n_games):
    stats = init_stats(names)
    seat_stats = {i: {"wins": 0.0, "games": 0, "coins_total": 0} for i in range(4)}
    glog = []
    for _ in range(n_games):
        run_game(bots, names, stats, seat_stats, game_log=glog)
    return stats, glog


def _worker_play(conn, bots, names, n_games, new_bot):
    """Child process: play n_games, ship stats + the new bot's timeout count back."""
    import random
    random.seed()  # fork copies the parent RNG state; without this every worker replays identical games
    try:
        stats, glog = _play_games(bots, names, n_games)
        conn.send({
            "stats": _plain_stats(stats),
            "glog": glog,
            "newBotTimeouts": new_bot.timeouts if new_bot else 0,
        })
    except Exception as e:  # noqa: BLE001 — surfaced as a round failure in the parent
        conn.send({"error": f"{type(e).__name__}: {e}"})
    finally:
        conn.close()


def _play_round(bots, names, n_games, new_bot):
    """
    Play one round of games, forking WORKERS processes when the platform
    allows (bots are exec'd classes, unpicklable — fork inheritance is the
    only way to hand them to workers). Returns a list of plain stats dicts.
    """
    can_fork = WORKERS > 1 and "fork" in mp.get_all_start_methods()
    if not can_fork:
        stats, glog = _play_games(bots, names, n_games)
        return [{
            "stats": _plain_stats(stats),
            "glog": glog,
            "newBotTimeouts": new_bot.timeouts if new_bot else 0,
        }]

    ctx = mp.get_context("fork")
    base, extra = divmod(n_games, WORKERS)
    procs = []
    for i in range(WORKERS):
        share = base + (1 if i < extra else 0)
        if share == 0:
            continue
        parent_conn, child_conn = ctx.Pipe(duplex=False)
        p = ctx.Process(target=_worker_play, args=(child_conn, bots, names, share, new_bot))
        p.start()
        child_conn.close()
        procs.append((p, parent_conn))

    results = []
    for p, conn in procs:
        try:
            results.append(conn.recv())
        except EOFError:
            results.append({"error": "worker exited without reporting (crash/OOM)"})
        finally:
            p.join()

    for r in results:
        if "error" in r:
            raise RuntimeError(f"tournament worker failed: {r['error']}")
    return results


def _self_invoke(context, payload):
    import boto3
    boto3.client("lambda").invoke(
        FunctionName=context.invoked_function_arn,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )


def handler(event, context):
    storage = Storage()

    # A self-invoke carries only {"id", "resume"}; the accumulated state lives
    # in the S3 checkpoint. Rehydrate it and proceed as if it were the payload.
    is_resume = bool(event.get("resume"))
    if is_resume:
        data = storage.read_checkpoint(event["id"])
        if data is None:
            raise RuntimeError(f"resume for {event['id']} but no checkpoint found")
        if data.get("done"):
            return {"status": "complete"}  # a late/duplicate continuation
    else:
        data = event

    submission_id = data.get("id") or "rerun"
    is_rerun = data.get("op") == "rerun"
    bot_name = None if is_rerun else data["botName"]
    author = data.get("author")
    games_done = int(data.get("gamesDone", 0))
    agg = data.get("agg") or {}
    glog = data.get("glog") or []
    code = data.get("code")
    class_name = data.get("className")

    def write_checkpoint():
        ckpt = {"id": submission_id, "gamesDone": games_done,
                "agg": agg, "glog": glog, "updated": _now()}
        if is_rerun:
            ckpt["op"] = "rerun"
        else:
            ckpt.update({"botName": bot_name, "author": author,
                         "code": code, "className": class_name})
        storage.write_checkpoint(submission_id, ckpt)

    def status(phase, **extra):
        storage.write_status(submission_id, {
            "id": submission_id, "phase": phase, "botName": bot_name,
            "gamesDone": games_done, "totalGames": TOTAL_GAMES,
            "updated": _now(), **extra,
        })

    try:
        bots, names, authors, submitted, _wrappers = _load_roster(storage)

        new_bot = None
        if not is_rerun:
            first_pass = not is_resume  # a fresh submission validates once, up front
            if first_pass:
                status("validating")
                if bot_name in RESERVED_NAMES or bot_name in names:
                    raise BotValidationError(f"a bot named '{bot_name}' already exists")
                class_name = validate_bot_source(code, class_name)
            new_bot = TimedBot(load_bot_class(code, class_name), MOVE_LIMIT_S)
            if first_pass:
                _smoke_test(new_bot, bot_name)
            bots.append(new_bot)
            names.append(bot_name)
            authors[bot_name] = author

        status("running")

        while games_done < TOTAL_GAMES and context.get_remaining_time_in_millis() > SAFETY_MS:
            round_games = min(WORKERS * GAMES_PER_WORKER_ROUND, TOTAL_GAMES - games_done)
            results = _play_round(bots, names, round_games, new_bot)
            games_done += round_games
            for r in results:
                _merge_stats_into_agg(r["stats"], agg)
                glog.extend(r.get("glog") or [])
            if new_bot:
                worst_ms = max(
                    (max(r["stats"].get(bot_name, {}).get("times_ms") or [0])
                     for r in results),
                    default=0,
                )
                if any(r["newBotTimeouts"] for r in results) or worst_ms > MOVE_LIMIT_MS:
                    raise BotValidationError(
                        f"disqualified: a move exceeded the {MOVE_LIMIT_S:g}s limit "
                        f"(around game {games_done})"
                    )
            write_checkpoint()  # persist progress so a dropped self-invoke is recoverable
            status("running")

        if games_done < TOTAL_GAMES:
            continuation = {"id": submission_id, "resume": True}
            if os.environ.get("CAMEL_LOCAL_DIR"):
                return {"continue": continuation}
            _self_invoke(context, continuation)
            status("running")
            return {"status": "continuing", "gamesDone": games_done}

        # Persist author names of previously accepted bots into the board too.
        submission = None
        if not is_rerun:
            accepted_at = _now()
            storage.save_accepted_bot(bot_name, code, {
                "author": author, "className": class_name,
                "submissionId": submission_id, "accepted": accepted_at,
            })
            submitted[bot_name] = accepted_at
            submission = {"id": submission_id, "botName": bot_name, "author": author}

        board = _build_leaderboard(agg, TOTAL_GAMES, authors, submission, glog,
                                   submitted)
        storage.write_leaderboard(board)
        # Collapse the checkpoint to a tiny marker: reclaims the large glog and
        # makes any late/duplicate resume a no-op (see the resume guard above).
        storage.write_checkpoint(submission_id, {"id": submission_id, "done": True})

        rank = next(
            (i + 1 for i, b in enumerate(board["bots"]) if b["name"] == bot_name), None
        )
        status("complete", rank=rank)
        return {"status": "complete", "rank": rank}

    except BotValidationError as e:
        status("rejected", reason=str(e))
        return {"status": "rejected", "reason": str(e)}
    except Exception as e:  # noqa: BLE001 — surface anything else to the poller
        status("error", reason=f"{type(e).__name__}: {e}")
        raise
