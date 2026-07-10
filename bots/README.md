# Bots

Bots implement `PlayerInterface` (see `../playerinterface.py`) and are split
into three categories by where they live:

| Folder         | Checked in? | Role |
|----------------|-------------|------|
| `house/`       | ✅ yes       | The Cup's standing opponents (`HandcodedHenry`, `ClaudeCamel`, `GeminiGerry`, `OpusOmul`, `FabelFelix`). These play in every tournament and are the field a submission is measured against. |
| `test/`        | ✅ yes       | Smoke-test baselines (`players.py` → `Player0/1/2`). The Lambda seats a new submission against these to validate it before it joins the field. Not scored in the Cup. |
| `contenders/`  | ❌ **gitignored** | The private competitive lab — bots being developed for / submitted to the Cup. Never checked in, never deployed. |

## Why contenders are isolated

The engine (`camelup.py`) and tournament core (`tournament_core.py`) must **never
hard-import a contender**, or a bare checkout (and the Lambda package, which ships
only `house/` + `test/`) would fail to import. So:

- `tournament_core.py` imports `house/` and `test/` explicitly (always present).
- Contenders are **discovered dynamically** at import: `_discover_contenders()`
  walks `bots/contenders/*.py`, skips `_*.py` helper modules, and registers the
  `PlayerInterface` subclass each file defines as `tb-<filename>`. If the folder
  is absent, it returns nothing — the registry is just the house roster.

A contender named `Foo.py` (class `Foo`) therefore registers as `tb-Foo` locally
and simply doesn't exist in a clean clone or in production.

## Registration & naming

- Registry names carry a `tb-` prefix. Submitted bot names can't contain hyphens
  (site + Lambda validation), so the prefix can't be impersonated.
- Only `house/` + `test/` names are **reserved** (`RESERVED_NAMES` in the Lambda
  handler). Contender names are *not* reserved — they're local-only and mustn't
  block legitimate submissions.

## Conventions

- One `PlayerInterface` subclass per bot file; helper/shared code goes in
  `_*.py` modules (ignored by discovery). Contender data (e.g.
  `endgame_table.json`) lives in `contenders/` too.
- A contender may optionally define a module-level `BOT_INFO` dict (author /
  model / note / year); discovery merges it into the leaderboard provenance.
