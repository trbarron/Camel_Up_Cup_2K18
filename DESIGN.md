# Design notes — edges for the Camel Up bot

Companion to `EXPERIMENTS.md` (results log). Worked-out designs so
implementation can proceed mechanically. Written 2026-07-02.

Framing: every bot computes the same *camel* probabilities (exactly
computable — no edge there). Remaining edges come from two places:
**statefulness** (what the history of the current game reveals that the
redacted current state doesn't) and **computation** (decision quality the
greedy 1-ply field leaves on the table). Behavioral profiling of opponents
was considered and rejected: a fixed policy can be beaten without it, and
per-bot models don't transfer to unknown Cup submissions.

What the engine redacts but history recovers:
1. WHEN each hidden game bet was placed and the board state at that moment
   → the bet's camel leaks (§1). This is the flagship stateful edge.
2. The global turn counter → exact actor sequence to game end (§3).
3. The rate at which bet-ladder slots and trap squares get claimed
   → option value of waiting vs claiming now (§4).

Everything else in the history (money decomposition, trap habits, dice)
is either already public, iid noise, or only feeds profiling — skipped.

---

## 0. Observation layer (foundation — build first)

Bots receive only current state, but class attributes persist across
`move()` calls (games run sequentially per process). Reconstruct history:

- **Game boundary**: new game iff any camel sits at a lower track position
  than last remembered (camels only move forward within a game), or memory
  is empty. Reset per-game state.
- **Action attribution**: between our consecutive calls, opponents acted
  in known seat order (`(me+1)%4, (me+2)%4, (me+3)%4`; before our first
  call of the game: seats `0..me-1`). Each seat's action is identifiable
  from public diffs: new `round_bets` entries carry the player; new game
  bet entries carry the player and preserve order; `trap_track` diffs
  carry the owner; a seat with none of those rolled. (The engine's
  invalid-action fallback registers as a roll — correct, it was one.)
- **State snapshots**: keep last seen `camel_track` and bet-list lengths;
  camel-track diffs identify which camels moved between our turns.

```python
_MEM = {
    "track": None,          # last seen camel_track
    "turn": 0,              # our call counter this game
    "n_gw": 0, "n_gl": 0,   # game-bet list lengths last seen
    "bet_beliefs": [],      # per hidden bet: {"player","kind","belief"}
}
```
Microseconds per turn. Unit-test the attribution against scripted games
(harness has ground truth).

---

## 1. Hidden game-bet inference (statefulness edge #1 — highest priority)

Not profiling: assumes only that opponents bet camels they currently
believe in, which holds for any competent bot (the whole field bets its
MC-best camel, thresholded).

### Posterior
When seat `o` places a game-winner bet (detected via §0), reconstruct the
approximate board at their turn (last snapshot advanced by the camel moves
attributable before their seat position; midpoint approximation fine).
Compute camel win probabilities `q_c` there (our own `_mc_game`, a few
hundred sims — runs at most 3×/turn and only when a bet appeared). Then

    P(bet = c) ∝ exp(β · q_c),  β ≈ 10 (knob BET_GREED),

restricted to camels `o` hasn't plausibly already bet (engine forbids
re-betting a camel across both lists: subtract the same player's earlier
belief mass, renormalize). Loser bets: same with `lose_p`. Beliefs are
fixed at placement; their value is re-marked each turn against current
probabilities.

### Consumers
1. **Our ladder slot, exactly.** If we bet camel c and c wins, our payout
   index = number of earlier winner-bet entries on c. Earlier hidden entry
   j is on c with probability `b_j(c)` →
   `E[pay] = Σ_k P(k earlier on c) · GAME_PAY[min(k,3)]`
   via Poisson-binomial convolution (n ≤ 12, exact). Replaces the crude
   `idx ≈ n·p²/Σp²` heuristic every bot uses.
2. **Opponent equity.** Replace the flat `OPP_GB_EV = 1.2` per hidden bet
   in the gap model with `Σ_c b_j(c)·(q_c·pay_j − (1−q_c))`, `pay_j` from
   their known ladder position. Sharpens the binding gap exactly where
   endgame decisions live.
3. **Trap targeting.** Opponent equity sensitivity to camel c is
   `≈ b_j(c)·(pay_j+1)·Δq_c` — traps can attack the leader's likely bet
   camel, not just their round settlement.

### Validation before any SPRT (cheap — do first)
The harness sees the unredacted `GameState`, so truth is available: play
~200 scripted games, log every posterior at placement vs the true camel.
Report top-1 accuracy (baseline 20% for 5-way) and calibration per
probability bucket. Below ~50% top-1 on first bets → fix the model before
paying for SPRT. Expected effect: +1–3pp; test with `--delta 0.02`.

---

## 2. Two-ply self-lookahead (computation edge — likely the biggest)

The entire field is 1-ply greedy: score each action, take the max. But our
actions interact across our own turns (trap now enables round bet later;
roll now advances the round toward a settlement we want; claiming a ladder
slot now vs next turn). No information asymmetry — pure decision quality.

Design: for each candidate action a₁, advance the round distribution as if
a₁ were taken, model the three intervening opponents cheaply (roll, or
claim the greedy round bet if its EV clears a threshold — this consumes
ladder slots, the main interaction), then score our best reply a₂ with the
existing 1-ply machinery and back up `value(a₁) = immediate(a₁) + γ·E[best
a₂]`. Even a coarse opponent model captures the dominant effect: slots and
trap squares disappearing between our turns.

Budget: current bots spend ≤ ~1s/move against a self-imposed ~3.3s cap;
there is headroom for 5–10 candidate a₁ × cheap a₂ scoring. Profile first.
Note the engine imposes NO move time limit (tournament only reports ms) —
as tournament owner, decide and document a cap before someone exploits it;
design to whatever cap is ruled.

