# ---
# name: tb-ClaudeCamel
# author: Tyler Barron
# model: Claude Sonnet
# year: 2026
# ---
from playerinterface import PlayerInterface

class ClaudeCamel(PlayerInterface):
    """
    ClaudeCamel: Optimized Camel Up bot.

    Strategy:
      - Round bets: Full enumeration of all remaining camel move permutations
        to compute exact probabilities for 1st/2nd place finish.
      - Game winner/loser bets: Monte Carlo simulation of full games.
      - Rolling dice: Baseline EV = 1 coin guaranteed.
      - Always picks the highest EV action.

    Key improvements vs Sir_Humpfree_Bogart:
      - Fixes MC bug (SHB used stale hyp_camel_track instead of g.camel_track)
      - Fixes camel_bank reference bug (SHB aliased instead of copied)
      - No riskiness distortion — pure EV maximization
      - Avoids slow deepcopy via [list(row) for row in track]
      - Precomputes camel positions for O(1) lookups in sim_move
    """

    def move(player, g):
        from itertools import permutations
        import random
        import hashlib

        FINISH_LINE = 16
        NUM_CAMELS = 5
        TRACK_LEN = len(g.camel_track)

        def check_bet(hashed_bet, user_bet):
            bet, salt = hashed_bet.split(':')
            return bet == hashlib.sha256(salt.encode() + user_bet.encode()).hexdigest()

        def copy_track(track):
            """Fast copy for list-of-lists of ints — much faster than deepcopy."""
            return [list(row) for row in track]

        def copy_trap(trap):
            """Fast copy for trap track (list of [] or [int, int])."""
            return [list(row) for row in trap]

        def build_pos_map(track):
            """Return dict: camel -> (pos, y_pos) for O(1) lookup in sim_move."""
            pos_map = {}
            for ix, row in enumerate(track):
                for iy, c in enumerate(row):
                    pos_map[c] = (ix, iy)
            return pos_map

        def sim_move(camel, dist, track, trap_track, pos_map):
            """
            Move a camel, replicating camelup.py MoveCamel physics exactly.
            Updates track and pos_map in place.
            """
            if camel not in pos_map:
                return
            pos, y_pos = pos_map[camel]
            stack = len(track[pos]) - y_pos
            distance = dist
            stack_from_bottom = False

            dest = pos + distance
            if 0 <= dest < TRACK_LEN and trap_track[dest]:
                if trap_track[dest][0] == -1:
                    stack_from_bottom = True
                distance += trap_track[dest][0]
                dest = pos + distance

            dest = max(0, min(dest, TRACK_LEN - 1))

            if stack_from_bottom:
                for c in range(stack):
                    moved = track[pos].pop(stack - c - 1)
                    track[dest].insert(0, moved)
            else:
                for c in range(stack):
                    moved = track[pos].pop(y_pos)
                    track[dest].append(moved)

            # Rebuild pos_map for affected cells only
            for iy, c in enumerate(track[pos]):
                pos_map[c] = (pos, iy)
            for iy, c in enumerate(track[dest]):
                pos_map[c] = (dest, iy)

        def find_nth(track, n):
            """Return camel in nth place (1 = leading). Searches from track end."""
            counted = 0
            i = 1
            while i <= TRACK_LEN:
                sz = len(track[TRACK_LEN - i])
                if sz >= n - counted:
                    return track[TRACK_LEN - i][sz - (n - counted)]
                counted += sz
                i += 1
            return 0  # safety fallback

        def is_over(pos_map):
            """Game ends when any camel is at or past the finish line."""
            for c in range(NUM_CAMELS):
                if c in pos_map and pos_map[c][0] >= FINISH_LINE:
                    return True
            return False

        # ================================================================
        # ROUND BET ANALYSIS: Enumerate every permutation of remaining moves
        # ================================================================
        remaining = [i for i in range(NUM_CAMELS) if g.camel_yet_to_move[i]]
        n = len(remaining)

        # place_counts[camel][0=other, 1=2nd, 2=1st]
        place_counts = [[0, 0, 0] for _ in range(NUM_CAMELS)]
        total_scenarios = 0

        base_trap = copy_trap(g.trap_track)

        for perm in permutations(remaining, n):
            for combo in range(3 ** n):
                track = copy_track(g.camel_track)
                pos_map = build_pos_map(track)
                trap = base_trap  # traps don't change mid-round; share the reference

                for step in range(n):
                    dist = (combo // (3 ** step)) % 3 + 1
                    sim_move(perm[step], dist, track, trap, pos_map)
                    if is_over(pos_map):
                        break

                first = find_nth(track, 1)
                second = find_nth(track, 2)
                for c in range(NUM_CAMELS):
                    if c == first:
                        place_counts[c][2] += 1
                    elif c == second:
                        place_counts[c][1] += 1
                    else:
                        place_counts[c][0] += 1
                total_scenarios += 1

        # ================================================================
        # GAME WINNER / LOSER: Monte Carlo over full games
        # Note: SHB bug fixed — start from g.camel_track, not stale hyp_track
        # ================================================================
        MC_RUNS = 800
        win_counts = [0] * NUM_CAMELS
        lose_counts = [0] * NUM_CAMELS

        # Pre-generate all dice rolls for the MC loop (one bulk call vs
        # ~64K individual randint calls).
        _MAX_DEPTH = 64
        _dice      = random.choices((1, 2, 3), k=MC_RUNS * _MAX_DEPTH)
        _di        = 0
        _randrange = random.randrange

        for _ in range(MC_RUNS):
            track      = copy_track(g.camel_track)
            trap       = copy_trap(g.trap_track)
            pos_map    = build_pos_map(track)
            yet_to_move = list(g.camel_yet_to_move)
            depth      = 0

            while not is_over(pos_map) and depth < _MAX_DEPTH:
                bank = [i for i in range(NUM_CAMELS) if yet_to_move[i]]
                if not bank:
                    yet_to_move = [True] * NUM_CAMELS
                    trap        = [[] for _ in range(TRACK_LEN)]
                    bank        = list(range(NUM_CAMELS))
                # Swap-and-pop gives O(1) removal; _randrange is a bound
                # method (avoids attribute lookup on every iteration).
                idx = _randrange(len(bank))
                c   = bank[idx]
                bank[idx] = bank[-1]
                bank.pop()
                yet_to_move[c] = False
                sim_move(c, _dice[_di], track, trap, pos_map)
                _di   += 1
                depth += 1

            win_counts[find_nth(track, 1)] += 1
            lose_counts[find_nth(track, NUM_CAMELS)] += 1

        # Determine which camels this player has already game-bet on.
        # Only check own bets (g.player_game_bets[player]) — cracking other
        # players' entries in g.game_winner_bets / g.game_loser_bets would be
        # reading privileged information the hash was designed to hide.
        already_bet = set()
        for hb in g.player_game_bets[player]:
            for c in range(NUM_CAMELS):
                if check_bet(hb, str(c)):
                    already_bet.add(c)
                    break

        # Payout tier: determined by total bets placed so far (not per-camel,
        # since the per-camel breakdown requires cracking hashes we shouldn't
        # crack). Using the total count is a conservative approximation that
        # matches what the game engine exposes without privileged access.
        # TODO: if GameState ever exposes per-camel bet counts directly, use
        # those instead for a more accurate EV.
        total_winner_bets = len(g.game_winner_bets)
        total_loser_bets  = len(g.game_loser_bets)

        # ================================================================
        # SELECT BEST ACTION: compare EV of all options vs rolling (EV=1)
        # ================================================================
        best_ev = 1.0   # Rolling always gives exactly 1 coin
        best_action = [0]

        # --- Round bets ---
        # Payouts decrease as more bets are placed on the same camel
        fp_payouts = [5, 3, 2, 0]
        sp_payouts = [1, 1, 1, 0]

        for camel in range(NUM_CAMELS):
            bet_idx = sum(1 for b in g.round_bets if b[0] == camel)
            if bet_idx >= 3:
                continue  # Would pay 0, skip

            p1 = place_counts[camel][2] / total_scenarios
            p2 = place_counts[camel][1] / total_scenarios
            po = place_counts[camel][0] / total_scenarios

            ev = p1 * fp_payouts[bet_idx] + p2 * sp_payouts[bet_idx] + po * (-1)
            if ev > best_ev:
                best_ev = ev
                best_action = [2, camel]

        # --- Game winner bets ---
        # Payout: 8, 5, 3, 1 (first four correct bettors); wrong = -1.
        # We use total_winner_bets as the payout-tier index — a slight
        # over-estimate of the competition for any single camel, but it avoids
        # reading information we're not entitled to.
        payout_struct = [8, 5, 3, 1]

        for camel in range(NUM_CAMELS):
            if camel in already_bet:
                continue
            p_win  = win_counts[camel] / MC_RUNS
            payout = payout_struct[min(total_winner_bets, len(payout_struct) - 1)]
            ev     = p_win * payout - (1 - p_win) * 1
            if ev > best_ev:
                best_ev = ev
                best_action = [3, camel]

        # --- Game loser bets ---
        for camel in range(NUM_CAMELS):
            if camel in already_bet:
                continue
            p_lose = lose_counts[camel] / MC_RUNS
            payout = payout_struct[min(total_loser_bets, len(payout_struct) - 1)]
            ev     = p_lose * payout - (1 - p_lose) * 1
            if ev > best_ev:
                best_ev = ev
                best_action = [4, camel]

        return best_action
