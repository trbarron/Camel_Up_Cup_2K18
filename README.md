# Camel Up Cup

A Python simulation of [Camel Up](https://boardgamegeek.com/boardgame/153938/camel-up), the board game, designed for bot competition. Write a bot, drop it in, and see how it fares against the field.

## How It Works

Bots are shuffled into random 4-player games, scores accumulate across many games, and standings are printed periodically. Each game, players take turns choosing one of five actions:

| Action | Return value | Description |
|---|---|---|
| Move camel | `[0]` | Roll the dice — moves a random camel 1–3 spaces and earns 1 coin |
| Place/move trap | `[1, trap_type, position]` | Place a +1 or -1 trap on the track; earn 1 coin each time a camel hits it |
| Round winner bet | `[2, camel]` | Bet on which camel leads at end of the round; pays 5/3/2 coins or -1 |
| Game winner bet | `[3, camel]` | Bet on the overall game winner; pays 8/5/3/1 coins or -1 |
| Game loser bet | `[4, camel]` | Bet on the overall game loser; pays 8/5/3/1 coins or -1 |

### Game Rules

- **Track**: 16 spaces to the finish line. First camel to cross wins.
- **Camels**: 5 camels (0–4), each starting randomly in spaces 0–2.
- **Stacking**: Camels stack on top of each other. When a camel moves, all camels on top of it move with it.
- **Traps**: `+1` traps boost a camel one extra space; `-1` traps send it one space back and place it *under* the stack at that square.
- **Rounds**: A round ends when all 5 camels have moved once. Round bets and traps are cleared; a new round begins.
- **Winning**: The player with the most coins when any camel crosses space 16 wins.

## Adding a Bot

1. Create a new file, e.g. `MyBot.py`:

```python
from playerinterface import PlayerInterface

class MyBot(PlayerInterface):
    def move(player, g):
        # player: your player index (0–3)
        # g: a deep copy of the current GameState
        return [0]  # always roll the dice
```

2. Import and register your bot. For the basic runner, add it to `camelup.py`:

```python
from MyBot import MyBot

player_pool = [Player0, Player1, Player2, Sir_Humpfree_Bogart, MyBot]
```

For the tournament runner (`tournament.py`), import your bot and add it to `_KNOWN_BOTS`:

```python
from MyBot import MyBot

_KNOWN_BOTS = [
    # ... existing bots ...
    ("MyBot", MyBot),
]
```

That's it. The tournament loop handles the rest.

### What Your Bot Receives

Your `move(player, g)` method receives:

- `player` — your seat index (0–3) for this game
- `g` — a **deep copy** of the current `GameState`

### GameState Fields

```python
g.camel_track             # list of 29 lists; each inner list is a stack of camel IDs (bottom to top)
g.trap_track              # list of 29 lists; each entry is [trap_type, player] or []
g.player_has_placed_trap  # [bool x4] — whether each player has an active trap
g.round_bets              # list of [camel, player] for this round's bets
g.game_winner_bets        # list of [hashed_camel, player] — game winner bets (hashed!)
g.game_loser_bets         # list of [hashed_camel, player] — game loser bets (hashed!)
g.player_game_bets        # [[hashed_camel, ...] x4] — each player's game-level bet hashes
g.player_money_values     # [int x4] — current coin totals
g.camel_yet_to_move       # [bool x5] — which camels haven't moved this round
g.camels                  # [0, 1, 2, 3, 4]
```

### Fair Play: What You Can and Can't Use

The game state is a deep copy, so you can mutate it freely for simulation purposes. However, there are rules about what information your bot should access:

**Fair game (use freely):**
- `g.camel_track` — full board state, camel positions and stacking order
- `g.trap_track` — all trap positions and types (public information)
- `g.player_has_placed_trap` — who has an active trap
- `g.round_bets` — all round bets placed so far (these are public in the board game)
- `g.player_money_values` — everyone's coin totals
- `g.camel_yet_to_move` — which camels still need to roll this round
- `g.camels` — the list of camel IDs
- `g.player_game_bets[player]` — **your own** game-level bet hashes (to check what you've already bet on)
- `len(g.game_winner_bets)` / `len(g.game_loser_bets)` — how many total game bets have been placed (public count)

**Off limits (don't crack or read):**
- `g.game_winner_bets` / `g.game_loser_bets` contents — these are hashed specifically so bots can't see which camels other players bet on. You can see the count and which player placed each bet, but **do not** attempt to brute-force the hashes to reveal opponents' camel choices. In the real board game these bets are placed face-down.
- `g.player_game_bets[other_player]` — other players' game bet hashes. Only inspect your own (`g.player_game_bets[player]`).

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

- Traps cannot be placed on space 0
- Traps cannot be placed adjacent to another trap (unless it's your own being moved)
- Traps cannot be placed on a space with camels on it
- Each player can only have one trap on the board at a time
- `trap_type` must be `1` (boost: +1 space) or `-1` (slow: -1 space, stack underneath)

### Return Value

Your `move()` must return one of:

```python
[0]                    # Roll the dice
[1, trap_type, pos]    # Place/move trap (trap_type: 1 or -1, pos: track position)
[2, camel]             # Round winner bet (camel: 0–4)
[3, camel]             # Game winner bet (camel: 0–4)
[4, camel]             # Game loser bet (camel: 0–4)
```

If your bot crashes or returns an invalid action, the tournament runner falls back to rolling the dice.

## Existing Bots

| Bot | Strategy |
|---|---|
| `Player0` | Always rolls the dice |
| `Player1` | Bets on a random round winner if losing, otherwise places a random trap |
| `Player2` | Always bets on a random round winner |
| `Sir_Humpfree_Bogart` | Enumerates all possible camel move outcomes for round predictions, runs Monte Carlo simulations for game-level predictions, and adjusts risk tolerance based on standing and proximity to the finish line |
| `ClaudeCamel` | LLM-refactored version of Sir_Humpfree_Bogart. Fixes several bugs (stale track reference in MC sims, camel bank aliasing), removes the riskiness heuristic in favor of pure EV maximization, and adds performance optimizations (precomputed position maps, bulk dice generation) |
| `OpusOmul` | Built from scratch by an LLM with no knowledge of existing bot strategies. Uses the same core approach (round enumeration + Monte Carlo game sims) but arrived at it independently. Also evaluates trap placement by estimating landing frequency per space |
| `GeminiGerry` | Monte Carlo simulation bot that uses `copy.deepcopy` for game sims, biases slightly toward action over rolling, and requires a confidence threshold (>25% win probability) before placing game-level bets |

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

### Requirements

- Python 3
- `rich` (for `tournament.py` only)
