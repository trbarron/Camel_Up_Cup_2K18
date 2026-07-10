# Site handoff — Camel Up leaderboard: new `elo` field, make it the default sort

For the agent working on tylerbarron.com. The tournament Lambda
(`camel-up-tournament`, in the Camel_Up_Cup_2K18 repo) now computes an
Elo rating per bot and includes it in the leaderboard payload. The site
should display it and **sort by it by default**.

## Payload change (backward compatible)

`GET /images/camel-up/leaderboard.json` (CloudFront, `max-age=30`) —
each entry in `bots[]` gains one field:

```json
{
  "name": "curried_camel",
  "author": "Matthew",
  "elo": 1642.7,          // NEW — float, or null (see below)
  "wins": 74.33,
  "games": 170,
  "winPct": 43.7,
  "avgCoins": 29.3,
  ...unchanged fields...
}
```

`elo` is `null` when the board predates the rating system or a bot has
no logged games — handle it (see sorting).

## What the number means (for the column tooltip / blurb)

Winner-take-all Bradley-Terry rating on the familiar Elo scale
(anchored at 1500). Key properties, worth surfacing to players:

- **Only winning counts.** Each game the winner gains against the three
  losers; the losers exchange nothing among themselves. Finishing 2nd
  every game rates the same as finishing 4th every game — matching the
  game's actual objective.
- **Opponent-adjusted.** Beating a strong field pays more than farming
  a weak one, so ratings correct for the seating luck that raw win %
  can't.
- **Wide spread is normal.** Winner-take-all ratings fan out more than
  chess Elo (hundreds of points between top and bottom). Ordering and
  relative gaps are the signal. Suggest displaying rounded to the
  nearest integer.

## Site changes requested

1. Add an **ELO** column to the leaderboard table.
2. **Default sort: `elo` descending**, nulls last; keep the existing
   column-sort interactions (WIN % etc.) available. Fall back to the
   current winPct sort if `elo` is absent from the payload entirely
   (old cached boards during rollout).
3. Medals / rank numbers should follow the default (elo) ordering.

## Addendum (2026-07-06): `submitted` field

Each entry in `bots[]` also now carries
`"submitted": "2026-07-05T20:40:23+00:00" | null` — the ISO timestamp
the bot's submission was accepted. `null` for house bots (they predate
the tournament; show "—" or "house"). Suggested display: a "Submitted"
column with just the date part, or a tooltip on the bot name. Already
present in the live board (patched in place) and emitted by the Lambda
for all future boards.

## Rollout timing & roster note

- The field appears in the first board published after the next
  tournament run completes (Lambda deploy is queued behind an in-flight
  rerun on 2026-07-04). Until then `elo` is missing → the fallback in
  (2) covers the gap.
- Unrelated but visible: the filler house bots (tb-Player0/1/2) have
  been removed from tournament play, so the board has fewer rows. Their
  names remain reserved. No site change needed.
