# How it works

## Booting from the card

The X-T3's boot ROM can start firmware from the SD card: `ffinit.bin` (a loader) reads `ffboot.bin` (the firmware image) into memory and starts it. FujiMod made this usable. Its recovery card is official 5.11 plus five bytes that enable the card start. Holding Fn1 and pressing the rear dial at power-on chooses the card. Nothing is written to the camera.

The **fast loader** is our replacement for the slow read. It drives the SD controller directly (multi-block DMA at high speed), follows a file stored in pieces (exFAT and FAT32), and skips the image's long stretches of zeros, which are listed in a segment table inside `ffinit.bin`. Boot drops from about 95 s to about 5 s. It checks a sampled sum of what it read, and on any problem falls back to the ROM's own read.

## What the firmware adds

All of it lives in memory that official firmware leaves unused (a 104 KiB room at `0x1509000`, typed as code up to `0x151A000` and read-write above), plus a store appended after the image for tables and icons.

- **Film rows.** The four film lists (film menu, Q menu, I.Q. menu, the custom-setting editor) get 16 more entries. Choosing one stores PRO Neg. Std plus a RAM-only marker; the colour pipeline then applies that row's 16×16×16 table to JPEGs and live view, which official firmware already supports but leaves at identity.
- **Text and icons.** Official text and icon lookups reject ids past their own range. Small wrappers answer our ids (names, descriptions, sizes, style overrides) and pass every other id to the official code unchanged.
- **RAW CONVERSION** lists the rows and develops with the chosen row's table.

## The recipe

`firmware/recipes/p02f.json.xz` turns the official image into the tested firmware with three kinds of step:

| Step | Holds |
| --- | --- |
| `own` | our bytes: hooks on official code (with the SHA-256 of the official bytes they replace), our code and data, the colour tables |
| `copy` | "copy n bytes from this address of your image to that one": where our lists reuse official menu rows |
| `icons` | the row icons, drawn from five stock icons in your image with Lato Bold letters |

`tools/xt3_build.py` applies it and requires the result's SHA-256 to equal the camera-tested image. The standard loader is FujiMod's with its size and checksum fields set. The fast loader is `fast-loader.json.xz` applied to FujiMod's loader, then given this image's segment table and check value. All four card files are pinned.

## Palette

Palette changes data only: the colour tables, the icons, the row text, the store's checksum word, and list terminators to show fewer rows. It refuses any change outside those ranges, so the code stays the tested code.
