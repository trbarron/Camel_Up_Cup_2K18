#!/usr/bin/env python3
"""
tournament.py — Camel Up Cup tournament runner with Rich CLI and profiling.

Usage:
    python tournament.py                              # 100 games, all bots
    python tournament.py --games 50                   # custom game count
    python tournament.py --profile ClaudeCamel        # cProfile a bot's moves
    python tournament.py --profile-top 20             # top N hotspots in report
    python tournament.py --players ClaudeCamel Sir_Humpfree Player0 Player1

Dependencies:
    pip install rich
"""

import argparse
import cProfile
import copy
import io
import pstats
import random
import time
from collections import defaultdict
from statistics import mean, median, stdev

from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich import box

try:
    from rich.console import Group
except ImportError:
    from rich.console import RenderGroup as Group  # rich < 12 compat

from camelup import (
    GameState,
    MoveCamel, PlaceTrap, MoveTrap,
    PlaceRoundWinnerBet, PlaceGameWinnerBet, PlaceGameLoserBet,
)
from players import Player0, Player1, Player2
from Sir_Humpfree_Bogart import Sir_Humpfree_Bogart
from ClaudeCamel import ClaudeCamel
from GeminiGerry import GeminiGerry
from OpusOmul import OpusOmul
from TrainingOpponent import TrainingOpponent
try:
    from NeatCamel import NeatCamel
except Exception:
    NeatCamel = None

# ── Registry ──────────────────────────────────────────────────────────────────
# Any bot whose file doesn't exist yet is silently excluded at runtime.

def _try_import(module, cls):
    try:
        return getattr(__import__(module), cls)
    except (ImportError, AttributeError):
        return None

_KNOWN_BOTS = [
    ("Player0",      Player0),
    ("Player1",      Player1),
    ("Player2",      Player2),
    ("Sir_Humpfree", Sir_Humpfree_Bogart),
    ("ClaudeCamel",  ClaudeCamel),
    ("GeminiGerry",  GeminiGerry),
    ("OpusOmul",         OpusOmul),
    ("TrainingOpponent", TrainingOpponent),
    ("NeatCamel",        NeatCamel),
]

BOT_REGISTRY = {name: cls for name, cls in _KNOWN_BOTS if cls is not None}

BOT_COLORS = {
    "Player0":      "cyan",
    "Player1":      "green",
    "Player2":      "yellow",
    "Sir_Humpfree": "magenta",
    "ClaudeCamel":  "bold red",
    "OpusOmul":     "bright_blue",
    "GeminiGerry":  "bright_green",
    "NeatCamel":    "bold magenta",
}

ACTION_KEYS   = ["roll", "round_bet", "game_win", "game_lose", "trap"]
ACTION_LABELS = ["Roll", "Round Bet", "Game Win", "Game Lose", "Trap"]
ACTION_MAP    = {0: "roll", 1: "trap", 2: "round_bet", 3: "game_win", 4: "game_lose"}

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

        g_snap = copy.deepcopy(g)

        if profile_name and name == profile_name:
            pr = cProfile.Profile()
            pr.enable()
            t0     = time.perf_counter()
            result = bot.move(seat, g_snap)
            ms     = (time.perf_counter() - t0) * 1000
            pr.disable()
            new_ps = pstats.Stats(pr)
            if stats[name]["profile"] is None:
                stats[name]["profile"] = new_ps
            else:
                stats[name]["profile"].add(new_ps)
        else:
            t0     = time.perf_counter()
            result = bot.move(seat, g_snap)
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


# ── Rich tables ────────────────────────────────────────────────────────────────

def _colored(name):
    c = BOT_COLORS.get(name, "white")
    return f"[{c}]{name}[/{c}]"


