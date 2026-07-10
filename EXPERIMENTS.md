# Experiment Log — Camel Up bot iteration

Running record of every bot revision: what changed, why, how it was tested,
and what the data said. All comparisons are paired-seed (common random
numbers) via `evaluate.py` against the strong pool unless noted:
`--opponents tb-ClaudeCamel tb-OpusOmul tb-GeminiGerry tb-HandcodedHenry`.

Methodology decisions, made before any experiment:
- **No NEAT / neural policies.** The hard part of Camel Up (round-outcome
  distribution) is exactly computable; a learned net would re-approximate
  it, the win-rate fitness signal is too noisy for evolution, and evolved
  policies overfit the training pool. Learning is reserved for tuning the
  few scalar knobs of an analytic bot.
- **One change per revision**, gated by SPRT (α = β = 0.05, LLR bounds
  ±2.94). Settings evolved with experience: early runs used δ=3pp / max
  600 pairs; from wave 1 on, δ=2.5pp / max 800 for screening and δ=2pp /
  max 1500 for precision runs. Individual runs decide via SPRT;
  promotion decisions pool across seeds (early stops inflate single-run
  estimates — winner's curse).
- **Offline gate before SPRT budget** for any component with a testable
  inference (the harness holds unredacted ground truth): never pay for
  win-rate measurement on a mechanism that fails offline validation.
- **Strong pool only.** Weak-opponent pools have a ceiling effect: measured
  ClaudeCamel 97.5% vs HandcodedHenry 96.5% (+1.0pp, CI −3.4..+5.4, 100
  pairs) — every decent bot wins ~97% of uncontested games, so there is no
  signal about which is better.

Champion history:
- **FabelFelix** (2026-07-02 → 2026-07-03): exact round enumeration, MC
  game sims, settlement-order-aware EV, hand-tuned risk-lambda schedule.
- **BetTrapReader** (2026-07-03 → 2026-07-05): FabelFelix + hidden
  game-bet inference + future-trap modeling. Promoted on wave-1 pooled
  evidence; confirmed +2.4pp vs FabelFelix over 1,500 pairs. Still the
  live Cup entry as tb-PairTestedPeter.
- **PortfolioPamV2** (2026-07-05 → ): TableTina (exact endgame table)
  + exact-covariance portfolio (λ prices the portfolio increment via
  the joint (winner,last) table). Promoted on waves 12–13: six
  consecutive positive seeds across two baselines; vs BetTrapReader
  directly +1.68 / +10.25 (SPRT) / +4.56 (CI excl 0), pooled ≈ +4pp,
  honest estimate ~+3pp.

---

## Harness (2026-07-02)

`evaluate.py`: candidate and baseline play identical games — same seed,
seat, opponents, camel starting positions, and pre-scripted dice
(`ScriptedDice`; valid because every camel moves exactly once per round in
uniform random order, so per-round move order + die values can be fixed
regardless of when players roll). Self-test: identical bots → exactly
0.00pp over 40 pairs, 0 discordant.

Rev 2 additions: parallel pairs across worker processes (~4.7s/pair on 10
workers, was ~22s serial) and SPRT early stopping. Validated on a lopsided
matchup (HandcodedHenry vs Player2: stopped early, correct verdict).
Engine hooks added to `camelup.py`: `GameState(rng=...)`,
`MoveCamel(..., dice_fn=...)` — both backward compatible.

---

## PairedPaul v1 — one-shot P(win) objective ❌ REJECTED

- **Date**: 2026-07-02, seed 1
- **Change vs FabelFelix**: replaced the EV + λ·σ risk heuristic entirely.
  Modeled each opponent's final coin gap as a normal (mean from coins +
  expected settlements + game-bet priors; variance growing with remaining
  dice) and scored every action by
  P(win) = E_X[∏ₒ Φ((μₒ + X)/σₒ)] over the action's payoff distribution X.
- **Result**: **−7.14pp** (34.58% vs 41.72%), 95% CI −12.92..−1.36,
  467 pairs, SPRT accepted H0 (LLR −2.98). Also −2.6 avg coins/game.
- **Diagnosis** (932-decision divergence trace, `scratchpad/divergence.py`):
  46% disagreement with FabelFelix in the early game vs 11% late; the
  dominant flows were rbet/trap/roll → game bets. The Φ-product objective
  is *convex* — one +8 payoff clears all three opponents at once, so
  longshot game bets look great — and *myopic*: with ~15 turns left,
  banking EV each turn and adding variance later dominates. Early wrong
  game bets at −1 each explain the coin deficit.
- **Lesson**: greedy per-move P(win) ≠ optimal policy. The objective is
  right; the altitude (per-action, one-shot) is wrong.

## PairedPaul v2 — local-quadratic P(win) (EV + derived-risk × var) ❌ NOT BETTER

