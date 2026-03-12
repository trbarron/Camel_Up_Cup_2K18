#!/usr/bin/env python3
"""
NEAT training script for NeatCamel.

Evolves a neural network using NeuroEvolution of Augmenting Topologies (NEAT)
to play Camel Up. The best genome is saved to neat_best_genome.pkl.

Input vector (39 features):
  [0-4]   camel positions normalised by finish line (one per camel)
  [5-9]   camel y-position in stack normalised (one per camel)
  [10-14] camel_yet_to_move flags (bool per camel)
  [15-18] player money normalised by max (all 4 players)
  [19-21] (other_money - my_money) / max_money (3 relative values)
  [22-26] round bets already placed per camel / 4.0
  [27-31] game bet already placed on this camel (winner or loser)
  [32]    total game winner bets / 10.0
  [33]    total game loser bets / 10.0
  [34]    my trap placed (bool)
  [35]    leader position / finish_line  (game-end proximity)
  [36]    (leader - trailer) / finish_line  (race spread / tightness)
  [37]    camels remaining this round / num_camels  (round stage)
  [38]    my rank among players / 3.0  (0=first, 1=last)

Output vector (16 nodes):
  [0]     Roll dice
  [1-5]   Round winner bet on camel 0-4
  [6-10]  Game winner bet on camel 0-4
  [11-15] Game loser bet on camel 0-4

Fitness = avg_coins + win_rate * 10  (blended: coins + win bonus)

Usage:
    pip install neat-python
    python train_neat.py
    python train_neat.py --generations 100 --games 30
"""

import argparse
import copy
import hashlib
import multiprocessing
import os
import pickle
import random
import sqlite3
import sys
import time

try:
    import neat
except ImportError:
    sys.exit("neat-python not found. Install with: pip install neat-python")

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from camelup import (
    GameState,
    MoveCamel, PlaceTrap, MoveTrap,
    PlaceRoundWinnerBet, PlaceGameWinnerBet, PlaceGameLoserBet,
)

# ── Constants ─────────────────────────────────────────────────────────────────

NUM_CAMELS  = 5
NUM_PLAYERS = 4
FINISH_LINE = 16
TRACK_LEN   = 29
NUM_INPUTS  = 39
NUM_OUTPUTS = 16

# ── Training history DB ───────────────────────────────────────────────────────

_DB_PATH = os.path.join(_DIR, "neat_training_history.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT,
    finished_at      TEXT,
    generations      INTEGER,
    start_generation INTEGER DEFAULT 0,
    games_per_genome INTEGER,
    pop_size         INTEGER,
    strong_opponents INTEGER,
    resumed_from_run INTEGER REFERENCES runs(id),
    best_fitness     REAL,
    nodes            INTEGER,
    connections      INTEGER,
    benchmark_neat_avg  REAL,
    benchmark_opp_avg   REAL,
    benchmark_opp_label TEXT
);

