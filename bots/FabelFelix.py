# ---
# name: tb-FabelFelix
# author: Tyler Barron
# model: Claude Fable 5
# year: 2026
# ---
"""FabelFelix (fka FableCamel) — exact-EV Camel Up bot.

Per turn:
  1. Exactly enumerate every way the current round can finish (every die
     order and value for the camels still to move, including trap
     deflections) to get the joint distribution of (round winner,
     runner-up, game-ends-now) plus expected trap coins per player.
  2. Monte-Carlo the remainder of the game for game-winner odds and pace.
  3. Price every available action — roll, each round bet, each game bet,
     each legal trap placement — using the engine's actual settlement
     rules (payout ladders indexed by bet order), then pick the best after
     a risk adjustment based on our coin lead and how close the game is to
     ending.

The move simulator is a faithful port of camelup.MoveCamel (a -1 trap
moves the hit camel and its riders under the stack one square back), so
enumerated probabilities match the engine exactly.
"""

import hashlib
import math
import random
import time

from playerinterface import PlayerInterface

FINISH = 16
KEYLEN = 21          # highest track index reachable mid-round is 19
TRACKLEN = 25        # working track length for simulations
DICE = (1, 2, 3)

ROUND_FIRST_PAY = (5, 3, 2, 0)
ROUND_SECOND_PAY = (1, 1, 1, 0)
GAME_PAY = (8, 5, 3, 1)

_rng = random.Random(0xCA3E1)


def _check_bet(hashed_bet, user_bet):
    bet, salt = hashed_bet.split(':')
    return bet == hashlib.sha256(salt.encode() + user_bet.encode()).hexdigest()


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def _top_two(track):
    """First and second place camels (engine's FindCamelInNthPlace order)."""
    first = None
    for p in range(len(track) - 1, -1, -1):
        st = track[p]
        for i in range(len(st) - 1, -1, -1):
            if first is None:
                first = st[i]
            else:
                return first, st[i]
    return first, None


def _fifth(track):
    for p in range(len(track)):
        if track[p]:
            return track[p][0]
    return 0


def _enum_apply(tk, camel, dist, traps):
    """Apply one camel move to a tuple-of-tuples track. Returns
    (new_track, trap_owner_or_None, raw_landing_spot, final_spot).
    Mirrors camelup.MoveCamel exactly: the hit camel and its riders move
    together; a -1 trap puts them under the destination stack."""
    curr = y = 0
    for p, st in enumerate(tk):
        if camel in st:
            curr = p
            y = st.index(camel)
            break
    raw = curr + dist
    fb = False
    owner = None
    tt = traps.get(raw)
    if tt is not None:
        owner = tt[1]
        if tt[0] == -1:
            fb = True
        dist += tt[0]
    tgt = curr + dist
    lst = list(tk)
    src = lst[curr]
    moving = src[y:]
    if tgt == curr:
        lst[curr] = moving + src[:y]  # -1 trap bounce onto the same square
    elif fb:
        lst[curr] = src[:y]
        lst[tgt] = moving + lst[tgt]
    else:
        lst[curr] = src[:y]
        lst[tgt] = lst[tgt] + moving
    return tuple(lst), owner, raw, tgt


def _enum_round(track, remaining, traps, want_landing):
    """Exact distribution over round outcomes.
    Returns (fs, coins, landing):
      fs      : {(first, second, game_ended): probability}
      coins   : [4] expected trap coins per player this round
      landing : [spot] expected raw landings (trap-hit chances), or None
    """
    key0 = tuple(tuple(track[p]) for p in range(KEYLEN))
    layer = {(key0, frozenset(remaining)): [1.0, [0.0, 0.0, 0.0, 0.0]]}
    fs = {}
    coins = [0.0, 0.0, 0.0, 0.0]
    landing = [0.0] * TRACKLEN if want_landing else None

    while layer:
        nxt = {}
        for (tk, rem), (prob, cex) in layer.items():
            if not rem:
                f, s = _top_two(tk)
                key = (f, s, False)
                fs[key] = fs.get(key, 0.0) + prob
                for i in range(4):
                    coins[i] += cex[i]
                continue
            share = 1.0 / (len(rem) * 3)
            for camel in rem:
                for dist in DICE:
                    p = prob * share
                    ntk, owner, raw, tgt = _enum_apply(tk, camel, dist, traps)
                    if want_landing:
                        landing[raw] += p
                    ce = [cex[0] * share, cex[1] * share,
                          cex[2] * share, cex[3] * share]
                    if owner is not None:
                        ce[owner] += p
                    if tgt >= FINISH:
                        f, s = _top_two(ntk)
                        key = (f, s, True)
                        fs[key] = fs.get(key, 0.0) + p
                        for i in range(4):
                            coins[i] += ce[i]
                    else:
                        nk = (ntk, rem.difference((camel,)))
                        cur = nxt.get(nk)
                        if cur is None:
                            nxt[nk] = [p, ce]
                        else:
                            cur[0] += p
                            cc = cur[1]
                            cc[0] += ce[0]
                            cc[1] += ce[1]
                            cc[2] += ce[2]
                            cc[3] += ce[3]
        layer = nxt
    return fs, coins, landing


