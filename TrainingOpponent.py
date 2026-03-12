"""
TrainingOpponent — a speed-optimised variant of OpusOmul for NEAT training.

Full OpusOmul logic, two knobs turned down:

  1. Round-bet probabilities: exact enumeration when ≤3 camels remain
     (≤162 outcomes), MC sampling (N_ROUND_SAMPLES) when 4-5 remain.
     Full enumeration with 5 camels = 29,160 iterations; sampling caps at 500.

  2. Game-level MC: N_SIM = 100 (OpusOmul uses 800).

Still makes intelligent round bets, game winner/loser bets, and trap
placements — just with less precision. Intended to be ~5-8× faster than
OpusOmul while providing enough competitive signal for NEAT training.
"""

from playerinterface import PlayerInterface


class TrainingOpponent(PlayerInterface):
    def move(player, g):
        import random, hashlib, math
        from itertools import permutations

        FINISH           = 16
        N_CAMELS         = 5
        N_ROUND_SAMPLES  = 100   # MC samples for round bets when 4-5 camels remain
        N_SIM            = 10    # game-level MC runs (OpusOmul: 800)
        _MAX_DEPTH       = 60

        # ── helpers (identical to OpusOmul) ──────────────────────────────────

        def find_pos(track, cid):
            for si, stack in enumerate(track):
                try:
                    return si, stack.index(cid)
                except ValueError:
                    pass
            return None, None

        def nth_place(track, n):
            counted = 0
            for si in range(len(track) - 1, -1, -1):
                s = track[si]
                if counted + len(s) >= n:
                    return s[len(s) - (n - counted)]
                counted += len(s)
            return None

        def sim_move(track, cid, dist, traps):
            pos, yi = find_pos(track, cid)
            if pos is None or pos >= FINISH:
                return
            new_pos = min(pos + dist, FINISH)
            under = False
            if new_pos < len(traps) and len(traps[new_pos]) > 0:
                if traps[new_pos][0] == -1:
                    under = True
                new_pos += traps[new_pos][0]
            movers = track[pos][yi:]
            track[pos] = track[pos][:yi]
            if under:
                track[new_pos] = movers + track[new_pos]
            else:
                track[new_pos] = track[new_pos] + movers

        def game_over(track):
            for s in range(FINISH, len(track)):
                if len(track[s]) > 0:
                    return True
            return False

        def chk(hb, val):
            b, s = hb.split(':')
            return b == hashlib.sha256(s.encode() + val.encode()).hexdigest()

        def rank_track(t, pc):
            """Single backward pass to score all camels by finish position."""
            rank = 0
            for si in range(len(t) - 1, -1, -1):
                stack = t[si]
                for j in range(len(stack) - 1, -1, -1):
                    pc[stack[j]][rank] += 1
                    rank += 1
                    if rank == N_CAMELS:
                        return
                if rank == N_CAMELS:
                    return

        # ── round-bet probabilities ───────────────────────────────────────────

        remaining = [i for i in range(N_CAMELS) if g.camel_yet_to_move[i]]
        n_rem     = len(remaining)
        pc        = [[0] * N_CAMELS for _ in range(N_CAMELS)]
        total     = 0

        if n_rem == 0:
            for p in range(1, N_CAMELS + 1):
                c = nth_place(g.camel_track, p)
                if c is not None:
                    pc[c][p - 1] += 1
            total = 1

        elif math.factorial(n_rem) * (3 ** n_rem) <= N_ROUND_SAMPLES:
            # Exact enumeration — only reached for n_rem ≤ 3 (≤162 outcomes)
            for perm in permutations(remaining):
                for combo in range(3 ** n_rem):
                    t = [list(row) for row in g.camel_track]
                    for mi in range(n_rem):
                        d = (combo // (3 ** mi)) % 3 + 1
                        sim_move(t, perm[mi], d, g.trap_track)
                    rank_track(t, pc)
                    total += 1

        else:
            # MC sampling for 4-5 remaining camels
            for _ in range(N_ROUND_SAMPLES):
                perm = random.sample(remaining, n_rem)
                t    = [list(row) for row in g.camel_track]
                for mi in range(n_rem):
                    sim_move(t, perm[mi], random.randint(1, 3), g.trap_track)
                rank_track(t, pc)
                total += 1

        # ── best action (roll = guaranteed 1 coin baseline) ──────────────────

        best_act = [0]
        best_ev  = 1.0

        # Round winner bets
        first_pay = [5, 3, 2, 0]
        for cam in range(N_CAMELS):
            bi = sum(1 for b in g.round_bets if b[0] == cam)
            if bi >= len(first_pay):
                continue
            p1 = pc[cam][0] / total if total else 0
            p2 = pc[cam][1] / total if total else 0
            ev = p1 * first_pay[bi] + p2 * 1 + (1 - p1 - p2) * (-1)
            if ev > best_ev:
                best_ev  = ev
                best_act = [2, cam]

        # ── game-level MC (reduced N_SIM) ─────────────────────────────────────

        wins   = [0] * N_CAMELS
        losses = [0] * N_CAMELS
        _dice      = random.choices((1, 2, 3), k=N_SIM * _MAX_DEPTH)
        _di        = 0
        _randrange = random.randrange

        for _ in range(N_SIM):
            t     = [list(row) for row in g.camel_track]
            bank  = list(remaining)
            depth = 0
            while not game_over(t) and depth < _MAX_DEPTH:
                if not bank:
                    bank = list(range(N_CAMELS))
                idx       = _randrange(len(bank))
                c         = bank[idx]
                bank[idx] = bank[-1]
                bank.pop()
                sim_move(t, c, _dice[_di], g.trap_track)
                _di   += 1
                depth += 1
            w  = nth_place(t, 1)
            lo = nth_place(t, N_CAMELS)
            if w  is not None: wins[w]    += 1
            if lo is not None: losses[lo] += 1

        bet_on = set()
        for hb in g.player_game_bets[player]:
            for c in range(N_CAMELS):
                if chk(hb, str(c)):
                    bet_on.add(c)

        pay = [8, 5, 3, 1]

        for cam in range(N_CAMELS):
            if cam in bet_on:
                continue
            pw = wins[cam] / N_SIM
            pi = min(len(g.game_winner_bets), len(pay) - 1)
            ev = pw * pay[pi] - (1 - pw)
            if ev > best_ev:
                best_ev  = ev
                best_act = [3, cam]

        for cam in range(N_CAMELS):
            if cam in bet_on:
                continue
            pl = losses[cam] / N_SIM
            pi = min(len(g.game_loser_bets), len(pay) - 1)
            ev = pl * pay[pi] - (1 - pl)
            if ev > best_ev:
                best_ev  = ev
                best_act = [4, cam]

        # ── trap placement (identical to OpusOmul) ────────────────────────────

        land = [0.0] * len(g.camel_track)
        for cam in remaining:
            pos, _ = find_pos(g.camel_track, cam)
            if pos is not None:
                for d in range(1, 4):
                    tgt = pos + d
                    if tgt < len(land):
                        land[tgt] += 1.0 / 3.0

        own_trap = None
        if g.player_has_placed_trap[player]:
            for ti, tr in enumerate(g.trap_track):
                if len(tr) >= 2 and tr[1] == player:
                    own_trap = ti
                    break

        for tp in range(1, FINISH + 1):
            if len(g.camel_track[tp]) > 0:
                continue
            ok = True
            for off in [-1, 0, 1]:
                chk_pos = tp + off
                if chk_pos < 0 or chk_pos >= len(g.trap_track):
                    continue
                if len(g.trap_track[chk_pos]) > 0 and chk_pos != own_trap:
                    ok = False
                    break
            if not ok:
                continue
            tev = land[tp]
            if tev > best_ev:
                best_ev  = tev
                best_act = [1, 1, tp]

        return best_act
