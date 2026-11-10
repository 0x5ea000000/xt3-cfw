# Optional: start the card without buttons (flash stub)

**Optional, and the only part of this project that flashes the camera.** Everything else runs from the card and leaves the camera
untouched. If you are not comfortable flashing firmware, skip this page: holding Fn1 and pressing the rear dial at power-on works
just as well.

With the stub installed, a **normal power-on with the card files in** starts the card (about 5 s with the fast files). Without the
card, or without `ffinit.bin` on it, the camera starts official 5.11 as usual.

## What it is

Fujifilm's official X-T3 5.11 firmware file with three small changes, nothing else, and nothing recompressed:

| Change | Where (flash) | Size |
| --- | --- | --- |
| the stub: looks for `ffinit.bin` on the card and starts it, else continues the normal start | `0x7300`, blank flash | 408 bytes |
| one literal so the start-up code enters the stub | `0x8A0` | 4 bytes |
| the file's global checksum | header | 4 bytes |

| File | SHA-256 |
| --- | --- |
| input: Fujifilm's X-T3 5.11 `FWUP0019.DAT` | `9f2c75fd8a16a1d71b9218f6dbd3144b1f11820bcecd3a9608c8cda9f25f95a3` |
| output: the stub `FWUP0019.DAT` | `42377df7f563e59f08d2547274c14cec4c8d0a93fbd02f01979bbf6f0cab050a` |

## Tested

- **Camera:** this exact file installed on one X-T3 (2026-11-10): works. The same 408 stub bytes ran before on two other bases.
- **Emulator:** 13 start-up cases: card and files; no card; no `ffinit.bin`; no `ffboot.bin`; bad data in `ffboot.bin`; every flash
  mode; the camera's second core. Every failure falls back to the normal start.
- **Not tested:** recovering from a broken stub (never needed). The camera's ROM chooses the card route before it reads flash, so
  FujiMod's recovery card should still work.

## Make it

1. Download Fujifilm's **X-T3 firmware 5.11** from Fujifilm's [X-T3 firmware page](https://www.fujifilm-x.com/global/support/download/firmware/cameras/x-t3/)
   (accept the licence; direct file: https://dl.fujifilm-x.com/support/firmware/x-t3-511-t3j28rmw/FWUP0019.DAT). It is the same
   file FujiMod's recovery page asks for.
2. ```sh
   python3 tools/xt3_build.py stub inputs/FWUP0019.DAT build-stub
   ```
   It checks your file, applies the three changes, and refuses to write anything unless the result is exactly the tested file
   (`build-stub/FWUP0019.DAT`, SHA-256 above).

## Before you flash

1. **A recovery card**, separate from your everyday card: the three files of FujiMod's X-T3 5.11 recovery zip in its top folder.
   Prove it boots with Fn1 + rear dial. Do not run the update from it.
2. **A fully charged battery.** Power loss during an update is the worst case.
3. **Your everyday card** with `build/fast/ffboot.bin` and `ffinit.bin`, working with the button hold.
4. **Fujifilm's official `FWUP0019.DAT`** kept on your computer: it is the way back.

## Flash

5. Copy `build-stub/FWUP0019.DAT` to the top folder of a card that has **no** `ffinit.bin` or `ffboot.bin`. Check its SHA-256.
6. Run the camera's firmware update (power on holding DISP/BACK, or the update menu). Keep the camera still; do not open a door or
   power off until it has finished.
7. Power off. Delete `FWUP0019.DAT` from the card.

## After

Normal power-on, **no buttons**:

| Test | You see | Meaning |
| --- | --- | --- |
| Everyday card in | the extra rows and films, in about 5 s | **The stub works** |
| | the stock film list, about 2 s | the stub did not take; nothing is harmed |
| | a hang (lamp on, or black) | battery out, card out, power on with no card |
| No card | official 5.11, normal | good |
| | a hang | see below |

## If the normal start is dead

Insert the recovery card, hold Fn1 and the rear dial, power on, and keep holding until the lamp lights. Let go, then hold DISP/BACK
until the update screen appears (80 s or more). Run the update: it installs official 5.11 without the stub.

## Going back

Install Fujifilm's official `FWUP0019.DAT` the same way, from a card without `ffinit.bin`, so the stub does not start the card first.