def _mc_game(track, remaining, traps, budget):
    """Monte-Carlo the rest of the game. Current-round traps apply, then
    traps clear each round (engine behaviour). Returns
    (win_prob[5], lose_prob[5], avg_dice_until_game_end)."""
    base = [tuple(track[p]) if p < len(track) else () for p in range(TRACKLEN)]
    win = [0] * 5
    lose = [0] * 5
    moves_tot = 0
    sims = 0
    deadline = time.perf_counter() + budget
    rng = _rng
    trap0 = traps if traps else None

    while True:
        t = [list(x) for x in base]
        pos = {}
        for p2, st in enumerate(t):
            for cml in st:
                pos[cml] = p2
        rem = list(remaining)
        trp = trap0
        moves = 0
        while True:
            if not rem:
                rem = [0, 1, 2, 3, 4]
                trp = None
            camel = rem.pop(rng.randrange(len(rem)))
            curr = pos[camel]
            dist = rng.randint(1, 3)
            fb = False
            if trp is not None:
                tt = trp.get(curr + dist)
                if tt is not None:
                    if tt[0] == -1:
                        fb = True
                    dist += tt[0]
            tgt = curr + dist
            src = t[curr]
            y = src.index(camel)
            moved = src[y:]
            del src[y:]
            if fb:
                t[tgt][:0] = moved
            else:
                t[tgt].extend(moved)
            if tgt != curr:
                for m in moved:
                    pos[m] = tgt
            moves += 1
            if tgt >= FINISH:
                break
        f, _s = _top_two(t)
        win[f] += 1
        lose[_fifth(t)] += 1
        moves_tot += moves
        sims += 1
        if sims >= 3000 or (sims >= 250 and time.perf_counter() > deadline):
            break
    return ([w / sims for w in win],
            [l / sims for l in lose],
            moves_tot / sims)


def _settle_round(fs, rbets):
    """Expected round-bet settlement per player for the existing bet list."""
    val = [0.0, 0.0, 0.0, 0.0]
    for (f, s, _e), p in fs.items():
        fi = si = 0
        for camel, owner in rbets:
            if camel == f:
                pay = ROUND_FIRST_PAY[fi] if fi < 4 else 0
                fi += 1
            elif camel == s:
                pay = ROUND_SECOND_PAY[si] if si < 4 else 0
                si += 1
            else:
                pay = -1
            val[owner] += p * pay
    return val


def _round_bet_ev(fs, rbets, c):
    """EV/variance of appending a round bet on camel c right now. Existing
    bets on the same camel settle ahead of ours in the payout ladder."""
    prior_c = sum(1 for cam, _o in rbets if cam == c)
    ev = 0.0
    e2 = 0.0
    for (f, s, _e), p in fs.items():
        if c == f:
            pay = ROUND_FIRST_PAY[prior_c] if prior_c < 4 else 0
        elif c == s:
            pay = ROUND_SECOND_PAY[prior_c] if prior_c < 4 else 0
        else:
            pay = -1
        ev += p * pay
        e2 += p * pay * pay
    return ev, e2 - ev * ev


def _two_point(p_hit, pay):
    ev = p_hit * pay - (1.0 - p_hit)
    e2 = p_hit * pay * pay + (1.0 - p_hit)
    return ev, e2 - ev * ev


def _my_game_bets(g, me):
    """Decode which camels *we* already hold game bets on (own hashes only,
    per the fair-play rules)."""
    mine = set()
    for hb in g.player_game_bets[me]:
        for c in range(5):
            if _check_bet(hb, str(c)):
                mine.add(c)
                break
    return mine


def _position_value(fs, coins, rbets, me, my_bets, cont, money, lead):
    """Scalar value of a round-outcome distribution from our seat: our round
    bets + our trap coins + our game bets' win odds, minus a threat-weighted
    share of the same for opponents, plus a pace preference (leaders want
    the game over, trailers want it to continue)."""
    settle = _settle_round(fs, rbets)
    p_end = 0.0
    for (_f, _s, e), p in fs.items():
        if e:
            p_end += p
    val = settle[me] + coins[me]
    for c in my_bets:
        p_ew = 0.0
        for (f, _s, e), p in fs.items():
            if e and f == c:
                p_ew += p
        p_win = p_ew + (1.0 - p_end) * cont.get(c, 0.0)
        val += p_win * 6.0          # ~payout+1 swing per unit of win prob
    opp_max = max(money[o] for o in range(4) if o != me)
    for o in range(4):
        if o == me:
            continue
        w = 0.35 if money[o] == opp_max else 0.18
        val -= w * (settle[o] + coins[o])
    val += _clamp(lead * 0.15, -0.8, 0.8) * p_end
    return val


