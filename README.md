# Camel Up Cup

A Python simulation of [Camel Up](https://boardgamegeek.com/boardgame/153938/camel-up), the board game, designed for bot competition. Write a bot, drop it in, and see how it fares against the field.

## How It Works

Bots are shuffled into random 4-player games, scores accumulate across many games, and standings are printed periodically. Each game, players take turns choosing one of five actions:

| Action | Return value | Description |
|---|---|---|
| Move camel | `[0]` | Roll the dice — moves a random camel 1–3 spaces and earns 1 coin |
| Place/move trap | `[1, trap_type, position]` | Place a +1 or -1 trap on the track; earn 1 coin each time a camel hits it |
| Round winner bet | `[2, camel]` | Bet on which camel leads at end of the round; pays 5/3/2 (first), 1 (second), -1 otherwise |
| Game winner bet | `[3, camel]` | Bet on the overall game winner; pays 8/5/3/1 coins or -1 |
| Game loser bet | `[4, camel]` | Bet on the overall game loser; pays 8/5/3/1 coins or -1 |

### Game Rules

- **Track**: 16 spaces to the finish line. First camel to cross wins.
- **Camels**: 5 camels (0–4), each starting randomly in spaces 0–2.
- **Stacking**: Camels stack on top of each other. When a camel moves, all camels on top of it move with it.
- **Traps**: `+1` traps boost a camel one extra space; `-1` traps send it one space back and place it *under* the stack at that square.
- **Rounds**: A round ends when all 5 camels have moved once. Round bets and traps are cleared; a new round begins.
- **Bet settlement**: Bets settle in the order they were placed. Round bets on the leading camel pay 5/3/2 down the ladder (0 after that); bets on the runner-up pay 1 (first three); every other round bet costs 1 coin. Game winner/loser bets pay 8/5/3/1 down the ladder (1 after that) or -1 if wrong.
- **Winning**: The player with the most coins when any camel crosses space 16 wins.

## Repository layout

Bots live in three folders by role (see [`bots/README.md`](bots/README.md) for
the full contract):

- `bots/house/` — the Cup's standing opponents (checked in).
- `bots/test/` — smoke-test baselines, `Player0/1/2` (checked in).
- `bots/contenders/` — the private competitive lab (**gitignored**, never deployed).

`tournament_core.py` imports house + test explicitly and **discovers** contenders
dynamically, so a clean clone (and the Lambda) runs the house roster with no
contenders present. Scratch experiment scripts live in `lab/` (also gitignored).

## Adding a Bot

1. Create a new file in `bots/contenders/`, e.g. `bots/contenders/MyBot.py`:

```python
from playerinterface import PlayerInterface

class MyBot(PlayerInterface):
    def move(player, g):
        # player: your player index (0–3)
        # g: a deep copy of the current GameState
        return [0]  # always roll the dice
```

2. That's it — no registration needed. `tournament_core` discovers the file and
   registers it as `tb-MyBot` (the class it defines). It shows up automatically
   in `tournament.py` and the paired-seed evaluator.

To pit it against the house roster in the basic runner, import it under the
`__main__` guard in `camelup.py`:

```python
from bots.contenders.MyBot import MyBot
player_pool = [Player0, HandcodedHenry, MyBot]
```

### What Your Bot Receives

Your `move(player, g)` method receives:

- `player` — your seat index (0–3) for this game
- `g` — a **deep copy** of the current `GameState`

### GameState Fields

```python
g.camel_track             # list of 29 lists; each inner list is a stack of camel IDs (bottom to top)
g.trap_track              # list of 29 lists; each entry is [trap_type, player] or []
g.player_has_placed_trap  # [bool x4] — whether each player has an active trap
g.round_bets              # list of [camel, player] for this round's bets (public)
g.game_winner_bets        # list of [hashed_camel, player]; opponents' entries are [None, player]
g.game_loser_bets         # list of [hashed_camel, player]; opponents' entries are [None, player]
g.player_game_bets        # [[hashed_camel, ...] x4]; other players' rows contain None placeholders
g.player_money_values     # [int x4] — current coin totals
g.camel_yet_to_move       # [bool x5] — which camels haven't moved this round
g.camels                  # [0, 1, 2, 3, 4]
```

### What Your Bot Can See

Your bot receives a **redacted view** of the game state (built by `camelup.player_view`), so hidden information is enforced by the engine rather than by an honor system. The view is a deep copy — mutate it freely for simulation purposes.

**Public (use freely):**
- `g.camel_track` — full board state, camel positions and stacking order
- `g.trap_track` — all trap positions and types
- `g.player_has_placed_trap` — who has an active trap
- `g.round_bets` — all round bets placed so far (public in the board game)
- `g.player_money_values` — everyone's coin totals
- `g.camel_yet_to_move` — which camels still need to roll this round
- `g.camels` — the list of camel IDs
- Bet counts and who placed each game bet (`len(g.game_winner_bets)`, the player field of each entry)

**Hidden (redacted by the engine — you can't read these even if you try):**
- Opponents' game-bet camel choices. Entries in `g.game_winner_bets` / `g.game_loser_bets` placed by other players appear as `[None, player]`, and `g.player_game_bets[other_player]` contains only `None` placeholders. In the real board game these bets are placed face-down.
- Your own game bets are present but hashed; decode them with the `check_bet` pattern below.

To check which camels you've already bet on, use the `check_bet` pattern:

```python
import hashlib

def check_bet(hashed_bet, user_bet):
    bet, salt = hashed_bet.split(':')
    return bet == hashlib.sha256(salt.encode() + user_bet.encode()).hexdigest()

# Check your own bets
already_bet = set()
for hb in g.player_game_bets[player]:
    for c in range(5):
        if check_bet(hb, str(c)):
            already_bet.add(c)
            break
```

### Trap Placement Rules

All of these are enforced by the engine (an illegal placement counts as an invalid action, and your turn becomes a dice roll):

- Traps cannot be placed on space 0
- Traps cannot be placed adjacent to another trap (unless it's your own being moved)
- Traps cannot be placed on a space with camels on it
- Each player can only have one trap on the board at a time
- `trap_type` must be `1` (boost: +1 space) or `-1` (slow: -1 space, the hit camel and its riders go under the stack on the destination square)

### Return Value

Your `move()` must return one of:

```python
[0]                    # Roll the dice
[1, trap_type, pos]    # Place/move trap (trap_type: 1 or -1, pos: track position)
[2, camel]             # Round winner bet (camel: 0–4)
[3, camel]             # Game winner bet (camel: 0–4)
[4, camel]             # Game loser bet (camel: 0–4)
```

If your bot crashes or returns an invalid action, your turn becomes a dice roll (both runners).

## Existing Bots

| Bot | Strategy |
|---|---|
| `Player0` | Always rolls the dice |
| `Player1` | Bets on a random round winner if losing, otherwise places a random trap |
| `Player2` | Always bets on a random round winner |
| `HandcodedHenry` (fka `Sir_Humpfree_Bogart`, 2018) | Enumerates all possible camel move outcomes for round predictions, runs Monte Carlo simulations for game-level predictions, and adjusts risk tolerance based on standing and proximity to the finish line |
| `ClaudeCamel` | LLM-refactored version of HandcodedHenry. Fixes several bugs (stale track reference in MC sims, camel bank aliasing), removes the riskiness heuristic in favor of pure EV maximization, and adds performance optimizations (precomputed position maps, bulk dice generation) |
| `OpusOmul` | Built from scratch by an LLM with no knowledge of existing bot strategies. Uses the same core approach (round enumeration + Monte Carlo game sims) but arrived at it independently. Also evaluates trap placement by estimating landing frequency per space |
| `GeminiGerry` | Monte Carlo simulation bot that uses `copy.deepcopy` for game sims, biases slightly toward action over rolling, and requires a confidence threshold (>25% win probability) before placing game-level bets |
| `FabelFelix` (fka `FableCamel`) | Exact enumeration of every way the current round can finish (with state merging), Monte Carlo game sims, settlement-order-aware bet pricing, trap placement valued by the EV shift for itself minus a threat-weighted shift for opponents, and a risk posture that chases variance when trailing late and locks in coins when leading |
| `PairedPaul` | FabelFelix with the risk heuristic replaced by a direct P(win) objective: models each opponent's final coin gap as a normal distribution and scores every action by the probability of finishing with the most coins. Named for the paired-seed evaluation harness that gates its changes. Rejected across three revisions (see `EXPERIMENTS.md`) |
| `BetReader` | FabelFelix + hidden game-bet inference: reconstructs opponents' face-down game bets from the public order and timing of placements (cross-turn memory), then prices its own bet-ladder slot exactly and weights opponent threats by their inferred bet equity. Positive at all 5 evaluation seeds |
| `TrapAware` | FabelFelix + future opponent traps modeled in the Monte Carlo game sims, correcting a shared bias (every bot assumes no traps are ever placed again). ~Neutral on its own |
| `BetTrapReader` 👑 | **Current champion.** BetReader + TrapAware combined. Promoted 2026-07-03 on pooled paired-seed evidence: ~+2pp over FabelFelix, with every bet-inference run in the campaign finishing positive |
| `PacedPete`, `ParityPeggy`, `TrapDenyDana`, `BetReaderV2` | Experimental one-mechanism variants (income-rate pacing, round-end parity, trap-shadow denial, negative-information inference) — see `DESIGN.md` and `EXPERIMENTS.md` for designs and verdicts |

## Running

### Basic runner

```bash
python camelup.py
```

### Tournament runner (recommended)

```bash
python tournament.py                                  # 100 games, all bots
python tournament.py --games 500                      # custom game count
python tournament.py --profile ClaudeCamel            # cProfile a specific bot
python tournament.py --profile-top 20                 # top N hotspots in profile
python tournament.py --players ClaudeCamel OpusOmul Player0  # subset of bots
```

The tournament runner requires `rich` (`pip install rich`) and provides a live leaderboard, action distribution, seat-order analysis, and move timing stats.

### Paired-seed evaluation (A/B testing bots)

Camel Up is high-luck: real skill differences between good bots are a few
percentage points of win rate, invisible over hundreds of independent games.
`lab/evaluate.py` compares two bots using **common random numbers**: both play the
*same* games — same seed, seat, opponents, camel starting positions, and the
same pre-scripted dice — so the per-pair win difference cancels the shared luck.
(Run scratch tools from the repo root with the root on `PYTHONPATH`; see
[`lab/README.md`](lab/README.md).)

```bash
PYTHONPATH=. python lab/evaluate.py --candidate tb-PairedPaul --baseline tb-FabelFelix
PYTHONPATH=. python lab/evaluate.py --candidate bots/contenders/MyBot.py:MyBot --baseline tb-FabelFelix --pairs 500
PYTHONPATH=. python lab/evaluate.py --candidate tb-FabelFelix --baseline tb-FabelFelix --fixed --workers 1  # self-test: diff is exactly 0
```

Pairs run in parallel across worker processes (`--workers`, default: all cores
minus two) and the run stops early via
[SPRT](https://www.chessprogramming.org/Sequential_Probability_Ratio_Test)
once the evidence crosses a significance bound — "candidate is better by at
least `--delta` (default 3pp)" or "it isn't" — or when `--pairs` (the maximum)
is reached. Use `--fixed` to disable early stopping and `--workers 1` for a
bit-reproducible run.

Dice are synchronizable because every camel moves exactly once per round in
uniform random order — each round's move order and die values are scripted
from the seed (`ScriptedDice`), so paired games see identical camel movement
regardless of when each player rolls. The report shows each bot's win rate,
the paired difference with a 95% confidence interval, and the variance
reduction achieved versus unpaired sampling.

Background reading: [common random numbers](https://en.wikipedia.org/wiki/Variance_reduction),
[match statistics](https://www.chessprogramming.org/Match_Statistics) and
[SPRT](https://www.chessprogramming.org/Sequential_Probability_Ratio_Test)
from the chess engine testing world.

### Requirements

- Python 3
- `rich` (for `tournament.py` only)
