# Camel Up Cup 2026 — Experiment Retrospective

Five days, 14 SPRT waves, ~25 experiments. End state: **tb-PortfolioPam
in a statistical three-way tie for first** on the certified 2,000-game
board. Full detail in `EXPERIMENTS.md`; this is the short version.

## What worked

**Paired-seed CRN harness** (`evaluate.py`) — the foundation. Candidate
and baseline play identical games (same camel starts, scripted dice,
seats, opponents), so skill differences of 2–3pp became measurable in
hundreds of pairs instead of tens of thousands of games. Every other
result in this document exists because of it.

**SPRT + parallelism** — sequential stopping meant clear losers died in
20 minutes while close calls earned full budgets, and 10 workers made a
wave an afternoon instead of a week. Self-allocating compute was worth
more than any single mechanism.

**Hidden game-bet inference** (`BetReader` → champion) — opponents'
face-down bets leak through public placement order/timing; beliefs hit
63% top-1 against ground truth and fed threat-weighting everywhere.
The campaign's first real edge (+1–2pp) and the only *information*
mechanism that survived.

**BetTrapReader** — bet inference + future-trap modeling, promoted
champion on pooled evidence and confirmed +2.4pp over FabelFelix at
1,500 pairs. As `tb-PairTestedPeter`, it validated that lab edges
transfer to the live field.

**Exact endgame table** (`gen_endgame_table.py`) — the user's
lookup-table theory, realized: camel-symmetry collapses 1.86M race
states to 15,504, solved exactly by backward induction in 7 minutes.
Replaced Monte Carlo at 4.5× speed with provably better calibration
(TableTina), and its joint (winner, last) extension later powered the
final champion. The single most compounding artifact built.

**Exact-covariance portfolio** (`PortfolioPamV2`) — the risk schedule
pricing the portfolio *increment* (diversify ahead, concentrate behind)
via exact covariances from the joint table. Six consecutive positive
seeds across two baselines (~+3pp); the mechanism that took the crown —
and it was an operator idea, resurrected after its v1 died.

**PamMC / tb-PortfolioPam** — the 18KB submission build: the joint
estimated free from the same MC rollouts, edge retained (+2.8pp pooled
vs the old champion), rank 1 on submission, certified co-first at 2,000
games. Proof the whole pipeline — idea → gate → SPRT → ship — works.

**The measurement instruments** — the risk profiler (revealed that risk
*capacity*, not appetite, binds when behind), the endgame-targeted
harness (4× resolution for regime mechanisms), the belief calibrator
(ground-truth accuracy before SPRT budget), and the knob-sweep rig.
Several "failed" bots below only failed *honestly* because these existed.

## What didn't work (and what each was worth)

**PairedPaul v1–v3** (P(win) objectives, −7.1/−3.9/−2.4pp) — greedy
per-move P(win) is convex and myopic; it over-gambles. Worth it: taught
one-mechanism-per-revision, and that FabelFelix's hand-tuned risk
schedule was already near-optimal.

**LookaheadLuke** (model opponents as our own algorithm, 2-ply) — three
failed prediction gates; opponents' moves are dominated by unrolled
dice, so simulating their *reasoning* can't beat trivial forecasts.
Worth it: killed the monoculture-lookahead idea for ~30 minutes of gate
compute and zero SPRT pairs.

**PacedPete** (income-rate pacing) — a +11.35pp first seed that
collapsed to nothing under replication. Worth it: the definitive
winner's-curse lesson — SPRT early stops inflate estimates, promotions
pool across seeds. Also: priors pick what to test first, never what to
skip.

**BetReaderV2 / EV-based inference** (two attempts at smarter opponent
models) — both *degraded* belief accuracy on ground truth. Worth it:
the field bets its noisy favorite; modeling opponents as more rational
than they are is a recurring, measurable mistake.

**AnalyticAnnie** (closed-form race, no MC) — lost to the zero-baseline
at every horizon: stack riding is jointly load-bearing and cannot be
independence-approximated. Worth it: pointed directly at the exact
table as the correct alternative, and proved the 6× speed headroom.

**ParityPeggy, TrapDenyDana, TargetTara, EndgameEddie** (round-end
parity, trap-shadow denial, rival targeting, exact final-round coin
race) — all flat, even Eddie under the targeted harness built
specifically to give him a fair trial. Worth it: collectively proved
the champion's heuristics already extract the endgame and the zero-sum
margins, which is what justified pivoting to portfolio structure.

**RiskyRandy / PortfolioPam v1** — steeper risk curve flat (capacity
binds, not appetite); portfolio-with-guessed-signs flat on the champion
after looking great on Randy. Worth it: the interaction-artifact lesson
(effects measured on a modified base don't transfer) and the seed of
the eventual winner — v1's failure was implementation, not concept.

**Knob sweep** (12 big-jump arms) — every arm ≤ 0; the only significant
result was a degradation. Worth it: closed parameter-tuning forever and
certified the day-one constants; also showed CRN pairing detects
behaviorally-inert knobs by collapsed variance alone.

## The meta-lessons

1. Measure before believing: every intuition, including strong ones,
   went through a gate — and most died there cheaply.
2. Winner's curse is real: promotions pool seeds; early stops flatter.
3. One mechanism per revision, tested on the current champion, or
   attribution is fiction.
4. Model opponents as they are, not as they should be.
5. Rejected ≠ wrong: the portfolio concept failed once on a bad
   implementation and later won the Cup. Check whether the *idea* or
   the *code* was tested.
6. Exact machinery compounds: the table built for speed later supplied
   the joint that powered the champion.
