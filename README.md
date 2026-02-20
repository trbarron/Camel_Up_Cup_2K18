# Camel Up Cup

A Python simulation of [Camel Up](https://boardgamegeek.com/boardgame/153938/camel-up), the board game, designed for bot competition. Write a bot, drop it in, and see how it fares against the field.

## How It Works

`camelup.py` runs a tournament: bots are shuffled into random 4-player games, scores accumulate across many games, and standings are printed every 10 games. The number of games scales with the player pool size.

Each game, players take turns choosing one of five actions:

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

### GameState Fields

Your bot receives a deep copy of the `GameState` object each turn:

```python
g.camel_track          # list of 29 lists; each inner list is a stack of camel IDs (bottom to top)
g.trap_track           # list of 29 lists; each entry is [trap_type, player] or []
g.player_has_placed_trap  # [bool x4] — whether each player has an active trap
g.round_bets           # list of [camel, player] for this round's bets
g.game_winner_bets     # list of [hashed_camel, player] for game winner bets
g.game_loser_bets      # list of [hashed_camel, player] for game loser bets
g.player_game_bets     # [[hashed_camel, ...] x4] — your own game bets (for dupe checking)
g.player_money_values  # [int x4] — current coin totals
g.camel_yet_to_move    # [bool x5] — which camels haven't moved this round
g.camels               # [0, 1, 2, 3, 4]
```

> Note: Game winner/loser bets are hashed to prevent bots from reading opponents' hidden bets. Use `g.player_game_bets[player]` to check your own bets only.

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

2. Import and add your bot to `camelup.py`:

```python
from MyBot import MyBot

player_pool = [Player0, Player1, Player2, Sir_Humpfree_Bogart, MyBot]
```

That's it. The tournament loop handles the rest.

## Existing Bots

| Bot | Strategy |
|---|---|
| `Player0` | Always rolls the dice |
| `Player1` | Bets on a random round winner if losing, otherwise places a random trap |
| `Player2` | Always bets on a random round winner |
| `Sir_Humpfree_Bogart` | Enumerates all possible camel move outcomes, runs Monte Carlo simulations for game-level predictions, and picks the highest expected-value action with a risk tolerance that scales with desperation and proximity to the finish |

## Running

```bash
python camelup.py
```

Requires Python 3. No external dependencies.
