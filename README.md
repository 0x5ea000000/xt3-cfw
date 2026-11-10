# xt3-cfw

Custom firmware (cfw) for the Fujifilm X-T3: your own film simulations as extra rows in the camera's FILM SIMULATION menu. It runs from the SD card, on top of Fujifilm's official 5.11 firmware. Nothing is flashed.

- **16 extra rows** after the stock films, each with its own name, description and film-canister icon, in the film list, the Q menu and the I.Q. menu.
- Each row is a **colour table** (16×16×16) applied to JPEGs and live view. Live view previews a row while you highlight it.
- **RAW CONVERSION** in the camera lists the rows too.
- **Photos remember their row**: the row's icon shows on playback and on the shooting info screens, and an in-camera RAW conversion of a row photo uses that row.
- **Palette**, a local web app, fits a look from your own photos (camera JPEGs and the same RAWs exported with your Lightroom profile) and makes the card files.
- **Fast SD boot**: about 5 seconds from power-on to the shooting screen (a standard card takes about 95 s).
- **Classic Negative** and **Eterna Bleach Bypass** as two more films, with their own names (in all 35 camera languages), descriptions and icons, in the film list, the Q menu, playback and RAW CONVERSION.
- **Color Chrome FX Blue** (OFF / WEAK / STRONG) in IMAGE QUALITY SETTING, and **large grain** (STRONG / LARGE, WEAK / LARGE) in GRAIN EFFECT.

