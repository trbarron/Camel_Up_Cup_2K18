"""
NeatCamel — NEAT-evolved neural network bot for Camel Up.

A 39-feature game-state vector is fed through a feedforward network whose
topology and weights were evolved via NeuroEvolution of Augmenting Topologies
(NEAT).  The highest-scoring valid output neuron selects the action each turn.

Input vector (39 features):
  [0-4]   camel positions / finish_line
  [5-9]   camel y-position in stack / num_camels
  [10-14] camel_yet_to_move flags
  [15-18] player money / max_money
  [19-21] (other_money - my_money) / max_money  (3 relative values)
  [22-26] round bets already placed per camel / 4.0
  [27-31] game bet already placed on this camel (winner or loser)
  [32]    total game winner bets / 10.0
  [33]    total game loser bets / 10.0
  [34]    my trap placed
  [35]    leader position / finish_line  (game-end proximity)
  [36]    (leader - trailer) / finish_line  (race spread)
  [37]    camels remaining this round / num_camels  (round stage)
  [38]    my rank among players / 3.0

Output vector (16 nodes → masked to valid actions only):
  [0]     Roll
  [1-5]   Round winner bet on camel 0-4
  [6-10]  Game winner bet on camel 0-4
  [11-15] Game loser bet on camel 0-4

Train with:
    pip install neat-python
    python train_neat.py
"""

import hashlib
import os
import pickle
import sys

from playerinterface import PlayerInterface

_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Network loading (once at import time) ─────────────────────────────────────

_NUM_CAMELS  = 5
_FINISH_LINE = 16


def _load_net():
    try:
        import neat
    except ImportError:
        raise ImportError("neat-python required: pip install neat-python")

    config_path = os.path.join(_DIR, "neat_config.txt")
    genome_path = os.path.join(_DIR, "neat_best_genome.pkl")

    if not os.path.exists(genome_path):
        raise FileNotFoundError(
            f"Trained genome not found at {genome_path}. "
            "Run: python train_neat.py"
        )

    config = neat.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        config_path,
    )
    with open(genome_path, "rb") as f:
        genome = pickle.load(f)
    return neat.nn.FeedForwardNetwork.create(genome, config)


_NET = None
try:
    _NET = _load_net()
except FileNotFoundError as e:
    print(f"[NeatCamel] {e}")
    print("[NeatCamel] Falling back to round-bet baseline until trained.")
except Exception as e:
    print(f"[NeatCamel] Could not load network ({e}). Falling back to baseline.")


# ── Feature extraction (mirrors train_neat.py) ────────────────────────────────

def _check_bet(hashed_bet, user_bet):
    bet, salt = hashed_bet.split(':')
    return bet == hashlib.sha256(salt.encode() + user_bet.encode()).hexdigest()


def _extract_features(player, g):
    camel_pos_raw = [0] * _NUM_CAMELS
    camel_stack   = [0.0] * _NUM_CAMELS
    for ix, row in enumerate(g.camel_track):
        for iy, camel in enumerate(row):
            camel_pos_raw[camel] = ix
            camel_stack[camel]   = iy / _NUM_CAMELS

    camel_pos = [p / _FINISH_LINE for p in camel_pos_raw]

    my_money  = g.player_money_values[player]
    max_money = max(max(g.player_money_values), 1)

    round_bets_per_camel = [0] * _NUM_CAMELS
    for bet in g.round_bets:
        if 0 <= bet[0] < _NUM_CAMELS:
            round_bets_per_camel[bet[0]] += 1

    already_bet = [0.0] * _NUM_CAMELS
    for hb in g.player_game_bets[player]:
        for c in range(_NUM_CAMELS):
            if _check_bet(hb, str(c)):
                already_bet[c] = 1.0
                break

    leader_raw  = max(camel_pos_raw)
    trailer_raw = min(camel_pos_raw)

    features = []
    features.extend(camel_pos)
    features.extend(camel_stack)
    features.extend([1.0 if m else 0.0 for m in g.camel_yet_to_move])
    features.extend([m / max_money for m in g.player_money_values])
    features.extend(
        [(m - my_money) / max_money
         for i, m in enumerate(g.player_money_values) if i != player]
    )
    features.extend([c / 4.0 for c in round_bets_per_camel])
    features.extend(already_bet)
    features.append(min(len(g.game_winner_bets) / 10.0, 1.0))
    features.append(min(len(g.game_loser_bets)  / 10.0, 1.0))
    features.append(1.0 if g.player_has_placed_trap[player] else 0.0)
    features.append(leader_raw / _FINISH_LINE)                                        # game proximity
    features.append((leader_raw - trailer_raw) / _FINISH_LINE)                        # race spread
    features.append(sum(1.0 if m else 0.0 for m in g.camel_yet_to_move) / _NUM_CAMELS)  # round stage
    features.append(sum(1 for m in g.player_money_values if m > my_money) / 3.0)     # my rank
    return features  # 39 features


def _get_valid_actions(player, g):
    valid = [(0, [0])]  # Roll always valid

    for c in range(_NUM_CAMELS):
        valid.append((1 + c, [2, c]))  # Round bet

    already_bet = set()
    for hb in g.player_game_bets[player]:
        for c in range(_NUM_CAMELS):
            if _check_bet(hb, str(c)):
                already_bet.add(c)
                break

    for c in range(_NUM_CAMELS):
        if c not in already_bet:
            valid.append((6  + c, [3, c]))  # Game winner bet
            valid.append((11 + c, [4, c]))  # Game loser bet

    return valid


# ── Bot class ─────────────────────────────────────────────────────────────────

class NeatCamel(PlayerInterface):
    """
    NEAT-evolved neural network bot.

    Topology and weights were discovered by NeuroEvolution of Augmenting
    Topologies (NEAT) — the algorithm simultaneously evolves network structure
    and weights, starting from minimal networks and adding complexity only when
    it improves fitness (avg coins/game vs random opponents).

    Train / retrain: python train_neat.py [--generations N] [--games G]
                                          [--strong-opponents]
    """

    def move(player, g):
        if _NET is None:
            # Fallback: pick the round bet with the fewest existing bets.
            bets_per = [sum(1 for b in g.round_bets if b[0] == c)
                        for c in range(_NUM_CAMELS)]
            return [2, bets_per.index(min(bets_per))]

        outputs = _NET.activate(_extract_features(player, g))
        valid   = _get_valid_actions(player, g)
        _, action = max(valid, key=lambda va: outputs[va[0]])
        return action
