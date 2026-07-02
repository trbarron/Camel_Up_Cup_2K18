from playerinterface import PlayerInterface
import random
import copy
import hashlib
import uuid

# --- Simulation Helpers (Module Level) ---

def simulate_round(g):
    while sum(g.camel_yet_to_move) > 0 and g.active_game:
        available = [i for i, x in enumerate(g.camel_yet_to_move) if x]
        if not available: break
        c = random.choice(available)
        sim_move_camel(g, c)
        
        # Check game end
        if len(g.camel_track) > 16:
             if len(g.camel_track[16]) + len(g.camel_track[17]) + len(g.camel_track[18]) > 0:
                g.active_game = False
                return get_leader(g.camel_track)
    return get_leader(g.camel_track)

def sim_move_camel(g, camel_index):
    g.camel_yet_to_move[camel_index] = False
    
    # Find camel
    curr_pos = -1
    found_y_pos = -1
    for ix, row in enumerate(g.camel_track):
        if camel_index in row:
            curr_pos = ix
            found_y_pos = row.index(camel_index)
            break
            
    if curr_pos == -1: return

    stack_len = len(g.camel_track[curr_pos]) - found_y_pos
    distance = random.randint(1, 3)
    
    target_pos = curr_pos + distance
    stack_from_bottom = False
    
    if target_pos < len(g.trap_track) and len(g.trap_track[target_pos]) > 0:
        trap = g.trap_track[target_pos]
        if trap[0] == -1:
            stack_from_bottom = True
        distance += trap[0]
        
    final_pos = curr_pos + distance
    # Ensure track size. camelup.py has 29 spaces.
    if final_pos >= len(g.camel_track): final_pos = len(g.camel_track) - 1
    
    camels_to_move = []
    source_stack = g.camel_track[curr_pos]
    
    if stack_from_bottom:
        # Replicating trap -1 logic: sends to bottom of stack at destination
        # Implementation in camelup.py implies popping stack-c-1
        # [A, B] -> Pop B -> Insert B at 0 -> [B, ...]
        # Pop A -> Insert A at 0 -> [A, B, ...]
        # Order preserved.
        for c in range(stack_len):
            pop_idx = stack_len - c - 1
            if pop_idx < len(source_stack):
                camels_to_move.append(source_stack.pop(pop_idx))
            
            if camels_to_move:
                g.camel_track[final_pos].insert(0, camels_to_move[0])
                camels_to_move.clear()
    else:
        # Normal stack: on top
        for c in range(stack_len):
            if found_y_pos < len(source_stack):
                camels_to_move.append(source_stack.pop(found_y_pos))
                g.camel_track[final_pos].append(camels_to_move[0])
                camels_to_move.clear()

def get_leader(track):
    for i in range(len(track)-1, -1, -1):
        if track[i]: return track[i][-1]
    return None

def get_loser(track):
    for i in range(len(track)):
        if track[i]: return track[i][0]
    return None

def verify_bet(hashed_bet, user_bet):
    try:
        bet, salt = hashed_bet.split(':')
        return bet == hashlib.sha256(salt.encode() + user_bet.encode()).hexdigest()
    except:
        return False

class GeminiGerry(PlayerInterface):
    def move(player_index, current_game_state):
        # GeminiGerry: Optimized Risk-Taker
        
        g = current_game_state
        
        # --- Parameters ---
        NUM_SIMULATIONS = 750 
        ROLL_EV = 1.0
        
        # --- 1. Simulation ---
        wins = {0:0, 1:0, 2:0, 3:0, 4:0}
        losses = {0:0, 1:0, 2:0, 3:0, 4:0}
        round_wins = {0:0, 1:0, 2:0, 3:0, 4:0}
        
        for _ in range(NUM_SIMULATIONS):
            sim_g = copy.deepcopy(g)
            
            # Sim Round
            r_winner = simulate_round(sim_g)
            if r_winner is not None:
                round_wins[r_winner] += 1
                
            # Sim Remainder of Game
            while sim_g.active_game:
                # Approximate next round setup if game active
                sim_g.camel_yet_to_move = [True]*5
                sim_g.trap_track = [[] for _ in range(29)]
                
                simulate_round(sim_g)
                
            g_winner = get_leader(sim_g.camel_track)
            g_loser = get_loser(sim_g.camel_track)
            if g_winner is not None: wins[g_winner] += 1
            if g_loser is not None: losses[g_loser] += 1

        # --- 2. Evaluation ---
        best_action = [0] # Roll
        best_ev = ROLL_EV + 0.1 # Bias slightly towards action if EV is significantly better
        
        # A. Round Bets
        camel_round_bet_counts = {0:0, 1:0, 2:0, 3:0, 4:0}
        for bet in g.round_bets:
            if bet[0] in camel_round_bet_counts:
                camel_round_bet_counts[bet[0]] += 1
        
        payout_tiers = [5, 3, 2, 0] 
        
        for c in range(5):
            prob = round_wins[c] / NUM_SIMULATIONS
            
            current_bets = camel_round_bet_counts[c]
            if current_bets < 3:
                payout = payout_tiers[current_bets]
            else:
                payout = 0 
            
            if payout > 0:
                ev = prob * payout - (1.0 - prob) * 1.0
                if ev > best_ev:
                    best_ev = ev
                    best_action = [2, c]

        # B. Game Winner Bets (Risky)
        # Assume max payout (8) to encourage early betting
        for c in range(5):
            prob = wins[c] / NUM_SIMULATIONS
            if prob > 0.25:
                ev = prob * 8.0 - (1.0 - prob) * 1.0
                if ev > best_ev:
                    # Check if already bet
                    already_bet = False
                    for bet_hash in g.player_game_bets[player_index]:
                        if verify_bet(bet_hash, str(c)):
                            already_bet = True; break
                    
                    if not already_bet:
                        best_ev = ev
                        best_action = [3, c]

        # C. Game Loser Bets (Risky)
        for c in range(5):
            prob = losses[c] / NUM_SIMULATIONS
            if prob > 0.25:
                ev = prob * 8.0 - (1.0 - prob) * 1.0
                if ev > best_ev:
                    already_bet = False
                    for bet_hash in g.player_game_bets[player_index]:
                        if verify_bet(bet_hash, str(c)):
                            already_bet = True; break
                    
                    if not already_bet:
                        best_ev = ev
                        best_action = [4, c]

        return best_action