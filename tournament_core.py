"""
tournament_core.py — dependency-free tournament internals.

Everything needed to run games and collect stats programmatically, with no
CLI/display dependencies (tournament.py layers Rich on top of this; the
Lambda runner imports this directly so `rich` never needs to be installed).
"""

import cProfile
import pstats
import random
import time
from collections import defaultdict

from camelup import (
    GameState, player_view,
    MoveCamel, PlaceTrap, MoveTrap,
    PlaceRoundWinnerBet, PlaceGameWinnerBet, PlaceGameLoserBet,
)

ACTION_MAP = {0: "roll", 1: "trap", 2: "round_bet", 3: "game_win", 4: "game_lose"}

# ── Registry ──────────────────────────────────────────────────────────────────
# House bots carry a "tb-" prefix. Submitted bot names can't contain hyphens
# (site + lambda validation), so the prefix can't be impersonated.

from bots.players import Player0, Player1, Player2
from bots.HandcodedHenry import HandcodedHenry
from bots.ClaudeCamel import ClaudeCamel
from bots.GeminiGerry import GeminiGerry
from bots.OpusOmul import OpusOmul
from bots.FabelFelix import FabelFelix

_KNOWN_BOTS = [
    ("tb-Player0",        Player0),
    ("tb-Player1",        Player1),
    ("tb-Player2",        Player2),
    ("tb-HandcodedHenry", HandcodedHenry),
    ("tb-ClaudeCamel",    ClaudeCamel),
    ("tb-GeminiGerry",    GeminiGerry),
    ("tb-OpusOmul",       OpusOmul),
    ("tb-FabelFelix",     FabelFelix),
]

BOT_REGISTRY = {name: cls for name, cls in _KNOWN_BOTS if cls is not None}

# Provenance shown on the tylerbarron.com leaderboard. Mirrors the frontmatter
# comment at the top of each bot file.
BOT_INFO = {
    "tb-Player0":        {"author": "Tyler Barron", "model": None, "note": "Hand-coded baseline: always rolls", "year": 2018},
    "tb-Player1":        {"author": "Tyler Barron", "model": None, "note": "Hand-coded baseline: bets and traps", "year": 2018},
    "tb-Player2":        {"author": "Tyler Barron", "model": None, "note": "Hand-coded baseline", "year": 2018},
    "tb-HandcodedHenry": {"author": "Tyler Barron", "model": None, "note": "Hand-coded; won the original Cup as Sir_Humpfree_Bogart", "year": 2018},
    "tb-ClaudeCamel":    {"author": "Tyler Barron", "model": "Claude Sonnet", "note": None, "year": 2026},
    "tb-GeminiGerry":    {"author": "Tyler Barron", "model": "Gemini", "note": None, "year": 2026},
    "tb-OpusOmul":       {"author": "Tyler Barron", "model": "Claude Opus", "note": None, "year": 2026},
    "tb-FabelFelix":     {"author": "Tyler Barron", "model": "Claude Fable 5", "note": None, "year": 2026},
}

# ── Stats ─────────────────────────────────────────────────────────────────────

def init_stats(names):
    return {
        name: {
            "wins":        0.0,   # fractional: ties split evenly
            "games":       0,
            "coins_total": 0,
            "times_ms":    [],
            "actions":     defaultdict(int),
            "profile":     None,    # pstats.Stats or None
        }
        for name in names
    }

# ── Game execution ─────────────────────────────────────────────────────────────

def _take_action(result, seat, g):
    """Apply a player decision to the live game state. Falls back to roll on error."""
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


def run_game(bots, names, stats, seat_stats, profile_name=None):
    """
    Play one complete game. Updates `stats` and `seat_stats` in place.
    Returns (list[winner_name], num_turns).
    """
    n = len(bots)
    idx        = random.sample(range(n), 4) if n >= 4 else [random.randrange(n) for _ in range(4)]
    game_bots  = [bots[i]  for i in idx]
    game_names = [names[i] for i in idx]

    g    = GameState()
    turn = 0

    while g.active_game:
        seat = turn % 4
        bot  = game_bots[seat]
        name = game_names[seat]

        g_snap = player_view(g, seat)

        if profile_name and name == profile_name:
            pr = cProfile.Profile()
            pr.enable()
            t0     = time.perf_counter()
            try:
                result = bot.move(seat, g_snap)
            except Exception:
                result = [0]
            ms     = (time.perf_counter() - t0) * 1000
            pr.disable()
            new_ps = pstats.Stats(pr)
            if stats[name]["profile"] is None:
                stats[name]["profile"] = new_ps
            else:
                stats[name]["profile"].add(new_ps)
        else:
            t0     = time.perf_counter()
            try:
                result = bot.move(seat, g_snap)
            except Exception:
                result = [0]
            ms     = (time.perf_counter() - t0) * 1000

        stats[name]["times_ms"].append(ms)
        stats[name]["actions"][ACTION_MAP.get(result[0], "unknown")] += 1

        _take_action(result, seat, g)
        turn += 1

    max_coins = max(g.player_money_values)
    winners   = [i for i, c in enumerate(g.player_money_values) if c == max_coins]

    for seat, name in enumerate(game_names):
        stats[name]["games"]       += 1
        stats[name]["coins_total"] += g.player_money_values[seat]
        seat_stats[seat]["games"]  += 1
        seat_stats[seat]["coins_total"] += g.player_money_values[seat]
        if seat in winners:
            share = 1 / len(winners)
            stats[name]["wins"]       += share
            seat_stats[seat]["wins"]  += share

    return [game_names[w] for w in winners], turn