- **Date**: 2026-07-02, seed 2
- **Change vs FabelFelix**: kept v1's gap model but used its local form:
  maximizing Φ((μ+m)/√(σ²+v)) over an action with payoff mean m, variance v
  reduces to m − (μ/2σ²)·v, so actions score EV + risk·var with
  risk = clamp(−μ_b/(2σ_b²), ±0.35) from the binding opponent. Also (in
  hindsight, a mistake in experiment design) changed trap valuation to
  binding-gap shift and dropped FabelFelix's pace-preference term — three
  simultaneous changes.
- **Result**: **−3.94pp** (39.1% vs 43.1%), 95% CI −9.06..+1.17, ran to
  the 600-pair cap (LLR −2.40, just short of formal rejection). Verdict:
  no significant difference — but the point estimate is negative and the
  CI barely includes 0. Champion unchanged.
- **Lessons**: change one mechanism per revision, or attribution is
  impossible; and an inconclusive SPRT with a −4pp point estimate is not
  a keep — the burden of proof is on the challenger.

## PairedPaul v3 — minimal: derived risk term only ❌ NOT BETTER

- **Date**: 2026-07-02, seed 3
- **Change vs FabelFelix**: exactly one — the hand-tuned λ schedule
  (`lam·√var`, stepwise on lead and urgency) replaced by the derived
  coefficient `risk·var`, risk = clamp(−μ_b/(2σ_b²), ±0.35) from the gap
  model. Trap valuation, pace term, everything else verbatim. Knobs
  (all first guesses): GB_PAY_EST=4.0, OPP_GB_EV=1.2, OPP_GB_VAR=6.0,
  SIG_BASE=4.0, SIG_PER_DIE=0.4, RISK_CAP=0.35, TRAP_VAR=0.5.
- **Result**: **−2.44pp** (39.5% vs 41.9%), 95% CI −7.44..+2.55, ran to
  the 600-pair cap (LLR −1.82). No significant difference; negative
  point estimate.
- **Conclusion for the whole line**: across v1 (−7.1pp), v2 (−3.9pp) and
  v3 (−2.4pp) the P(win)-derived risk term loses to FabelFelix's
  hand-tuned λ schedule every time. FabelFelix's risk posture is not the
  weak point — stop touching it. Pivot to information/computation edges.

---

## Overnight batch — 2026-07-02 (run via `run_queue.py`)

Pivot away from risk-term tinkering toward the statefulness edges in
`DESIGN.md`. Three new candidates, all = FabelFelix + one mechanism:

- **tb-BetReader** — hidden game-bet inference. Reconstructs opponents'
  face-down game bets from public placement order/timing (see
  `bots/_observe.py`), then (1) prices our own bet-ladder slot from the
  expected number of earlier bets on the same camel and (2) inflates an
  opponent's effective coins by their inferred bet equity when weighing
  threats. The flagship stateful edge.
- **tb-TrapAware** — models future opponent traps (a -1 ahead of the
  leader, prob P_TRAP) in the MC game sims, correcting a bias every bot
  shares (all assume no future traps).
- **tb-BetTrapReader** — both combined; tests whether the edges stack.

Validation before queueing (PASSED 2026-07-03): smoke clean
(TrapAware 161ms, BetReader 185ms mean/move); inference calibration
over 150 games / 964 true opponent bets: **63.1% top-1** (random
~20–33%), 67.4% on each player's first bet, mean P(true camel) 0.42,
reliability roughly monotone (conf 0.3→60%, conf 1.0→73%; mildly
overconfident at the top — acceptable). Cleared the ≥50% gate in
DESIGN.md §1. Repro: `python calibrate_beliefs.py`.

Queue = 12 SPRT runs vs FabelFelix across seeds 11–23,
single-mechanism runs first, three precision (δ=0.02, 1500-pair) runs
last. Budgeted ~8h; interruptible and resumable (`run_queue.py` skips
experiments whose log already holds a verdict). Results append to
`overnight_results.md` + full per-pair logs in `scratch_logs/`.

## Overnight wave 2 — exploration (chained via `run_queue2.py`)

