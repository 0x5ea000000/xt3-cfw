# xt3-cfw

Custom firmware (cfw) for the Fujifilm X-T3: your own film simulations as extra rows in the camera's FILM SIMULATION menu. It runs from the SD card, on top of Fujifilm's official 5.11 firmware. Nothing is flashed.

- **16 extra rows** after the stock films, each with its own name, description and film-canister icon, in the film list, the Q menu and the I.Q. menu.
- Each row is a **colour table** (16×16×16) applied to JPEGs and live view. Live view previews a row while you highlight it.
- **RAW CONVERSION** in the camera lists the rows too.
- **Photos remember their row**: the row's icon shows on playback and on the shooting info screens, and an in-camera RAW conversion of a row photo uses that row.
- **Palette**, a local web app, fits a look from your own photos (camera JPEGs and the same RAWs exported with your Lightroom profile) and makes the card files.
- **Fast SD boot**: about 5 seconds from power-on to the shooting screen (a standard card takes about 95 s).

Status: tested on one X-T3 with official 5.11 inside. See [what has been tested](#tested) before you rely on it.

## What you need

1. A Fujifilm **X-T3** on official firmware **5.11**.
2. **FujiMod's X-T3 5.11 recovery SD boot zip** (https://fujimod.com/recovery/). Make it on FujiMod's site from Fujifilm's own 5.11 firmware download. It holds the official firmware image and FujiMod's SD-boot loader. This repository contains no Fujifilm or FujiMod files; the build checks yours by SHA-256 and refuses anything else.
3. Python 3.10 or newer. The firmware build uses the standard library only.

## Build the card files

```sh
python3 tools/xt3_build.py build path/to/fujimod-recovery-sd-boot-x-t3-5.11.zip build
```

It rebuilds the tested firmware from your zip and checks every output against its pinned SHA-256:

| Folder | Boots in | Files |
| --- | --- | --- |
| `build/fast/` | about 5 s | `ffboot.bin`, `ffinit.bin` |
| `build/standard/` | about 95 s | `ffboot.bin`, `ffinit.bin` |

Copy `ffboot.bin` first, then `ffinit.bin`, to the top folder of an empty card (exFAT or FAT32, formatted in the camera). Power on holding **Fn1** and pressing the **rear command dial**. Without the card, or without the buttons, the camera starts its own firmware as usual.

The built firmware has 16 example rows: NEUTRAL 1 and 2 (no change) and 14 test tints (TEST RED … TEST FLAT). They show that everything works. Your own looks come from Palette.

## Palette: your own looks

```sh
python3 palette/run.py
```

Open http://127.0.0.1:8877. Palette runs on your computer only. The first run sets up `palette/.venv`. It needs the firmware built first (above). The photo workflow is in [docs/palette-guide.md](docs/palette-guide.md): 30 to 50 RAWs from your X-T3, exported once as PRO Neg. Std and once with your Lightroom profile.

## How it works

The build starts from your official image and applies a recipe in `firmware/recipes/`. The recipe holds only our own bytes: the hooks, our code and data, and the colour tables. Where our film lists reuse rows from official menus, the recipe holds a "copy these bytes from your image" step instead of the bytes. Row icons are drawn at build time from stock icons in your image, with Lato Bold letters. The result must equal the camera-tested firmware byte for byte, or nothing is written. Details: [docs/how-it-works.md](docs/how-it-works.md).

## Tested

| What | Evidence |
| --- | --- |
| Boots; 16 rows with names, descriptions and icons; live preview; photos; RAW CONVERSION | camera, official 5.11 inside, standard and fast card |
| Row icons on playback and shooting info screens; photos marked with their row; RAW CONVERSION of a row photo as its row | camera |
| Palette builds with fewer rows (9 looks) | camera |
| Every output of `tools/xt3_build.py` equals the tested files | checked on every build |
| Fast loader on cards with files in pieces (exFAT, FAT32) | emulator |

Not there yet: Classic Negative, Bleach Bypass, large grain.

## Safety

Read [SAFETY.md](SAFETY.md) first. In short: SD boot only, never flash anything as a test, keep FujiMod's recovery card at hand. You use this at your own risk.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests are reviewed and merged by the maintainer.

## Licence

MIT, see [LICENSE](LICENSE). It covers this project's own code, documents and recipes. Lato Bold in `fonts/` is under the SIL Open Font Licence (`fonts/OFL.txt`). Fujifilm's firmware and FujiMod's files are not part of this repository and are not covered by it.

Fujifilm, X-T3 and the film simulation names are Fujifilm's. This project is not affiliated with Fujifilm.

## Credits

- **[FujiMod](https://github.com/justjake/fujimod)**: SD boot on Fujifilm cameras, and the X-T3 recovery card this builds on.
- **Haipro**: the initial custom firmware work on the X-T3.

Our cfw builds on, and continues to incorporate, the research and work they started.
