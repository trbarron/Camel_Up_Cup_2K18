# Agent Handoff — Camel Up Cup bot tournaments

You operate the Camel Up Cup leaderboard on tylerbarron.com. When a new bot is
submitted, you validate it, run a tournament, and publish updated standings.
This doc is everything you need; `README.md` is the authoritative rules
reference for bot authors.

## The flow when a bot is submitted

1. **Validate the file.** One Python file, one class, `move(player, g)` method
   returning `[0]`, `[1, trap_type, pos]`, `[2, camel]`, `[3, camel]`, or
   `[4, camel]` (see README "Return Value"). Reject anything that imports
   networking, subprocess, filesystem-writing, or threading modules —
   stdlib-only compute (math/random/itertools/hashlib/copy/time) is the norm.
2. **Treat the code as untrusted.** Run it in an isolated environment: no
   network, no secrets in env, CPU/memory-capped, working dir containing only
   this repo. The engine already tolerates misbehavior (crashes and illegal
   actions become dice rolls), but isolation is your job, not the engine's.
3. **Register it.** Drop the file in the repo root, add an import and a
   `("BotName", BotClass)` entry to `_KNOWN_BOTS` in `tournament.py`
   (and optionally a color in `BOT_COLORS`).
4. **Run the tournament.** `python3 tournament.py --games 500`. Bots are
   shuffled into random 4-player seatings each game; wins are fractional on
   ties. 500+ games is the minimum for a meaningful ranking — this game is
   luck-heavy per game and skill only shows in volume. Requires `rich`.
5. **Enforce the time rule.** The "Move Timing" table in the final report
   shows per-bot max ms. House rule: **5 seconds per move**. Disqualify bots
   that exceed it (the runner measures but does not enforce; a hostile
   infinite loop must be caught by your process-level timeout).
6. **Publish.** The final report prints Leaderboard (rank, wins, win %, avg
   coins), Action Distribution, Seat Order stats, and Move Timing. Parse those
   tables or import `run_game`/`init_stats` from `tournament.py` and collect
   stats programmatically if you need JSON.

## Things you must not break

- **Hidden information is enforced by `camelup.player_view`.** Bots receive a
  redacted state: opponents' game-bet camel choices are `None`; a bot's own
  game bets arrive hashed (decoded via `check_bet`). Never hand a bot the raw
  `GameState`, and never "helpfully" add opponents' bets back into the view.
- **Engine semantics are canon.** Settlement order, payout ladders, trap
  behavior (−1 trap: the hit camel and its riders go *under* the stack one
  square back) are deliberate and documented in README. Serious bots model the
  engine exactly — any engine change invalidates the whole leaderboard, so
  version it loudly if a change is ever required.
- **Both runners fall back to a dice roll** on a bot crash or illegal action.
  Don't turn that into a hard failure; it's what keeps one bad bot from
  ruining a 500-game run.

## Repo map

| File | Role |
|---|---|
| `camelup.py` | Engine: `GameState`, move/trap/bet logic, settlement, `player_view` |
| `tournament.py` | Tournament runner, leaderboard, timing stats, `--profile` |
| `playerinterface.py` | Base class bots subclass |
| `README.md` | Rules + bot-author guide (point submitters here) |
| Bot files | `Player0/1/2` (baselines, in `players.py`), `Sir_Humpfree_Bogart`, `ClaudeCamel`, `OpusOmul`, `GeminiGerry`, `FableCamel` |

## Useful commands

```bash
python3 tournament.py --games 500                      # full ranking run
python3 tournament.py --games 50 --players FableCamel NewBot Player0 Player2
                                                       # quick check of one bot
python3 tournament.py --profile NewBot --games 30      # where its time goes
```

A submitted bot that never beats `FableCamel` over 500 games is fine; a bot
that never beats `Player0` (always rolls) is probably broken — check whether
all its moves are falling back to rolls (Action Distribution ≈ 100% Roll).