---

## 3. Exact endgame solver (computation + turn counter from §0)

Trigger: `p_end > 0.35` or leader position ≥ 12. For the terminal branch
(already enumerated exactly in `fs`): compute final coins per outcome —
round settlements are public and exact; our game bets known; opponents'
hidden bets in expectation under §1 beliefs; roll income attributed to
actual seats via the turn counter. Score `P(strict win) + tie share`
(tournament splits ties). Non-terminal branch falls back to current
machinery. Two-round exact enumeration only if the one-round version
measures well.

---

## 4. Claim-rate option pricing (statefulness edge #2 — small, cheap)

Betting a round-bet slot now locks the ladder position at today's beliefs;
waiting sharpens beliefs but risks losing the slot. Track this game's
observed claim rate (how fast round-bet/trap slots fill per turn, from §0
diffs — an aggregate rate, not per-bot profiling) and price the option:
bet now iff `EV(now) > P(slot survives) · E[EV(next turn)]`. Same logic
for the game-bet 8-slot and for premium trap squares. Fold into §2's
lookahead if built; standalone knob otherwise.

Related zero-sum term, stateless and nearly free: **slot denial** — when
we take a ladder slot, the binding opponent loses access to it. Price
round bets as `own EV + w · (binding opponent's forgone EV)` with the same
threat weights `_position_value` already uses for traps (0.35/0.18).

---

## 5. Second-wave ideas (added 2026-07-03, unbuilt unless noted)

- **Income-rate pacing** (BUILT: tb-PacedPete): everyone paces on current
  coins; nobody on earning *rates*. Memory of the money trajectory gives
  each player's coins/cycle; effective standing = lead + (my rate − best
  opponent rate) × cycles remaining. Leaders with weaker engines should
  end the game; trailers with stronger engines should extend it. Feeds
  the pace term and gives the roll action explicit game-ending credit.
- **Opponents-as-champion**: the Cup field is likely LLM-written EV bots
  that reason like FabelFelix — so in lookahead, model opponents as a
  cheap FabelFelix-lite instead of as dice. If the monoculture hypothesis
  holds this is near-perfect opponent prediction. Enables true 2-ply.
- **Round-end parity**: rolling the round's last die gifts the next seat
  a fresh round (first pick of trap squares + full ladders). Price that
  transfer before taking the +1.
- **Negative-information inference**: update hidden-bet beliefs when an
  opponent *declines* an obviously strong game bet (they likely hold that
  camel already). Extends `_observe` from placements to inaction.
- **Trap-shadow denial**: a trap blocks its square and both neighbors for
  opponents — place/move ours to deny the premium square ahead of the
  leader; the move-trap action makes this a repeatable channel.
- **Opening book**: tiny first-turn state space (5 camels on squares
  0–2); precompute best opening action per configuration class offline.
- **Adaptive compute**: extend MC only when the top-2 candidate actions
  are within noise of each other (sequential testing inside the bot).

## 6. Fully analytic evaluation — no Monte Carlo (added 2026-07-03)

Motivated by curried_camel's tournament profile (max 254ms/move, best
avg coins in the field): the only MC left in our stack is `_mc_game`'s
game-winner sampling; everything else is exact. Replace it:

- **Current round**: `_enum_round` extended to also emit (a) per-camel
  position marginals at round end conditioned on the game continuing,
  and (b) the last-place camel distribution for game-ending branches.
  Exact, nearly free — the enumeration already visits every state.
- **Future rounds**: independent trinomial walks. Each camel advances
  its own die (uniform 1–3) once per round; first-crossing-time
  distributions via a 5 × 16-position × ~14-round DP (exact
  convolution, microseconds). Race resolution: win when crossing
  strictly first; simultaneous crossings split pairwise at 0.5.
  win_p = ends-now branch (exact) + (1−p_end) × race win. lose_p from
  position marginals at the expected ending round (independence
  approximation for the min).
- **Knowingly dropped in v1**: future-round stacking carries (current
  round's carries ARE exact via the enum) and future traps (measured
  ~+0.4pp at best). If calibration shows leader bias, add a CARRY_W
  knob before reaching for MC again.
- **Gate before SPRT** (the harness makes this free): over scripted
  games, Brier-score analytic win_p vs the 0.9s-budget MC win_p against
  realized winners. Analytic must match or beat MC's calibration. Note
  MC at 250–3000 sims has ±1–3pp sampling noise per estimate — beating
  it is plausible, not just matching.
- Payoff if it works: noise-free EVs (no more decision flips between
  identical states), ~10× faster moves, and compute headroom for the
  backlog (exact endgame, deeper trap search) that the MC budget was
  eating.

## Evaluation protocol

1. Offline calibration/accuracy first (truth available in harness) —
   never pay for SPRT on a component that fails offline.
2. One mechanism per revision, SPRT vs current champion, fresh seed.
3. Effects are small: `--delta 0.02`, budget longer runs; a rejection at
   delta 3pp is not evidence of no effect.
4. Every result → `EXPERIMENTS.md`, including rejections and diagnosis.

## Implementation order

| # | Item | Effort | Expected payoff | Depends on |
|---|------|--------|-----------------|------------|
| 1 | §0 observation layer + attribution tests | S | enabler | — |
| 2 | §1 bet inference + calibration script | M | +1–3pp | §0 |
| 3 | §2 two-ply self-lookahead | M | +1–3pp | time-cap ruling |
| 4 | §3 exact endgame (terminal branch) | M | +1–2pp | §0; §1 helps |
| 5 | §4 slot denial + claim-rate option | S | ~1pp | §0 (rate part) |