def leaderboard_table(stats):
    t = Table(box=box.ROUNDED, expand=True, header_style="bold dim", show_lines=False)
    t.add_column("Rank",      justify="center", width=6)
    t.add_column("Bot",       min_width=16)
    t.add_column("Wins",      justify="right")
    t.add_column("Games",     justify="right")
    t.add_column("Win %",     justify="right")
    t.add_column("Avg Coins", justify="right")
    t.add_column("Avg ms",    justify="right")
    t.add_column("Max ms",    justify="right")

    ranked = sorted(stats.items(), key=lambda kv: kv[1]["wins"], reverse=True)
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for rank, (name, s) in enumerate(ranked, 1):
        g   = s["games"]
        ms  = s["times_ms"]
        t.add_row(
            medals.get(rank, f" {rank} "),
            _colored(name),
            f"{s['wins']:.1f}",
            str(g),
            f"{100 * s['wins'] / g:.1f}%" if g else "—",
            f"{s['coins_total'] / g:.1f}"  if g else "—",
            f"{mean(ms):.0f}"              if ms else "—",
            f"{max(ms):.0f}"               if ms else "—",
        )
    return t


def action_table(stats):
    t = Table(box=box.SIMPLE, expand=True, header_style="bold dim")
    t.add_column("Bot", min_width=16)
    for lbl in ACTION_LABELS:
        t.add_column(lbl, justify="right")

    for name, s in sorted(stats.items(), key=lambda kv: -kv[1]["wins"]):
        total = sum(s["actions"].values())
        if not total:
            continue
        t.add_row(
            _colored(name),
            *[f"{100 * s['actions'].get(k, 0) / total:.0f}%" for k in ACTION_KEYS],
        )
    return t


def seat_table(seat_stats):
    t = Table(box=box.ROUNDED, expand=True, header_style="bold dim")
    t.add_column("Seat",      justify="center", width=6)
    t.add_column("Goes",      min_width=10)
    t.add_column("Wins",      justify="right")
    t.add_column("Games",     justify="right")
    t.add_column("Win %",     justify="right")
    t.add_column("Avg Coins", justify="right")

    labels = ["1st", "2nd", "3rd", "4th"]
    for seat in range(4):
        s = seat_stats[seat]
        g = s["games"]
        t.add_row(
            str(seat),
            labels[seat],
            f"{s['wins']:.1f}",
            str(g),
            f"{100 * s['wins'] / g:.1f}%" if g else "—",
            f"{s['coins_total'] / g:.1f}"  if g else "—",
        )
    return t


def timing_table(stats):
    t = Table(box=box.ROUNDED, expand=True, header_style="bold dim")
    t.add_column("Bot",       min_width=16)
    t.add_column("Moves",     justify="right")
    t.add_column("Min ms",    justify="right")
    t.add_column("Mean ms",   justify="right")
    t.add_column("Median ms", justify="right")
    t.add_column("Max ms",    justify="right")
    t.add_column("σ ms",      justify="right")

    for name, s in sorted(stats.items(), key=lambda kv: -kv[1]["wins"]):
        ms = s["times_ms"]
        if not ms:
            continue
        t.add_row(
            _colored(name),
            str(len(ms)),
            f"{min(ms):.1f}",
            f"{mean(ms):.1f}",
            f"{median(ms):.1f}",
            f"{max(ms):.1f}",
            f"{stdev(ms):.1f}" if len(ms) > 1 else "—",
        )
    return t


# ── Live display ───────────────────────────────────────────────────────────────