Per the "new ideas beat refinement" call: a second queue idles until wave 1
finishes, then runs **tb-PacedPete** (FabelFelix + income-rate pacing:
effective lead = lead + (my earning rate − best opponent's) × cycles left;
pace term and roll's game-ending credit use it) across seeds 31–33.
Second-wave idea list (opponents-as-champion, round-end parity,
negative-information inference, trap-shadow denial, opening book,
adaptive compute) is in DESIGN.md §5.

Early wave-1 readings (800-pair runs, individually inconclusive):
BetReader +2.54pp (s12) and +1.35pp (s14) — positive at both seeds, the
first candidate to point the right way; TrapAware +0.62pp (s11), then
trending ~−2pp at s13; BetTrapReader +0.42pp (s21). The δ=0.02
precision run to read closely in the morning is BetReader's (s17).

Mid-night revisions (2026-07-03, per operator):
- **Cut** the TrapAware (s19) and BetTrapReader (s23) 1500-pair precision
  runs via skip-stub logs — flat candidates, ~2.4h saved. BetReader's
  precision run kept.
- **PacedPete demoted** before testing: within one game an earning rate
  is ~unidentifiable (12–15 lumpy money snapshots; SE ≈ 0.7 coins/cycle
  vs true strong-pool differences of ~0.1–0.3). Keeps one curiosity seed
  (s31) as all of wave 2.
- **BetReaderV2 (negative-information inference) FAILED its offline
  gate** — paired calibration on identical observations, 236 bets:
  winner-bet top-1 56.1% vs v1's 59.2%, mean P(truth) a wash. Boosting
  beliefs toward the *current* favorite misfires (opponents' bets were
  placed at earlier board states; declines happen for other reasons;
  boosts compound across correlated turns). Not SPRT'd, per protocol.
  Rework ideas: use the favorite at *belief-formation* time, one-shot
  instead of compounding boosts, require the decliner to have no better
  action available. Code: `bots/_observe2.py`, `bots/BetReaderV2.py`.
- **Two design bots built and queued into wave 2** (2 seeds each, then
  the PacedPete curiosity seed): **tb-ParityPeggy** (DESIGN.md §5
  round-end parity: rolling the last die pays PARITY_COST×(1−p_end) for
  gifting the next seat the fresh-round opening) and **tb-TrapDenyDana**
  (trap-shadow denial: candidate traps earn DENY_W×landing[p]×
  trapless-opponents/3 for the real estate they take away). Both
  stateless single-knob mechanisms importing FabelFelix's machinery
  unchanged. Opponents-as-champion deliberately deferred to a daytime
  build — too large to construct and gate unattended.

## Wave 1 final results (completed 2026-07-03 ~09:45)

| Run | Result | Verdict |
|---|---|---|
| BetReader s12 | +2.54pp | inconclusive |
| BetReader s14 | +1.35pp | inconclusive |
| BetReader s16 | +0.38pp | inconclusive |
| BetReader s18 | +2.30pp | inconclusive |
| BetReader s17 (1500 pairs) | +0.70pp | inconclusive |
| TrapAware s11 / s13 / s15 | +0.62 / −0.60 / +1.17pp | inconclusive ×3 |
| BetTrapReader s21 | +0.42pp | inconclusive |
| BetTrapReader s22 | **+5.47pp** | **SPRT accept H1** (early stop → estimate inflated) |

Pooled analysis:
- **BetReader: +1.34pp over 4,700 pairs (CI ≈ −0.3..+2.9)** — just short
  of significance, but positive at **5 of 5 seeds** (sign test p ≈ 3%).
- **TrapAware: ≈ +0.4pp over 2,400 pairs** — consistent with ~0.
- **BetTrapReader: ≈ +2.9pp over ~1,600 pairs (CI roughly +0.3..+5.5)**
  — pooled CI excludes 0, though s22's early stop inflates it.
- All 7 runs of bet-inference bots (BetReader + BetTrapReader) came out
  positive: sign-test p < 1%. **The hidden-bet inference mechanism is
  almost certainly real; best estimate of magnitude +1–2pp**, with trap
  modeling adding little on its own but possibly stacking.

**Decision (operator, 2026-07-03): PROMOTED — tb-BetTrapReader is the new
champion** and the baseline for all future experiments. Caveat carried
forward: the pooled +2.9pp leans on s22's early-stopped run; honest
magnitude estimate +1.5–2.5pp over FabelFelix. Any future candidate
should SPRT against tb-BetTrapReader, and a fresh-seed confirmation of
the champion itself remains a worthwhile cheap experiment.

## LookaheadLuke — opponents-as-champion 2-ply lookahead (built 2026-07-03)

The big daytime build (DESIGN.md §2/§5, scoped to slot depletion).
**tb-LookaheadLuke** = champion BetTrapReader + a lite opponent policy
(each intervening opponent takes the best of roll / round-bet slot /
game bet, priced from our own EV tables, consuming ladders in turn
order) + 2-ply scoring: value(a₁) = immediate + P(survive) × best option
at our next turn under predicted depletion. Fixes 1-ply myopia: defer
marginal bets opponents won't take (harvest roll +1 AND the bet), claim
now what they will take. Falsifiable: predicts each opponent's next
action class; gate scores predictions vs reality.

- **Gate iteration 1 (FAILED)**: 24 games, 1,124 predictions — 44.3%
  accuracy vs 41.4% majority baseline. Diagnosis: over-predicts roll
  (static snapshot underestimates opponents' bet EVs — the interval's
  dice sharpen round bets before later actors move), pessimistic game-bet
  ladder index, loser bets unmodeled.
- **Gate iteration 2 (FAILED)**: added round-bet uplift, the field's own
  ladder-index heuristic for game bets, loser-bet prediction — 41.0%,
  exactly the majority baseline (over-corrected into over-predicting rb).
- **Gate iteration 3 (FAILED — SHELVED)**: pivoted to what the mechanism
  actually consumes: probabilistic expected-depletion forecasts (softmax
  over option EVs) scored by MAE against realized claims. Model lost to
  the ZERO-depletion baseline on every metric (all-camel 0.268 vs 0.242;
  top-camel 0.620 vs 0.556; gw-count 0.382 vs 0.231).
- **Verdict: opponents-as-champion is shelved.** Root cause, consistent
  across all three gates: opponents' interval behavior is dominated by
  dice that haven't rolled yet; simulating their *reasoning* from our
  snapshot cannot beat trivial forecasts. The monoculture premise may be
  true, but their decisive inputs are unobservable from our turn.
- **Salvage notes** (for a future attempt): (1) MAE is a harsh scoring
  rule for sparse counts — zero wins MAE whenever P(no claim) > 0.5 even
  when the rate is real; a Brier-scored per-slot survival probability is
  the fairer gate. (2) The top-EV camel's slot IS claimed at a high rate
  (~0.56 claims/interval measured) — so DESIGN.md §4's *calibrated
  constant hazard* (claim-rate option pricing, no opponent simulation)
  remains promising and is much simpler. (3) `run_queue3.py` is guarded
  (env LUKE_GATE_OVERRIDE) against accidental launch.

## Wave 2 final results (completed 2026-07-03 ~12:12)

| Run | Result | Verdict |
|---|---|---|
| ParityPeggy s51 | −0.85pp | inconclusive |
| ParityPeggy s52 | **+3.67pp** | **CI excludes 0** |
| TrapDenyDana s61 / s62 | +0.19 / +0.17pp | flat — **REJECT** |
| **PacedPete s31** | **+11.35pp** (CI +5.6..+17.1) | **SPRT winner — largest result of the project** |

The humbling headline: **PacedPete — demoted before testing by both
operator and Claude as "extrapolating luck" — put up +11.35pp on its one
curiosity seed.** An SPRT early stop inflates the estimate, and it is one
seed; but even heavily discounted it demands replication. Candidate
explanations if real: the roll-credit facet (explicitly pushing the pack
over the finish line while ahead) may matter far more than the
income-rate estimate itself; FabelFelix's pace term only modulates traps,
so it systematically under-ends games it is winning. Lesson recorded:
**priors are for choosing what to test first, not for skipping tests —
the one-seed curiosity run was nearly free and would have been the
biggest miss of the project.**

Wave 4 launched (~12:48): PacedPete s32/s33/s34, ParityPeggy s53, plus
the pending champion confirmation (BetTrapReader vs FabelFelix, 1500
pairs, δ=0.02, seed 99). ~4h total; results append to
overnight_results.md as usual.

## AnalyticAnnie — zero-Monte-Carlo evaluation ❌ SHELVED (2026-07-03)

Ground-up rebuild of the game-level evaluator inspired by curried_camel's
tournament profile (sub-300ms, best coin economy). Kept the exact round
enumeration (extended to emit per-camel end-of-round position marginals,
last-place-if-ends distribution, and expected stack heights — exact and
nearly free) and replaced `_mc_game` with a closed-form race: independent
trinomial walks, first-crossing DP, pairwise tie-splitting. Decision
layer unchanged from champion. Eval speed: **15–22ms vs MC's ~92ms**.

Calibration gates (Brier vs realized winners, MC(0.9s) as reference,
~490 positions/run):
1. Pure independence race: win-Brier 0.808 vs MC 0.744 — FAIL.
2. + stack-carry term (probabilistic +1 step, knob grid): best 0.755
   (carry=1.0) vs MC 0.723 — improved, plateaued, FAIL; carry also
   degrades lose-side calibration.
3. Hybrid (analytic far from finish, MC(0.3s) near): best 0.761 at the
   most-MC threshold, trend monotonic toward pure MC — FAIL.

**Verdict: stack dynamics are load-bearing at every game stage; camels'
finishing odds are jointly determined by stack membership in ways an
independence model cannot express. Camel Up's game-winner odds genuinely
require full-state sampling (or exact multi-round enumeration — a much
heavier future project).** The speed thesis was confirmed (6× faster),
but speed isn't win rate; our MC at 0.9s is nowhere near the 5s limit.

Salvage worth keeping: (a) the marginals-extended enumeration — the
ends-this-round branch of win_p/lose_p is EXACT and could
Rao-Blackwellize the champion's MC (sample only the continue-branch,
combine with exact now-branch) for a pure variance reduction; (b) the
measured fact that curried_camel-class speed is achievable if ever
needed for a deeper search budget. Code stays in `bots/AnalyticAnnie.py`
(registered but not to be SPRT'd as-is).

## Risk profiling & wave 5 (2026-07-04)

New instrument `risk_profile.py`: measures a bot's *revealed* risk
response curve — per coin-lead bin, the volatility of chosen actions,
the EV premium paid, and how often the bot chose a higher-variance
action than the EV-max one. Measured over ~630 decisions each:

- Both FabelFelix and the champion ARE risk-responsive: seek-rate falls
  40–48% (buried) → ~0% (ahead); rolling rises 6% → ~30%; the champion
  pays a real insurance premium (0.22 EV/turn) when far ahead.
- **Key finding: when deeply behind, available σ SHRINKS** (mean chosen
  σ 1.85 at lead ≤−8 vs 2.3 at −3..−1) because deficits happen late,
  when round outcomes are near-certain and ladders are depleted. The
  binding constraint is risk *capacity*, not appetite — predicting that
  steepening λ buys little, and that the real desperation play is traps
  (which add variance to the race itself). Wave 5 tests this.

Wave 5 launched (stacked attribution, 2 seeds each):
- **tb-RiskyRandy** (champion + steeper knob-exposed risk curve) vs
  champion — tests appetite.
- **tb-RiskyRandyV2** (+ portfolio term: −PORT_W × posture × corr × σ;
  diversify ahead, concentrate behind — a mechanism no bot in the field
  has) vs RiskyRandy — tests the portfolio axis.

## Wave 5 final — risk curve dead, portfolio term REPLICATED (2026-07-04)

| Run | Result |
|---|---|
| RiskyRandy vs champion s121/s122 | −0.79 / −1.27pp — **steeper risk curve REJECTED** (capacity, not appetite, binds — as the risk profiler predicted) |
| RiskyRandyV2 vs RiskyRandy s131 | **+4.52pp (CI +0.47..+8.57, excludes 0)** |
| RiskyRandyV2 vs RiskyRandy s132 | **+2.6pp at 790/800** (run's pool hung at drain; killed, data kept) |

**Portfolio term pooled: ≈ +3.6pp over ~1,590 pairs, CI ≈ +0.9..+6.3 —
replicated across two seeds.** The first mechanism since bet inference
to clear the bar, and it is the operator's idea (diversify ahead,
concentrate behind). Harness note: multiprocessing pool can hang at the
final-pairs drain if a worker dies mid-pair — consider a per-pair
timeout in evaluate.py.

**Wave 6 launched**: tb-PortfolioPam (champion + portfolio term only,
Randy's dead curve stripped) vs tb-BetTrapReader, seeds 141–143. If
pooled positive → new champion → resubmission candidate.

Ops same day: Player0 also removed from the Cup roster (explicit
HOUSE_ROSTER in handler decouples the lab registry from the deployed
field); winner-take-all Bradley-Terry Elo added to the leaderboard
build (second place earns nothing, per operator ruling); site handoff
in SITE_HANDOFF_ELO.md; final Elo-rated rerun in flight.

## Exact endgame table (2026-07-04) — gate PASSED, wave 7 launched

Prompted by the operator's lookup-table theory of curried_camel. The
race-odds state space is tiny once canonicalized: 5 camels on 16 squares
with stacking = 16·17·18·19·20 = 1,860,480 states / 5! relabelings =
**15,504 canonical classes**. `gen_endgame_table.py` solved all of them
EXACTLY by backward induction over position-sum (each state = one exact
trapless round enumeration whose round-complete leaves are already-solved
higher-sum states): **7 minutes of compute, 3.4MB JSON, 0 probability-sum
errors**. `bots/_endgame.py` integrates it: current round enumerated
exactly WITH live traps; round-end leaves are table lookups. This is the
exact value of the same trapless-future quantity the MC sampled.

Gate (322 positions, Brier vs realized outcomes): **table 0.7134 vs
MC(0.9s) 0.7147 on wins** (exact beats sampled, as theory requires),
lose-side identical, **20.7ms vs 93.4ms mean eval**. PASS.

**tb-TableTina** = champion + exact odds (one engine swap; TrapAware's
future-trap micro-feature knowingly dropped — the table is trapless-
future like plain MC).

**Wave 7 final (−3.56 / +0.38 / −0.21pp, pooled ≈ −1.1 ± 1.6 over 2,400
pairs): statistical parity with a negative lean.** Reading: MC at
250–3,000 sims is accurate enough that its noise rarely flips decisions
that matter — exact inputs play equal, not better. Per the
burden-of-proof rule (a negative-leaning inconclusive is not a keep),
**champion remains tb-BetTrapReader for competition**. TableTina is
adopted as the **R&D platform base**: equal within noise, 4.5× cheaper
and deterministic, so future mechanism experiments build on Tina and
SPRT vs Tina (faster waves) — but any Tina-based winner must ALSO beat
tb-BetTrapReader before promotion or submission. The freed compute
reopens the backlog: deeper trap search, 2-ply with an exact evaluator.

**Wave 6 final — PortfolioPam ❌ NOT PROMOTED**: +0.44 / +0.33 / −1.86pp
across three seeds vs champion, pooled ≈ −0.4pp over 2,400 pairs —
nothing. The portfolio term's +3.6pp in wave 5 was an *interaction*: it
corrected RiskyRandy's over-steep risk curve rather than adding
free-standing value (V2 = Randy + portfolio ≈ champion, i.e. the two
changes cancel). Lessons: (1) mechanism effects measured on a modified
base don't transfer — keep SPRT baselines minimal; (2) a "+X over a
worse bot" result ceilings at parity with the unmodified original.
Champion remains tb-BetTrapReader, pending wave 7.

## Current state (as of 2026-07-04 ~14:30 — all waves 1–7 complete)

**Champion (competition): tb-BetTrapReader** — confirmed +2.4pp vs
FabelFelix over 1,500 fresh pairs. Live in the Cup as
**tb-PairTestedPeter** (`bots/NudeTayne.py`, single-file
sandbox-validated build; operator-submitted through the regular
pipeline). Current board: 3rd, Elo 1529, behind FH_ActualReplicant
(1600) and curried_camel (1551).

**R&D base: tb-TableTina** — champion with the exact endgame table
(15,504 canonical states) replacing MC. Parity in strength, 4.5× faster,
deterministic. New mechanisms build on Tina and SPRT vs Tina; winners
must also beat tb-BetTrapReader before promotion/submission.

**Tournament ops shipped**: Player0/1/2 retired from play (explicit
HOUSE_ROSTER decouples the lab registry from the deployed Cup);
winner-take-all Bradley-Terry Elo in the leaderboard (site handoff in
SITE_HANDOFF_ELO.md); FH_Replicant removed/rerun for its author.

**Mechanism scoreboard across the campaign**:
- Survived: hidden-bet inference (+1–2pp, in champion), trap-aware sims
  (small, in champion), exact endgame table (parity at 4.5× speed).
- Dead with diagnosis: P(win) risk terms (v1–v3), opponents-as-champion
  lookahead (3 gates), no-MC independence race, steeper risk curve
  (capacity binds, not appetite), income-rate pacing (winner's curse),
  round-end parity, trap-shadow denial, negative-information inference
  (failed calibration), portfolio term (interaction artifact).

## Wave 8 — EndgameEddie ❌ NOT PROMOTED (2026-07-04)

Exact final-round coin race (bots/_coinrace.py: per-outcome deterministic
settlements, belief-convolved opponent bets, roll-income attribution)
active at p_end ≥ 0.2, on the Tina base. Seeds: −1.84 / +0.77 / −1.22 →
pooled ≈ −0.8 ± 1.6 over 2,400 pairs. Flat.

Diagnosis candidates, in order of suspicion:
1. **Dilution**: the mechanism only acts on ~15–25% of turns (endgame
   regime), so even a real +2pp-per-affected-decision edge shows as
   <0.5pp overall — below this wave's resolution. Methodology note for
   the future: regime-limited mechanisms need *targeted* paired evals
   seeded from in-regime states, not whole-game win rates.
2. Endgame decisions are often near-forced (one clearly best action), so
   exactness rarely flips them — consistent with wave 7's finding that
   removing MC noise didn't help either.
3. The coarse edges (roll-income attribution, game-continues logistic,
   opponent pay-ladder estimate) may cost what the exact core earns.

Pattern across waves 7–8: **the champion's decision heuristics appear to
be near the game's decision-quality ceiling** — better inputs and exact
objectives keep measuring as parity. Remaining edges likely live in
information (belief calibration), knobs, or regime-targeted tests fine
enough to see small effects.

## Wave 9 — TargetTara ❌ NOT PROMOTED (2026-07-04)

Rival targeting when behind (differential bets vs the effective leader's
inferred portfolio + exact equity-damage trap credits). Seeds: −1.99 /
+0.25 / +0.27 → pooled ≈ −0.5 ± 1.6 over 2,400 pairs. Flat. Same
dilution caveat as Eddie (mechanism active only when trailing a
meaningful amount), so "unproven at whole-game resolution," not
disproven.

**Plateau assessment after waves 7–9**: three principled mechanisms
(exact inputs, exact endgame objective, zero-sum targeting) all measured
parity on the Tina/champion base. The heuristic core appears to sit near
this game's decision-quality ceiling at whole-game resolution. Remaining
credible edges, in order: (1) the never-attempted knob sweep (every
constant is a hand guess); (2) belief recalibration (measured
overconfidence at high confidence); (3) a targeted-eval harness for
regime-limited mechanisms (Eddie/Tara deserve re-judgment at proper
resolution); (4) post-Cup study of FH_ActualReplicant and curried_camel
(they hold ~7–12pp on us — a real algorithmic gap exists somewhere).

## Knob sensitivity sweep — COMPLETE (2026-07-04, `sweep_runner.py`)

Twelve big-jump arms (halve/double each constant family), TunedTina vs
TableTina, 600 pairs, δ=3pp. TunedTina verified decision-identical to
Tina at defaults (51/51) before the sweep.

| Family | Jumps | Results | Verdict |
|---|---|---|---|
| belief greed β | 5 / 20 | +0.17 / −2.00 | insensitive (basin at 10) |
| **threat weights** | 0.55-0.30 / 0.20-0.10 | **−5.44 (CI excl 0)** / −1.60 | **load-bearing; default 0.35/0.18 ≈ optimum** |
| continuation factor | 9 / 3 | −1.35 / +0.82 | insensitive |
| equity prior | 5 / 1.5 | +0.00 / +0.34 | behaviorally inert (near-zero discordance) |
| pace | ×2.3 / ×0.3 | +0.83 / +0.82 | insensitive |
| trap risk-bonus | 0 | −2.50 | weakly load-bearing; keep 0.4 |
| urgency | 1.5 | −0.22 | insensitive |

**Conclusion: no tuning gains exist at this resolution.** Every big jump
measured ≤0 in expectation; the only significant result was a
degradation. The day-one hand guesses were already at or near optimum —
the incumbent constants win. Combined with waves 7–9, the plateau
conclusion is now strongly supported: the champion's decision core is
near this game's ceiling for both mechanisms AND parameters. The
~7–12pp gap to FH_ActualReplicant/curried_camel must be structural —
something they compute or infer that we have not conceived. Best paths
remaining: targeted-eval harness (re-judge Eddie/Tara at proper
resolution), belief recalibration (small), and post-Cup study of the
leaders' published bots.

Harness note discovered mid-sweep: for behaviorally-inert knobs the CRN
pairing collapses variance (most pair diffs exactly 0), so tight CIs
around 0 are themselves evidence the knob rarely changes any decision.

## Wave 10 — the eval pool was stale (launched 2026-07-05)

A new, stronger outside bot joined the Cup, prompting the realization
that our eval pool (ClaudeCamel/OpusOmul/GeminiGerry/HandcodedHenry) is
now weak relative to the live field — the day-one ceiling-effect lesson
recurring one level up. Waves 8–9 measured "parity" in games our lineage
wins at ~42%; exact-endgame and rival-targeting are precisely the
mechanisms that should matter in CLOSE games against strong opponents.

**Pool upgrade**: ELITE = tb-BetTrapReader, tb-TableTina,
tb-EndgameEddie, tb-TargetTara (champion-tier self-play, all
table-fast). All future waves should use ELITE, not the legacy STRONG
pool. Wave 10 re-judges Eddie and Tara vs TableTina in ELITE (2 seeds
each). The plateau conclusion is provisionally suspended pending these
results. (Using Cup submissions as local sparring partners remains an
operator-only governance option, deliberately not taken.)

## Waves 10–11 — elite pool + endgame-targeted evals (2026-07-05)

**Wave 10 (elite self-play pool)**: Eddie +2.73 / +1.46 (positive lean,
inconclusive); Tara −0.06, then an anomalous **−13.41 (CI excl 0)** —
not reproduced by a 133-decision exception hunt (0 crashes); recorded as
an SPRT tail event or rare state-dependent failure. Tara: flat overall,
shelved.

**Wave 11 (endgame-targeted harness, `evaluate_endgame.py`)**: every
pair starts from an identical leader-at-square-12 snapshot (four-Tina
scripted warmup, takeover-seat memory cleared symmetrically; self-test
0/30 discordant with the deterministic opponent trio). Eddie's
engagement-threshold arms:

| EDDIE_THRESH | diff | discordant |
|---|---|---|
| 0.05 | −1.61pp | 121/623 |
| 0.20 (a) | −1.07pp | 118/688 |
| 0.20 (b) | −1.75pp | 87/504 |
| 0.50 | −1.09pp | 58/444 |

Pooled ≈ **−1.35 ± 1.5 over ~2,260 in-regime pairs. The exact coin race
is definitively NOT better than the inherited heuristics — the wave-8
dilution excuse is gone.** EndgameEddie: REJECTED (mechanism, not just
measurement). The wave-10 elite lean was noise.

**Program-level conclusion, now at high confidence**: the champion core
has survived exactness challenges at every altitude — inputs (w7),
whole-game objective (w8), targeting (w9–10), parameters (sweep), and
regime-pure endgame play (w11). Decision quality *given our
information* is essentially maxed. The leaders' edge must be
information we don't extract or structure we haven't modeled. Highest
remaining value: post-Cup study of published leader bots; the
targeted-eval harness and elite pool are permanent assets for whatever
that reveals.

## EV-based bet inference ❌ FAILED GATE (2026-07-05)

Operator idea: infer opponents' hidden game bets from the EV they faced
at bet time (probability × ladder slot payout) instead of raw win
probability. `bots/_observe_ev.py`; paired ground-truth calibration on
identical observations (328 bets): **top-1 52.1% vs v1's 61.6%, P(truth)
0.395 vs 0.424 — the refinement degrades inference.** Not SPRT'd.

Diagnosis: same failure family as opponents-as-champion — modeling
opponents' reasoning in MORE detail than they actually reason. The field
bets its noisy MC favorite with thresholds and quirks; "bet the likely
winner" (v1) is the robust common denominator, and ladder-EV corrections
add mismatched structure. v1's simplicity IS its calibration edge. The
bet-tracking capability itself remains live in the champion (v1,
63/61% top-1) and already feeds equity weighting + endgame plumbing.

## Wave 12 — PortfolioPamV2 ✅ WINNER vs TableTina (2026-07-05)

The portfolio idea's second stab, done exactly (operator-initiated
revisit). Changes vs the failed v1: (1) the endgame table regenerated to
carry the **joint P(winner, last)** per state (5-min regen; joint-
marginal consistency 0 errors) so game-bet portfolio variance is an
exact 25-term sum (`bots/_portfolio.py`); round-bet holdings exact over
the round enumeration; (2) **no new knobs** — the sweep-validated λ
schedule prices the portfolio INCREMENT `σ(with) − σ(without)` instead
of standalone bet σ. Identical to Tina until holdings exist (smoke:
diverges on 9/57 decisions — surgical activation).

**Seeds: +2.38 / +2.12 / +7.36 (SPRT accept, CI +2.91..+11.81). All
three positive; pooled ≈ +3.5pp, CI excludes 0. Honest estimate
discounting the early-stop: +2.5–3pp over TableTina.** First mechanism
to beat the base since the champion's own promotion.

Lessons: v1 failed on implementation (guessed correlation signs), not
concept — "the idea was never properly tested" is a real failure mode to
check before shelving concepts; and exact machinery (the joint table)
turned an untestable heuristic into a provable computation.

**Wave 13 — CONFIRMED ✅ (2026-07-05): +1.68 / +10.25 (SPRT accept) /
+4.56 (CI excludes 0) vs tb-BetTrapReader directly.** Six consecutive
positive seeds across two baselines; two independently significant.
**tb-PortfolioPamV2 is the new champion** (see champion history). The
Cup resubmission is the operator's open decision; engineering note: a
submission must be a single file with no file I/O, so the joint table
must be quantized + code-embedded (the loser-bet cross-terms are what
need the joint; a slimmer marginals-only fallback exists if size bites).

## 🥇 tb-PortfolioPam — RANK 1 in the Cup (2026-07-05)

The 64KB submission build (`submission_pam.py`, 18,229 bytes): champion
PortfolioPamV2's portfolio mechanism with the joint P(winner,last)
estimated by the same MC rollouts that produce the marginals (counting
pairs is free) — no table needed. Pre-flight: sandbox-validated,
decision-equivalent to lab PamMC at the noise ceiling (57/63 vs 58/63
self-control). Wave-14 validation (vs tb-BetTrapReader): +0.31, then
**+3.98 (CI excludes 0)** — the MC-joint carries the edge.

**Wave 14 final (post-submission): +0.31 / +3.98 (CI excl 0) / +4.08
(CI excl 0) vs tb-BetTrapReader — pooled ≈ +2.8pp.** The MC-joint
submission build fully retains the champion's edge; the noise tax vs the
exact table is ≤ ~0.5pp. The shipped bot is lab-certified.

Submitted as **tb-PortfolioPam**; its 500-game tournament finished
**RANK 1**: Elo 1575.3 (36.1%, 25.8 coins) over curried_camel (1556.5),
FH_ActualReplicant (1535.8), tb-PairTestedPeter (1528.8), and
CurriedCamel13 (1527.0).

Caveats for the sober morning read: single 500-game tournament, Elo gaps
to 2nd–3rd within noise at ~180 games/bot; the field will keep
submitting. Operator options: retire tb-PairTestedPeter (two of our
entries split wins; FH_Replicant-removal precedent) and let the ongoing
waves keep hunting. But as of tonight: **the paired-seed lab took a bot
from 5th-place lineage to the top of the live field in four days, and
the final mechanism was the operator's idea.**

## 2,000-game certification board (2026-07-06, ~$1.20)

Field re-run at 4× sample (≈730 games/bot, win-diff resolution ±2.5pp),
on 4 vCPUs (config: 7076MB, CAMEL_WORKERS=4, CAMEL_TOTAL_GAMES=2000).
Final: CurriedCamel13 1563.9 (33.8%) / **tb-PortfolioPam 1556.7
(33.5%)** / curried_camel 1553.4 (33.1%) / FH_ActualReplicant 1535.9
(30.2%) / tb-PairTestedPeter 1525.2 (29.2%).

**Read: the podium is a statistical three-way tie** (top-3 spread 0.7pp
≈ 0.3σ; separating it needs ~200k games). Pam sits at the measurable
frontier with Matthew's two bots, clearly above the rest.
External-validity check: lab-measured Pam−Peter = +2.8pp; public board
shows +4.3 ± 2.5 — the harness's predictions transfer to live play.
ActualReplicant's early 47%/41% boards were sample luck (now 30.2%).

Frontier implication: beating the curried camels needs new ideas, not
more measurement — post-Cup source study remains the top backlog item.
Measured Lambda economics: 500-game run = 86.8 min billed at 2 vCPU ≈
$0.30 ($0.0006/game, flat across memory sizes).

**Backlog, in rough order of promise** (all cheaper now on Tina):
1. Exact final-round COIN solver — the table gives race odds; the
   last-round coin race (who ends richest) is still heuristic and is
   where games are decided.
2. 2-ply lookahead with the exact evaluator (the compute objection is
   gone; the opponent-model objection stands — needs a new gate design).
3. Claim-rate option pricing (measured top-slot hazard ~0.56/interval).
4. Knob sweeps on the champion with the harness as fitness.
5. Post-Cup: publish bots per 2018 tradition; study the leaders' play.
