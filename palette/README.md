# Palette

Web app for adding, comparing and building custom looks for the X-T3 SD boot firmware.
Formerly called Look Lab (renamed 2026-11-08); older logs, build READMEs and research notes use that name.

```bash
python3 palette/run.py
```

Serves `http://127.0.0.1:8877`, on your own computer only (set `PALETTE_HOST` or `PALETTE_PORT` to change it). First run creates `.venv` from `requirements.txt`.

## What it does

| Page | Purpose |
| --- | --- |
| Film list | Choose up to 16 looks and their order, then build card files |
| Looks | Library. Add a look from a Lightroom `.xmp`, follow its checklist, fit, read the report |
| Compare | Drag between plain base, table and Lightroom on all 48 photos, across looks |
| Card | Read `ffboot.bin` and `ffinit.bin` in the browser: which looks, whether the copy is complete, whether the build is flagged. Understands the small fast pair (any loader) and the full older pair |
| Builds | History, download, go back, record the camera result |

## Rules it enforces

- **Data only.** A build is the approved engine image with the store (tables and icons), the store's sum word, the icon records, row text (names in the film-name style, `name_style` 2) and, to show fewer rows, list terminators replaced. RAW CONVERSION's list copy (`raw_list` in `engine.json`) keeps its keys and rows in step; any extra rows in it move up to follow the last shown row. `engine.check_diff` compares every byte and refuses a change anywhere else.
- **Engine: P03**, the official X-T3 5.11 image with our 16 rows, made by `tools/xt3_build.py` into `build/` (`b8a254d5…`). Build it first.
- **The store sum follows the tables.** The camera checks it on every shot and turns the row cyan if it is wrong, so each build verifies it before writing anything.
- **Rule 3 at startup.** The app reads the engine image's own 16 rows, with their icons, out of the image, rebuilds it and requires byte equality, or it will not build.
- **No DAT path, no card writes.** It produces two files for the user to copy. A test fails if a DAT or device path appears in the code.
- **Exports are checked before fitting**: all 48 names, Look name and Amount, profile, sliders, white balance, crop, lens, grain, and duplicates of another look's files.

Evidence labels still apply: a fit score is a software prediction. Only "Score it on the camera" and the user's report on a build are `camera` evidence, and only the user's reports go in `HARDWARE_LOG.md`.

## Files

| Path | Kept in git | What |
| --- | --- | --- |
| `engine.py`, `engine/engine.json` | yes | Pinned approved image, data ranges, patching, checks, card read-back |
| `builds.py` | yes | Build, verify, history, card inspection |
| `exports.py`, `quality.py` | yes | Export checks, plain-language fit reading |
| `jobs.py`, `samples_worker.py`, `score_worker.py` | yes | Background fit, comparison images, camera scoring |
| `library/` | yes | One folder per look: `look.json`, table, fit report. `rows.json` |
| `data/` | no | Comparison images and card builds. Regenerates, except each build's recorded camera result |

Fitting reuses `research/claude-look-fit/` unchanged. `PRO Neg. Std` renders are in `sample_photos/pro-neg-std/`. A new base film needs a new engine decision.

## Checks

```bash
palette/.venv/bin/python -m unittest discover -s palette/tests
```

`tests/browser_walkthrough.py` drives the real pages with Playwright against an isolated instance. Start one with `PALETTE_LIBRARY`, `PALETTE_DATA` and `PALETTE_PHOTOS` pointing at scratch folders on port 8878, with symlinks to the RAFs and base renders. It removes and re-adds Noritsu through the page; the resulting table must hash to `a8a492bd...89cf`.

## Limits

- 16 rows, 80 table slots. The other 64 slots are unused for now.
- Any row returns as Row 1 after power-off. Row order is under your control, so Row 1 is the one to choose with care.
- Every new build starts as "Not tested on camera", even though only data differs. The camera has run the full 16 row list; shorter lists have run in the emulator (8 rows), not on the camera.
- Name 12 characters, description lines 28, plain ASCII. Both limits were drawn in the emulator at full length with typical letters.
- Icons are one big and one small character, A to Z or 0 to 9, on Fujifilm's canister shape. A look without a chosen icon uses a suggestion from its camera name. `tools/film_icons.py` makes them from the stock templates in the built official image, with the bundled Lato Bold (`fonts/`).
- Photos record a row number for playback. Reorder rows and older photos show the icon now on that row.
- The film-list scores are software predictions. Use "Score it on the camera" to measure a look.

The camera has the flashed stub, so a card with Palette's `ffinit.bin` and `ffboot.bin` boots at a normal power-on, with no buttons. A card without them boots the internal firmware.