def build_display(stats, done, total, recent, t_start):
    elapsed = time.time() - t_start
    w       = 40
    filled  = int(w * done / total) if total else 0
    bar     = f"[green]{'█' * filled}[/green][dim]{'░' * (w - filled)}[/dim]"
    prog    = Text.from_markup(
        f"  {bar}  {done}/{total}  [dim]{elapsed:.1f}s elapsed[/dim]"
    )

    recent_lines = "\n".join(
        f"  [dim]#{r['num']:>3}[/dim]  "
        f"[bold]{' & '.join(r['winners'])}[/bold]"
        f"  [dim]({r['turns']} turns)[/dim]"
        for r in reversed(recent[-6:])
    ) or "  [dim]—[/dim]"

    return Group(
        Panel(prog, title="[bold white]Camel Up Cup Tournament[/bold white]", box=box.ROUNDED),
        Panel(leaderboard_table(stats),  title="[bold]Leaderboard[/bold]",        box=box.ROUNDED, padding=(0, 1)),
        Panel(action_table(stats),       title="[bold]Action Distribution[/bold]", box=box.ROUNDED, padding=(0, 1)),
        Panel(recent_lines,              title="[bold]Recent Games[/bold]",        box=box.ROUNDED),
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Camel Up Cup tournament runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--games",       type=int, default=100,
                        help="Number of games to simulate")
    parser.add_argument("--profile",     metavar="BOT", default=None,
                        choices=list(BOT_REGISTRY.keys()),
                        help="Bot to run under cProfile")
    parser.add_argument("--profile-top", type=int, default=15,
                        help="Top N functions to show in cProfile report")
    parser.add_argument("--players",     nargs="+", metavar="BOT",
                        choices=list(BOT_REGISTRY.keys()), default=None,
                        help="Subset of bots to include (default: all)")
    args = parser.parse_args()

    selected = args.players or list(BOT_REGISTRY.keys())
    bots     = [BOT_REGISTRY[n] for n in selected]

    if len(bots) < 2:
        Console().print("[bold red]Need at least 2 bots.[/bold red]")
        return

    stats      = init_stats(selected)
    seat_stats = {i: {"wins": 0.0, "games": 0, "coins_total": 0} for i in range(4)}
    recent     = []
    t_start    = time.time()

    with Live(
        build_display(stats, 0, args.games, recent, t_start),
        refresh_per_second=4,
        screen=False,
    ) as live:
        for game_num in range(1, args.games + 1):
            winners, turns = run_game(bots, selected, stats, seat_stats, profile_name=args.profile)
            recent.append({"num": game_num, "winners": winners, "turns": turns})
            live.update(build_display(stats, game_num, args.games, recent, t_start))

    # ── Final report ──────────────────────────────────────────────────────────
    console = Console()
    console.print()

    # Champion banner
    top_name, top_s = max(stats.items(), key=lambda kv: kv[1]["wins"])
    g = top_s["games"]
    console.print(Panel(
        f"  [bold]{_colored(top_name)}[/bold]  "
        f"[white]{top_s['wins']} wins  "
        f"({100 * top_s['wins'] / g:.1f}%  over {g} games)[/white]",
        title="[bold yellow]🏆  Tournament Champion[/bold yellow]",
        box=box.DOUBLE,
    ))

    console.print()
    console.print(Rule("[bold white]Leaderboard[/bold white]"))
    console.print(leaderboard_table(stats))

    console.print()
    console.print(Rule("[bold white]Action Distribution[/bold white]"))
    console.print(action_table(stats))

    console.print()
    console.print(Rule("[bold white]Seat Order Advantage[/bold white]"))
    console.print(seat_table(seat_stats))

    console.print()
    console.print(Rule("[bold white]Move Timing[/bold white]"))
    console.print(timing_table(stats))

    # cProfile report
    if args.profile:
        ps = stats[args.profile]["profile"]
        if ps is not None:
            console.print()
            console.print(Rule(f"[bold white]cProfile — {args.profile}[/bold white]"))
            buf = io.StringIO()
            ps.stream = buf
            ps.sort_stats("cumulative")
            ps.print_stats(args.profile_top)
            console.print(Panel(
                buf.getvalue().strip(),
                title=f"[bold]Top {args.profile_top} functions by cumulative time[/bold]",
                box=box.ROUNDED,
            ))
        else:
            console.print(f"\n[yellow]{args.profile} never played — no profile data.[/yellow]")


if __name__ == "__main__":
    main()
