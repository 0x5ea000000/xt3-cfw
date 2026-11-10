# Safety

These rules come from real failures while building this. They are not optional.

1. **SD boot only. Never flash a firmware file as a test step.** During development one test firmware file bricked a camera, and recovery needed FujiMod's recovery SD card. Everything here runs from the card and leaves the camera's own firmware untouched. The one exception is optional: the flash stub ([docs/optional-flash-stub.md](docs/optional-flash-stub.md)), the exact camera-tested file, made by the build tool from Fujifilm's own firmware and installed by you with the camera's updater.
2. **Keep a recovery route.** Have FujiMod's X-T3 recovery SD card ready, and know how to boot it.
3. **Use only what the build checked.** `tools/xt3_build.py` refuses any input or output whose SHA-256 does not match. Do not edit `ffboot.bin` or `ffinit.bin` by hand. Check the files on the card against `build/SHA256SUMS` after copying.
4. **Rows store a stock film; the extra films and settings do not.** Choosing one of the 16 rows saves PRO Neg. Std plus a marker that lives only in memory, so a normal start (no card) only ever sees a stock film. Classic Negative, Bleach Bypass, large grain and FX Blue are saved as values official firmware does not know. Before you start without the card, set a stock film, a stock grain value and FX BLUE OFF (official most likely treats an unknown film as PROVIA, but that is not tested in every menu).
5. **Label evidence honestly**: `camera` (seen on an X-T3, with file hashes), `emulator`, or `static` (reading the code). Only camera reports count as a pass.

## If the camera misbehaves

| Step | Do | Fixes |
| --- | --- | --- |
| 1 | Power off, take the battery out for 10 s, power on without the card | Most freezes; the camera's own firmware starts as usual |
| 2 | Copy `ffboot.bin` and `ffinit.bin` again and check their SHA-256 | A bad copy |
| 3 | Go back to the last card that worked | A bad build |
| 4 | FujiMod's recovery SD card | A camera that does not start |

## Before your first card

- Your camera's own firmware should be official **5.11**. Other versions are refused by the build (the input check) and must not be mixed with these card files.
- Use a card formatted in the camera.
- A fast boot that takes 20 s or more means `ffboot.bin` is stored in pieces on the card and the loader took its slow route. Delete both files and copy them again.
