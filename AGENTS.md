# Working rules (people and coding agents)

This repository adds film rows to the Fujifilm X-T3, firmware 5.11, by SD boot. `CLAUDE.md` imports this file.

## Non-negotiable

1. **SD boot only.** Never flash a DAT, and never ask anyone to, as a test step. Never write to SD cards, USB devices or cameras from a tool or an agent: people do all hardware steps.
2. **No Fujifilm or FujiMod bytes in git.** Inputs come from the user's FujiMod recovery zip, checked by SHA-256 (`tools/xt3_build.py`). Recipes hold our own bytes, copy steps from the user's image, and icons drawn at build time.
3. **Byte-exact and guarded.** Rebuild the known-good result before changing anything; check old bytes before patching; pin every output's SHA-256; refuse on any mismatch.
4. **Decode what you assemble.** Assemblers have silently mis-encoded far `adr` and branches after data. Check every branch, `ldr pc` literal and `adr` target against the intended address. Keep code before data.
5. **Rows store PRO Neg. Std** plus a RAM-only marker, so a normal boot never sees an unknown film value.
6. **Label evidence**: `camera`, `emulator` or `static`. Only camera reports count as a pass.
7. **Private material stays out**: personal paths, email addresses, photos, paid looks or anything fitted from them.

## Layout

| Path | What |
| --- | --- |
| `tools/xt3_build.py` | Builds the card files from the user's recovery zip and a recipe; checks everything |
| `tools/film_icons.py`, `tools/gvff.py` | Row icons: stock canister templates from the image, Lato Bold letters |
| `firmware/recipes/` | The tested firmware as a recipe (`firmware.json.xz`) and the fast loader (`fast-loader.json.xz`) |
| `palette/` | Local web app: fit looks from photos, build card files (data only, never code) |
| `research/` | The look-fitting model Palette runs |
| `docs/` | How it works, Palette guide |
| `tests/` | Recipe tests (no firmware needed) |

## Checks

```sh
python3 tools/repo_check.py
python3 -m unittest discover -s tests
palette/.venv/bin/python -m unittest discover -s palette/tests      # after a build; skipped without one
```