def _trap_actions(track, traps, remaining, landing, fs, coins, rbets,
                  me, my_bets, cont, money, lead, t_start):
    """Evaluate trap placements/moves as (value_delta, action) pairs."""
    others = {p: t for p, t in traps.items() if t[1] != me}

    def legal(p):
        if p < 1 or p > 18:
            return False
        if track[p]:                      # not on camels (house rule)
            return False
        if p in others or (p - 1) in others or (p + 1) in others:
            return False
        return True

    spots = sorted(
        (p for p in range(1, 19) if landing[p] > 0.04 and legal(p)),
        key=lambda p: -landing[p],
    )
    spots = spots[: (4 if len(remaining) >= 4 else 6)]
    if not spots:
        return []

    base_val = _position_value(fs, coins, rbets, me, my_bets, cont, money, lead)
    out = []
    for p in spots:
        for ttype in (1, -1):
            if time.perf_counter() - t_start > 3.3:
                return out
            tc = dict(others)
            tc[p] = (ttype, me)
            fs_c, coins_c, _ = _enum_round(track, remaining, tc, False)
            v = _position_value(fs_c, coins_c, rbets, me, my_bets, cont,
                                money, lead)
            out.append((v - base_val, [1, ttype, p]))
    return out


def _decide(me, g):
    t_start = time.perf_counter()
    track = g.camel_track
    traps = {p: (r[0], r[1]) for p, r in enumerate(g.trap_track) if r}
    remaining = [c for c in range(5) if g.camel_yet_to_move[c]]
    money = g.player_money_values
    rbets = [(b[0], b[1]) for b in g.round_bets]

    fs, coins, landing = _enum_round(track, remaining, traps, True)
    p_end = sum(p for (_f, _s, e), p in fs.items() if e)

    win_p, lose_p, dice_left = _mc_game(track, remaining, traps, 0.9)

    # Risk posture: trail late -> chase variance; lead late -> lock it in.
    lead = money[me] - max(money[o] for o in range(4) if o != me)
    urgency = min(1.0, p_end + 3.0 / max(dice_left, 1.0))
    if lead < 0:
        lam = min(1.5, -lead / 6.0) * urgency
    elif lead > 2:
        lam = -0.3 * urgency
    else:
        lam = 0.0

    cands = [(1.0, [0])]  # rolling always banks exactly one coin

    for c in range(5):
        ev, var = _round_bet_ev(fs, rbets, c)
        cands.append((ev + lam * math.sqrt(max(var, 0.0)), [2, c]))

    my_bets = _my_game_bets(g, me)
    n_w = sum(1 for b in g.game_winner_bets if b[1] != me)
    n_l = sum(1 for b in g.game_loser_bets if b[1] != me)
    sw = sum(x * x for x in win_p) or 1.0
    sl = sum(x * x for x in lose_p) or 1.0
    for c in range(5):
        if c in my_bets:
            continue
        idx_w = min(3, int(n_w * win_p[c] * win_p[c] / sw + 0.5))
        ev, var = _two_point(win_p[c], GAME_PAY[idx_w])
        cands.append((ev + lam * math.sqrt(max(var, 0.0)), [3, c]))

        idx_l = min(3, int(n_l * lose_p[c] * lose_p[c] / sl + 0.5))
        ev, var = _two_point(lose_p[c], GAME_PAY[idx_l])
        cands.append((ev + lam * math.sqrt(max(var, 0.0)), [4, c]))

    # Continuation win odds per camel given the game survives this round;
    # used to translate round-outcome shifts into game-bet value.
    cont = {}
    if p_end < 0.999:
        for c in my_bets:
            p_ew = sum(p for (f, _s, e), p in fs.items() if e and f == c)
            cont[c] = max(0.0, (win_p[c] - p_ew) / (1.0 - p_end))

    for dv, act in _trap_actions(track, traps, remaining, landing, fs, coins,
                                 rbets, me, my_bets, cont, money, lead,
                                 t_start):
        cands.append((dv + lam * 0.4, act))

    cands.sort(key=lambda x: -x[0])
    return cands[0][1]


class FabelFelix(PlayerInterface):
    def move(player, g):
        try:
            return _decide(player, g)
        except Exception:
            return [0]