CREATE TABLE IF NOT EXISTS generations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER REFERENCES runs(id),
    generation   INTEGER,
    best_fitness REAL,
    mean_fitness REAL,
    n_species    INTEGER,
    nodes        INTEGER,
    connections  INTEGER,
    elapsed_sec  REAL
);
"""

_CHECKPOINT_DIR = os.path.join(_DIR, "neat_checkpoints")


def _db_connect():
    con = sqlite3.connect(_DB_PATH)
    con.executescript(_SCHEMA)
    # Migrate older DBs that predate new columns
    for col, defn in [
        ("start_generation", "INTEGER DEFAULT 0"),
        ("resumed_from_run", "INTEGER"),
    ]:
        try:
            con.execute(f"ALTER TABLE runs ADD COLUMN {col} {defn}")
            con.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    return con


def _db_start_run(con, generations, games, pop_size, strong_opponents,
                  start_generation=0, resumed_from_run=None):
    cur = con.execute(
        "INSERT INTO runs "
        "(started_at, generations, start_generation, games_per_genome, pop_size, "
        " strong_opponents, resumed_from_run) "
        "VALUES (datetime('now'), ?, ?, ?, ?, ?, ?)",
        (generations, start_generation, games, pop_size,
         int(strong_opponents), resumed_from_run),
    )
    con.commit()
    return cur.lastrowid


def _db_record_generation(con, run_id, gen, best_f, mean_f, n_species, nodes, conns, elapsed):
    con.execute(
        "INSERT INTO generations "
        "(run_id, generation, best_fitness, mean_fitness, n_species, nodes, connections, elapsed_sec) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, gen, best_f, mean_f, n_species, nodes, conns, elapsed),
    )
    con.commit()


def _db_finish_run(con, run_id, best_fitness, nodes, connections,
                   neat_avg, opp_avg, opp_label):
    con.execute(
        "UPDATE runs SET finished_at=datetime('now'), best_fitness=?, nodes=?, connections=?, "
        "benchmark_neat_avg=?, benchmark_opp_avg=?, benchmark_opp_label=? WHERE id=?",
        (best_fitness, nodes, connections, neat_avg, opp_avg, opp_label, run_id),
    )
    con.commit()


def show_history(db_path=_DB_PATH, last_n=10):
    """Print a table of the last N training runs from the history DB."""
    if not os.path.exists(db_path):
        print("No training history found (neat_training_history.db doesn't exist yet).")
        return
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT id, started_at, generations, start_generation, games_per_genome, pop_size, "
        "       strong_opponents, resumed_from_run, best_fitness, nodes, connections, "
        "       benchmark_neat_avg, benchmark_opp_avg, benchmark_opp_label "
        "FROM runs ORDER BY id DESC LIMIT ?",
        (last_n,),
    ).fetchall()
    if not rows:
        print("History DB exists but contains no runs yet.")
        return

    opp_label = next((r[13] for r in rows if r[13]), "opp")
    print(f"\n{'─'*105}")
    print(f"  {'#':>3}  {'started':>19}  {'gens':>9}  {'g/gen':>5}  {'pop':>3}  "
          f"{'strong':>6}  {'resumes':>7}  {'best fit':>8}  {'nodes':>5}  {'conns':>5}  "
          f"{'vs ' + opp_label:>14}")
    print(f"{'─'*105}")
    for r in reversed(rows):
        (run_id, started, gens, start_gen, games, pop, strong,
         resumed_from, best_f, nodes, conns, neat_avg, opp_avg, _opp_label) = r
        opp_col     = f"{neat_avg:.1f} vs {opp_avg:.1f}" if neat_avg is not None else "—"
        resume_col  = f"#{resumed_from}" if resumed_from else "—"
        gen_range   = f"{start_gen}–{start_gen + gens - 1}"
        print(f"  {run_id:>3}  {started or '':>19}  {gen_range:>9}  {games:>5}  {pop:>3}  "
              f"{'yes' if strong else 'no':>6}  {resume_col:>7}  {best_f or 0:>8.2f}  "
              f"{nodes or 0:>5}  {conns or 0:>5}  {opp_col:>14}")
    print(f"{'─'*105}")

    # Fitness trajectory per run
    print("\nFitness trajectory (best per generation):\n")
    for r in reversed(rows):
        run_id, started, gens, start_gen = r[0], r[1], r[2], r[3]
        resumed_from = r[7]
        gens_data = con.execute(
            "SELECT generation, best_fitness FROM generations WHERE run_id=? ORDER BY generation",
            (run_id,),
        ).fetchall()
        if not gens_data:
            continue
        vals = [gd[1] for gd in gens_data]
        lo, hi = min(vals), max(vals)
        blocks = " ▁▂▃▄▅▆▇█"
        spark = (
            "".join(blocks[int((v - lo) / (hi - lo) * 8)] for v in vals)
            if hi > lo else "─" * len(vals)
        )
        resume_note = f"  (continues #{resumed_from})" if resumed_from else ""
        print(f"  Run {run_id:>3}  gen {start_gen:>3}–{start_gen+len(vals)-1:<3}"
              f"  [{spark}]  {vals[0]:.1f}→{vals[-1]:.1f}"
              f"  peak={max(vals):.1f}{resume_note}")

    # Show available checkpoints
    if os.path.isdir(_CHECKPOINT_DIR):
        ckpts = sorted(
            f for f in os.listdir(_CHECKPOINT_DIR) if f.startswith("neat-checkpoint-")
        )
        if ckpts:
            print(f"\nAvailable checkpoints ({_CHECKPOINT_DIR}):")
            for ck in ckpts:
                path = os.path.join(_CHECKPOINT_DIR, ck)
                size_kb = os.path.getsize(path) // 1024
                print(f"  {ck}  ({size_kb} KB)")
            print(f"\n  Resume with: python train_neat.py --resume {os.path.join(_CHECKPOINT_DIR, ckpts[-1])}")
    print()
    con.close()


# ── Feature extraction ────────────────────────────────────────────────────────

def _check_bet(hashed_bet, user_bet):
    bet, salt = hashed_bet.split(':')
    return bet == hashlib.sha256(salt.encode() + user_bet.encode()).hexdigest()


def extract_features(player, g):
    """Return a 39-element normalised feature vector for the current game state."""
    camel_pos_raw = [0] * NUM_CAMELS
    camel_stack   = [0.0] * NUM_CAMELS
    for ix, row in enumerate(g.camel_track):
        for iy, camel in enumerate(row):
            camel_pos_raw[camel] = ix
            camel_stack[camel]   = iy / NUM_CAMELS

    camel_pos = [p / FINISH_LINE for p in camel_pos_raw]

    my_money  = g.player_money_values[player]
    max_money = max(max(g.player_money_values), 1)

    round_bets_per_camel = [0] * NUM_CAMELS
    for bet in g.round_bets:
        if 0 <= bet[0] < NUM_CAMELS:
            round_bets_per_camel[bet[0]] += 1

    already_bet = [0.0] * NUM_CAMELS
    for hb in g.player_game_bets[player]:
        for c in range(NUM_CAMELS):
            if _check_bet(hb, str(c)):
                already_bet[c] = 1.0
                break

    # Derived features
    leader_raw  = max(camel_pos_raw)
    trailer_raw = min(camel_pos_raw)

    features = []
    features.extend(camel_pos)                                                        # 5
    features.extend(camel_stack)                                                       # 5
    features.extend([1.0 if m else 0.0 for m in g.camel_yet_to_move])                # 5
    features.extend([m / max_money for m in g.player_money_values])                   # 4
    features.extend(
        [(m - my_money) / max_money
         for i, m in enumerate(g.player_money_values) if i != player]
    )                                                                                  # 3
    features.extend([c / 4.0 for c in round_bets_per_camel])                         # 5
    features.extend(already_bet)                                                       # 5
    features.append(min(len(g.game_winner_bets) / 10.0, 1.0))                        # 1
    features.append(min(len(g.game_loser_bets)  / 10.0, 1.0))                        # 1
    features.append(1.0 if g.player_has_placed_trap[player] else 0.0)                # 1
    features.append(leader_raw / FINISH_LINE)                                         # 1  game proximity
    features.append((leader_raw - trailer_raw) / FINISH_LINE)                         # 1  race spread
    features.append(sum(1.0 if m else 0.0 for m in g.camel_yet_to_move) / NUM_CAMELS)# 1  round stage
    features.append(sum(1 for m in g.player_money_values if m > my_money) / 3.0)     # 1  my rank
    # Total: 39
    return features


# ── Action helpers ────────────────────────────────────────────────────────────

def get_valid_actions(player, g):
    """Return list of (output_index, game_action) pairs for all legal actions."""
    valid = [(0, [0])]  # Roll is always valid

    for c in range(NUM_CAMELS):
        valid.append((1 + c, [2, c]))  # Round bet

    # Game bets: skip camels already bet on (winner or loser)
    already_bet = set()
    for hb in g.player_game_bets[player]:
        for c in range(NUM_CAMELS):
            if _check_bet(hb, str(c)):
                already_bet.add(c)
                break

    for c in range(NUM_CAMELS):
        if c not in already_bet:
            valid.append((6  + c, [3, c]))  # Game winner bet
            valid.append((11 + c, [4, c]))  # Game loser bet

    return valid


def select_action(net, player, g):
    features = extract_features(player, g)
    expected = len(net.input_nodes)
    if len(features) != expected:
        features = features[:expected] + [0.0] * max(0, expected - len(features))
    outputs = net.activate(features)
    valid   = get_valid_actions(player, g)
    _, action = max(valid, key=lambda va: outputs[va[0]])
    return action


# ── Opponents ─────────────────────────────────────────────────────────────────

def _random_move(player, g):
    """Baseline opponent: 50% roll, 50% random round bet."""
    if random.random() < 0.5:
        return [0]
    return [2, random.randint(0, NUM_CAMELS - 1)]


# Swap in a stronger mix once the bots are importable.
_OPPONENT_POOL = [_random_move]
try:
    from TrainingOpponent import TrainingOpponent
    _OPPONENT_POOL = [_random_move, TrainingOpponent.move]
except Exception:
    pass


def _opponent_move(player, g):
    return random.choice(_OPPONENT_POOL)(player, g)


def _try_load_strong_opponents():
    """Load TrainingOpponent as the strong opponent pool."""
    global _OPPONENT_POOL
    try:
        from TrainingOpponent import TrainingOpponent
        _OPPONENT_POOL = [TrainingOpponent.move]
        print("[train_neat] Using 100% TrainingOpponent as opponent (~2ms/move).")
    except Exception:
        print("[train_neat] Could not load TrainingOpponent, falling back to default mix.")


# ── Parallel evaluation helpers ───────────────────────────────────────────────

def _worker_init(games, use_strong):
    """Initialise per-worker globals when multiprocessing pool spawns."""
    global GAMES_PER_GENOME, _OPPONENT_POOL
    GAMES_PER_GENOME = games
    try:
        from TrainingOpponent import TrainingOpponent
        if use_strong:
            _OPPONENT_POOL = [TrainingOpponent.move]
        else:
            _OPPONENT_POOL = [_random_move, TrainingOpponent.move]
    except Exception:
        pass


def _eval_one(args):
    """Evaluate a single genome in a worker process."""
    genome, config = args
    net         = neat.nn.FeedForwardNetwork.create(genome, config)
    total_coins = 0
    total_wins  = 0
    for i in range(GAMES_PER_GENOME):
        coins, won = run_training_game(net, i % NUM_PLAYERS)
        total_coins += coins
        total_wins  += won
    avg_coins = total_coins / GAMES_PER_GENOME
    win_rate  = total_wins  / GAMES_PER_GENOME
    return avg_coins + win_rate * 10


_POOL = None  # multiprocessing.Pool, created once in main()


# ── Game runner ───────────────────────────────────────────────────────────────

def run_training_game(net, neat_seat):
    """Play one complete game; return (coins, won) for the NEAT bot."""
    g    = GameState()
    turn = 0

    while g.active_game:
        seat = turn % NUM_PLAYERS

        # No deepcopy: both NEAT and TrainingOpponent are read-only on g.
        if seat == neat_seat:
            result = select_action(net, seat, g)
        else:
            result = _opponent_move(seat, g)

        try:
            code = result[0]
            if code == 0:
                MoveCamel(g, seat)
            elif code == 1:
                fn = MoveTrap if g.player_has_placed_trap[seat] else PlaceTrap
                fn(g, result[1], result[2], seat)
            elif code == 2:
                PlaceRoundWinnerBet(g, result[1], seat)
            elif code == 3:
                PlaceGameWinnerBet(g, result[1], seat)
            elif code == 4:
                PlaceGameLoserBet(g, result[1], seat)
            else:
                MoveCamel(g, seat)
        except Exception:
            MoveCamel(g, seat)

        turn += 1

    coins = g.player_money_values[neat_seat]
    won   = 1.0 if coins >= max(g.player_money_values) else 0.0
    return coins, won


# ── NEAT evaluation ───────────────────────────────────────────────────────────

GAMES_PER_GENOME = 20  # overridden by CLI args


def eval_genomes(genomes, config):
    if _POOL is not None:
        results = _POOL.map(_eval_one, [(g, config) for _, g in genomes])
        for (_, genome), fitness in zip(genomes, results):
            genome.fitness = fitness
    else:
        for _, genome in genomes:
            net         = neat.nn.FeedForwardNetwork.create(genome, config)
            total_coins = 0
            total_wins  = 0
            for i in range(GAMES_PER_GENOME):
                coins, won = run_training_game(net, i % NUM_PLAYERS)
                total_coins += coins
                total_wins  += won
            avg_coins = total_coins / GAMES_PER_GENOME
            win_rate  = total_wins  / GAMES_PER_GENOME
            genome.fitness = avg_coins + win_rate * 10


# ── Custom reporter ───────────────────────────────────────────────────────────

class _ProgressReporter(neat.reporting.BaseReporter):
    """
    Compact per-generation summary line:

        Gen  5  best=14.20  mean= 6.78  Δbest=+0.00  species=1  nodes=16  conns=280  2.3s
             ↑                                  ↑
         generation              improvement vs generation 0 best
    """

    def __init__(self, db_con=None, run_id=None, viz_freq=0, viz_dir=None, neat_config=None):
        self.gen         = 0
        self._start      = None
        self.best_hist   = []   # best fitness per generation
        self.mean_hist   = []   # mean fitness per generation
        self._db_con     = db_con
        self._run_id     = run_id
        self._viz_freq   = viz_freq      # save topology image every N gens (0=off)
        self._viz_dir    = viz_dir
        self._neat_config = neat_config

    def start_generation(self, generation):
        self.gen    = generation
        self._start = time.time()

    def post_evaluate(self, config, population, species_set, best_genome):
        elapsed   = time.time() - self._start
        fitnesses = [g.fitness for g in population.values() if g.fitness is not None]
        mean_f    = sum(fitnesses) / len(fitnesses)
        best_f    = best_genome.fitness
        n_species = len(species_set.species)
        nodes     = len(best_genome.nodes)
        conns     = len(best_genome.connections)

        self.best_hist.append(best_f)
        self.mean_hist.append(mean_f)

        if self._db_con and self._run_id:
            _db_record_generation(
                self._db_con, self._run_id,
                self.gen, best_f, mean_f, n_species, nodes, conns, elapsed,
            )

        baseline = self.best_hist[0]
        delta    = best_f - baseline
        sign     = "+" if delta >= 0 else ""

        # ASCII sparkline of best fitness (last 20 gens)
        hist = self.best_hist[-20:]
        lo, hi = min(hist), max(hist)
        blocks = " ▁▂▃▄▅▆▇█"
        if hi > lo:
            spark = "".join(blocks[int((v - lo) / (hi - lo) * 8)] for v in hist)
        else:
            spark = "─" * len(hist)

        print(
            f"Gen {self.gen:>3}  best={best_f:6.2f}  mean={mean_f:5.2f}"
            f"  Δbest={sign}{delta:.2f}  species={n_species}"
            f"  nodes={nodes}  conns={conns:>4}  [{spark}]  {elapsed:.1f}s"
        )

        if (self._viz_freq and self._viz_dir and self._neat_config
                and self.gen % self._viz_freq == 0):
            try:
                from neat_viz import draw_topology
                viz_path = os.path.join(
                    self._viz_dir, f"topology_gen{self.gen:04d}.png"
                )
                draw_topology(
                    best_genome, self._neat_config, viz_path,
                    title=f"gen {self.gen}  best={best_f:.2f}",
                )
            except Exception as e:
                print(f"[neat_viz] skipped: {e}")

    # Silence the default end-of-run summary (we print our own)
    def found_solution(self, config, generation, best):
        pass

    # sqlite3.Connection can't be pickled — exclude it from checkpoint state
    def __getstate__(self):
        state = self.__dict__.copy()
        state['_db_con']      = None
        state['_neat_config'] = None   # Config not pickle-safe across checkpoints
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)


def _plot_fitness(best_hist, mean_hist, out_path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        gens = list(range(len(best_hist)))
        plt.figure(figsize=(10, 5))
        plt.plot(gens, best_hist, label="Best", linewidth=2)
        plt.plot(gens, mean_hist, label="Mean", linewidth=1, linestyle="--", alpha=0.7)
        plt.fill_between(gens, mean_hist, best_hist, alpha=0.15)
        plt.xlabel("Generation")
        plt.ylabel("Avg coins / game")
        plt.title("NeatCamel NEAT Training — Fitness over Generations")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(out_path, dpi=120)
        print(f"Fitness plot saved → {out_path}")
    except ImportError:
        print("(matplotlib not installed — skipping fitness plot)")


def _benchmark(winner, config, n_games=100):
    """Quick post-training benchmark: NeatCamel vs ClaudeCamel vs random.
    Returns (neat_avg_coins, opp_avg_coins, opp_label)."""
    print(f"\nRunning post-training benchmark ({n_games} games)…")

    net = neat.nn.FeedForwardNetwork.create(winner, config)

    def neat_move(player, g):
        return select_action(net, player, g)

    # Try to load ClaudeCamel; fall back to random
    try:
        from ClaudeCamel import ClaudeCamel
        strong_move = ClaudeCamel.move
        opp_label   = "ClaudeCamel"
    except Exception:
        strong_move = _random_move
        opp_label   = "random"

    neat_coins   = []
    strong_coins = []

    for i in range(n_games):
        neat_seat   = i % NUM_PLAYERS
        strong_seat = (neat_seat + 1) % NUM_PLAYERS

        g    = GameState()
        turn = 0
        while g.active_game:
            seat   = turn % NUM_PLAYERS
            g_snap = copy.deepcopy(g)
            if seat == neat_seat:
                result = neat_move(seat, g_snap)
            elif seat == strong_seat:
                result = strong_move(seat, g_snap)
            else:
                result = _random_move(seat, g_snap)
            try:
                code = result[0]
                if code == 0:
                    MoveCamel(g, seat)
                elif code == 1:
                    fn = MoveTrap if g.player_has_placed_trap[seat] else PlaceTrap
                    fn(g, result[1], result[2], seat)
                elif code == 2:
                    PlaceRoundWinnerBet(g, result[1], seat)
                elif code == 3:
                    PlaceGameWinnerBet(g, result[1], seat)
                elif code == 4:
                    PlaceGameLoserBet(g, result[1], seat)
                else:
                    MoveCamel(g, seat)
            except Exception:
                MoveCamel(g, seat)
            turn += 1

        neat_coins.append(g.player_money_values[neat_seat])
        strong_coins.append(g.player_money_values[strong_seat])

    neat_avg   = sum(neat_coins)   / n_games
    strong_avg = sum(strong_coins) / n_games
    neat_wins  = sum(
        1 for nc, sc in zip(neat_coins, strong_coins) if nc >= sc
    )

    print(f"\n  {'Bot':<16}  {'Avg coins':>10}  {'Win/tie rate':>12}")
    print(f"  {'-'*44}")
    print(f"  {'NeatCamel':<16}  {neat_avg:>10.2f}  {100*neat_wins/n_games:>11.1f}%")
    print(f"  {opp_label:<16}  {strong_avg:>10.2f}  {100*(n_games-neat_wins)/n_games:>11.1f}%")
    return neat_avg, strong_avg, opp_label


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Train NeatCamel using NEAT",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--generations", type=int, default=50,
                        help="Number of NEAT generations to run")
    parser.add_argument("--games", type=int, default=20,
                        help="Games per genome per generation (higher = more stable but slower)")
    parser.add_argument("--config", default=os.path.join(_DIR, "neat_config.txt"),
                        help="Path to NEAT config file")
    parser.add_argument("--out", default=os.path.join(_DIR, "neat_best_genome.pkl"),
                        help="Output path for best genome pickle")
    parser.add_argument("--strong-opponents", action="store_true",
                        help="Include ClaudeCamel and Sir_Humpfree as training opponents")
    parser.add_argument("--checkpoint-freq", type=int, default=10, metavar="N",
                        help="Save a population checkpoint every N generations")
    parser.add_argument("--resume", metavar="CHECKPOINT",
                        help="Resume from a saved checkpoint file "
                             "(e.g. neat_checkpoints/neat-checkpoint-49)")
    parser.add_argument("--history", action="store_true",
                        help="Print training history from the DB and exit")
    parser.add_argument("--db", default=_DB_PATH,
                        help="Path to training history SQLite DB")
    parser.add_argument("--no-parallel", action="store_true",
                        help="Disable multiprocessing (useful for debugging)")
    parser.add_argument("--workers", type=int, default=None,
                        help="Number of parallel workers (default: CPU count)")
    parser.add_argument("--viz-freq", type=int, default=0, metavar="N",
                        help="Save a topology image every N generations (0=off)")
    args = parser.parse_args()

    if args.history:
        show_history(args.db)
        return

    global GAMES_PER_GENOME
    GAMES_PER_GENOME = args.games

    if args.strong_opponents:
        _try_load_strong_opponents()

    config = neat.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        args.config,
    )

    # ── Restore or create population ─────────────────────────────────────────
    resumed_from_run = None
    start_generation = 0

    if args.resume:
        if not os.path.exists(args.resume):
            sys.exit(f"Checkpoint not found: {args.resume}")
        pop = neat.Checkpointer.restore_checkpoint(args.resume)
        start_generation = pop.generation
        # Look up the most recent DB run that produced this checkpoint
        db_con_tmp = _db_connect()
        row = db_con_tmp.execute(
            "SELECT id FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            resumed_from_run = row[0]
        db_con_tmp.close()
        print(f"Resuming from checkpoint: {args.resume}  (generation {start_generation})")
    else:
        pop = neat.Population(config)

    # ── Set up reporters ──────────────────────────────────────────────────────
    os.makedirs(_CHECKPOINT_DIR, exist_ok=True)
    checkpoint_prefix = os.path.join(_CHECKPOINT_DIR, "neat-checkpoint-")

    db_con  = _db_connect()
    run_id  = _db_start_run(db_con, args.generations, args.games,
                             config.pop_size, args.strong_opponents,
                             start_generation=start_generation,
                             resumed_from_run=resumed_from_run)

    viz_dir = os.path.join(_DIR, "neat_topology_frames") if args.viz_freq else None
    if viz_dir:
        os.makedirs(viz_dir, exist_ok=True)

    progress = _ProgressReporter(
        db_con=db_con, run_id=run_id,
        viz_freq=args.viz_freq, viz_dir=viz_dir, neat_config=config,
    )
    pop.add_reporter(progress)
    pop.add_reporter(neat.StatisticsReporter())
    pop.add_reporter(neat.Checkpointer(
        generation_interval=args.checkpoint_freq,
        filename_prefix=checkpoint_prefix,
    ))

    resume_note = f"  (resumed from gen {start_generation})" if args.resume else ""

    n_workers = 0 if args.no_parallel else (args.workers or multiprocessing.cpu_count())
    parallel_note = f"  parallel={n_workers} workers" if n_workers > 0 else "  sequential"

    print(f"\nTraining run #{run_id}  —  {args.generations} generations{resume_note}  "
          f"({args.games} games/genome, pop={config.pop_size},{parallel_note})\n")
    print(f"  Checkpoints every {args.checkpoint_freq} gens → {_CHECKPOINT_DIR}/")
    print(f"  {'Gen':>3}  {'best':>6}  {'mean':>5}  {'Δbest':>7}  "
          f"{'species':>7}  {'nodes':>5}  {'conns':>5}  {'last 20 gens':>22}  time")
    print(f"  {'-'*88}")

    global _POOL
    if n_workers > 0:
        ctx = multiprocessing.get_context("fork")
        _POOL = ctx.Pool(
            processes=n_workers,
            initializer=_worker_init,
            initargs=(args.games, args.strong_opponents),
        )

    try:
        winner = pop.run(eval_genomes, args.generations)
    finally:
        if _POOL is not None:
            _POOL.close()
            _POOL.join()
            _POOL = None

    with open(args.out, "wb") as f:
        pickle.dump(winner, f)

    bench_neat_avg, bench_opp_avg, bench_opp_label = _benchmark(winner, config)
    _db_finish_run(db_con, run_id, winner.fitness,
                   len(winner.nodes), len(winner.connections),
                   bench_neat_avg, bench_opp_avg, bench_opp_label)
    db_con.close()

    print(f"\n{'─'*60}")
    print(f"Best genome saved   → {args.out}")
    print(f"Best fitness        :  {winner.fitness:.2f} avg coins/game")
    print(f"Network size        :  {len(winner.nodes)} nodes, {len(winner.connections)} connections")
    print(f"Improvement         :  {winner.fitness - progress.best_hist[0]:+.2f} coins vs this chunk")
    print(f"Checkpoints         → {_CHECKPOINT_DIR}/")
    print(f"History DB          → {args.db}")
    print(f"\nTo continue training:")
    latest_ckpt = max(
        (f for f in os.listdir(_CHECKPOINT_DIR) if f.startswith("neat-checkpoint-")),
        key=lambda f: int(f.split("-")[-1]),
        default=None,
    )
    if latest_ckpt:
        print(f"  python train_neat.py --resume {os.path.join(_CHECKPOINT_DIR, latest_ckpt)} "
              f"--generations {args.generations} --games {args.games}"
              + (" --strong-opponents" if args.strong_opponents else ""))

    plot_path = os.path.splitext(args.out)[0] + "_fitness.png"
    _plot_fitness(progress.best_hist, progress.mean_hist, plot_path)

    try:
        from neat_viz import draw_topology
        topo_path = os.path.splitext(args.out)[0] + "_topology.png"
        draw_topology(
            winner, config, topo_path,
            title=f"run #{run_id}  gen {start_generation}–{start_generation+args.generations-1}"
                  f"  best={winner.fitness:.2f}",
        )
    except Exception as e:
        print(f"[neat_viz] final topology skipped: {e}")


if __name__ == "__main__":
    main()