Status: tested on one X-T3 with official 5.11 inside. See [what has been tested](#tested) before you rely on it.

## What you need

1. A Fujifilm **X-T3** on official firmware **5.11** (MENU > SET UP > USER SETTING > VERSION shows it). Nothing gets installed on it.
2. **FujiMod's X-T3 5.11 recovery SD boot zip.** Go to https://fujimod.com/recovery/, pick X-T3 and 5.11, and follow the page: it makes the zip from Fujifilm's own X-T3 5.11 firmware. You get a file like `fujimod-recovery-sd-boot-x-t3-5.11-build-….zip`.
3. **Fujifilm's X-T4 firmware 2.12** (`FWUP0024.DAT`), a free download: open Fujifilm's [X-T4 firmware page](https://www.fujifilm-x.com/global/support/download/firmware/cameras/x-t4/), accept the licence, and download Ver. 2.12 (direct file: https://dl.fujifilm-x.com/support/firmware/x-t4-212-79jwnwyy/FWUP0024.DAT). The build only *reads* it: Classic Negative, Bleach Bypass, FX Blue and large grain use Fujifilm's own values, names and icons, which come from this file. **Never put this file on your X-T3's card or try to install it.**
4. Python 3.10 or newer. The firmware build uses the standard library only.

Put both downloads in one folder, for example `inputs/`. This repository contains no Fujifilm or FujiMod files: the build checks yours by SHA-256 and refuses anything else.

## Build the card files

```sh
python3 tools/xt3_build.py build inputs/fujimod-recovery-sd-boot-x-t3-5.11-build-*.zip build --x4 inputs/FWUP0024.DAT
```

It rebuilds the tested firmware from your two files and checks every output against its pinned SHA-256 (a few seconds):

| Folder | Boots in | Files |
| --- | --- | --- |
| `build/fast/` | about 5 s | `ffboot.bin`, `ffinit.bin` |
| `build/standard/` | about 95 s | `ffboot.bin`, `ffinit.bin` |

Copy `ffboot.bin` first, then `ffinit.bin`, to the top folder of an empty card (exFAT or FAT32, formatted in the camera). Power on holding **Fn1** and pressing the **rear command dial**. Without the card, or without the buttons, the camera starts its own firmware as usual.

The built firmware has 16 example rows: NEUTRAL 1 and 2 (no change) and 14 test tints (TEST RED … TEST FLAT). They show that everything works. Your own looks come from Palette.

Before you start the camera without the card, set FILM SIMULATION to a stock film (for example PROVIA), GRAIN EFFECT to a stock value and COLOR CHROME FX BLUE to OFF. Official firmware does not know Classic Negative, Bleach Bypass, large grain or FX Blue; a photo setting it does not know most likely falls back to PROVIA, but that has not been tested in every menu.

## Optional: start without buttons

For people willing to flash: a small **flash stub** on official 5.11 makes a normal power-on start the card, with no Fn1 + rear dial.
It is the only part of this project that flashes the camera. `python3 tools/xt3_build.py stub inputs/FWUP0019.DAT build-stub`
makes it from Fujifilm's X-T3 5.11 file. Read [docs/optional-flash-stub.md](docs/optional-flash-stub.md) first: it has the
recovery route and the way back.

## Palette: your own looks

```sh
python3 palette/run.py
```

Open http://127.0.0.1:8877. Palette runs on your computer only. The first run sets up `palette/.venv`. It needs the firmware built first (above). The photo workflow is in [docs/palette-guide.md](docs/palette-guide.md): 30 to 50 RAWs from your X-T3, exported once as PRO Neg. Std and once with your Lightroom profile.

## How it works

The build starts from your official image and applies a recipe in `firmware/recipes/`. The recipe holds only our own bytes and the cfw's code: the hooks, code and data, and the colour tables. Where the firmware reuses Fujifilm bytes (rows from official menus, and the X-T4's Classic Negative, Bleach Bypass, FX Blue and large-grain values, names and icons), the recipe holds a "copy these bytes from your file" step instead of the bytes, or computes the table from your X-T4 file's values. Row icons are drawn at build time from stock icons in your image, with Lato Bold letters. The result must equal the camera-tested firmware byte for byte, or nothing is written. Details: [docs/how-it-works.md](docs/how-it-works.md).

## Tested

| What | Evidence |
| --- | --- |
| Boots; 16 rows with names, descriptions and icons; live preview; photos; RAW CONVERSION | camera, official 5.11 inside, standard and fast card |
| Row icons on playback and shooting info screens; photos marked with their row; RAW CONVERSION of a row photo as its row | camera |
| Classic Negative, Bleach Bypass, FX Blue, large grain on official 5.11 inside (fast card) | camera: works as on the cfw (one camera, steps not itemised) |
| Their names in English, Japanese, German, Finnish and Russian; their icons; colour processing equal to the cfw's | emulator |
| Palette builds with fewer rows (9 looks) | camera (on the previous firmware) |
| Every output of `tools/xt3_build.py` equals the tested files | checked on every build |
| Fast loader on cards with files in pieces (exFAT, FAT32) | emulator |
| Optional flash stub on official 5.11: normal power-on starts the card | camera (installed on one X-T3); 13 start-up cases in the emulator |

Not tested yet: starting the camera without the card after leaving Classic Negative, Bleach Bypass, large grain or FX Blue selected (see above).

## Safety

Read [SAFETY.md](SAFETY.md) first. In short: SD boot only, never flash anything as a test, keep FujiMod's recovery card at hand. You use this at your own risk.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests are reviewed and merged by the maintainer.

## Licence

MIT, see [LICENSE](LICENSE). It covers this project's own code, documents and recipes. Lato Bold in `fonts/` is under the SIL Open Font Licence (`fonts/OFL.txt`). Fujifilm's firmware (X-T3 and X-T4) and FujiMod's files are not part of this repository and are not covered by it.

Fujifilm, X-T3 and the film simulation names are Fujifilm's. This project is not affiliated with Fujifilm.

## Credits

- **[FujiMod](https://github.com/justjake/fujimod)**: SD boot on Fujifilm cameras, and the X-T3 recovery card this builds on.
- **[0x5ea000000(haipro287)](https://github.com/0x5ea000000)**: the initial custom firmware work on the X-T3, including the Classic Negative, Bleach Bypass, Color Chrome FX Blue and large-grain code this firmware carries, shared with his permission.

Our cfw builds on, and continues to incorporate, the research and work they started.
