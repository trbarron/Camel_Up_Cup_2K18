# Site handoff — Camel Up leaderboard: display the new `submitted` field

For the agent working on tylerbarron.com's Camel Up leaderboard page.
Self-contained; the earlier Elo handoff (SITE_HANDOFF_ELO.md) is
separate and may or may not be done yet — this change is independent.

## Data contract

`GET /images/camel-up/leaderboard.json` (CloudFront, `max-age=30`).
Each entry in `bots[]` now includes:

```json
{
  "name": "tb-PortfolioPam",
  "author": "Tyler Barron",
  "builtin": false,
  "submitted": "2026-07-05T20:40:23+00:00",   // NEW
  ...existing fields (wins, games, winPct, avgCoins, elo, ...)
}
```

- `submitted` is an ISO-8601 timestamp with offset (always UTC), or
  **`null` for house bots** (`builtin: true` — they predate the
  tournament).
- Defensive parsing: treat a **missing key the same as `null`** (a
  cached pre-rollout board could briefly lack it). Never assume it
  parses — wrap in a try/fallback to "—".
- The field is already present in the live board and will be emitted by
  the tournament Lambda in all future boards. No versioning needed.

## UI changes requested

1. **Desktop: add a "Submitted" column** to the leaderboard table.
   Suggested placement: right of the bot/author cell (it's identity
   metadata, not performance). Display the date part only, rendered in
   the viewer's local timezone — e.g. `Jul 5, 2026` — with the full
   timestamp as a `title` tooltip.
2. **Mobile / compact layout**: rather than a new column, fold the date
   into the existing "uploaded" chip under the bot name:
   `uploaded Jul 5` (house bots keep no chip, or show `house`).
3. `null`/missing → render `—` (or the `house` treatment above). Do not
   render "Invalid Date".
4. **Sorting (optional, nice-to-have)**: make the column sortable
   (newest first on first click); nulls always sort last regardless of
   direction. Do NOT make it the default sort — default sort stays as
   the Elo handoff specifies (or win% if Elo isn't implemented yet).

## Why it's nice (for a caption/tooltip if wanted)

The dates tell the tournament's story: the field's arms race is visible
as submission order — later entries competed against everything before
them. No new endpoints, no schema migrations; purely additive display.
