# Making a look with Palette

Palette turns a Lightroom look into a custom film row on your X-T3. It learns the look from photo pairs: the camera's own **PRO Neg. Std** rendering of each RAW ("before") and the same RAW with your look applied in Lightroom ("after"). It fits a 16×16×16 colour table that turns one into the other, and puts that table on a row.

You bring your own photos. Nothing here ships photos, and nothing you add leaves your computer.

## What you need

- An X-T3 and 30 to 50 RAW photos (`.RAF`) you shot with it.
- **FUJIFILM X RAW STUDIO** (free, from Fujifilm; it needs the camera connected by USB), or the camera's own **RAW CONVERSION** menu.
- **Adobe Lightroom Classic**, and the look you want, as a Lightroom **Look** or preset (`.xmp`).
- Palette running: `python3 palette/run.py`, then open http://127.0.0.1:8877.

No grey card or colour chart is needed. The fit learns from whatever colours are in your photos.

## 1. Choose the photos

The table only learns colours that appear in your photos. Anything missing is filled in by smoothing, so variety matters more than count. About 30 varied photos is enough; past 50, more stop helping.

Cover as many of these as you can, one or two photos each:

| Area | Examples |
| --- | --- |
| Skin | different skin tones; daylight and shade |
| Greens | foliage in sun and in shade, grass, a backlit leaf |
| Blues | clear sky, evening sky, water, blue objects |
| Warm | golden hour, sunset, autumn leaves, wood, brick |
| Light sources | indoor tungsten, LED or fluorescent, mixed light, night streets or neon |
| Strong colours | flowers, signs, fruit, fabric: red, magenta, yellow, cyan, purple, teal |
| Neutrals | white walls, paper, concrete, clouds, snow |
| Tone range | a bright high-key scene, a dark low-key scene, a backlit scene, a flat overcast scene |

Avoid blown highlights. Pixels at the top of the range are left out of the fit, so a mostly clipped photo teaches nothing. Any lens and any film simulation at shooting time are fine, because both conversions below set their own.

Put the RAWs in `sample_photos/` at the top of the repo, for example `sample_photos/DSCF0412.RAF`. Keep the camera's filenames; every other file is matched to them by name.

## 2. Make the "before" set: PRO Neg. Std

Convert every RAW with **X RAW Studio** (or in the camera with **RAW CONVERSION**) using:

| Setting | Value |
| --- | --- |
| Film simulation | PRO Neg. Std |
| Dynamic range | DR100 |
| Color Chrome Effect | Off |
| White balance | As shot |
| Exposure, tone, colour, sharpness, noise reduction | Unchanged (0) |
| Grain | Off |
| Output | JPEG, full size |

Save the JPEGs to `sample_photos/pro-neg-std/`, with the same filename as each RAW: `DSCF0412.RAF` → `sample_photos/pro-neg-std/DSCF0412.jpg`.

These are the settings the table is made for. On the camera, use the custom row with **DR100 and Color Chrome Off** too: other settings change the colours before the table sees them.

## 3. Add the look in Palette

Open **Looks** → add a look, and drop your `.xmp` preset or Look on the page. Palette reads its name from the file. Then fill in:

- **Lightroom Look name**: as it appears in Lightroom. Palette uses it to check your exports.
- **Name on the camera**: up to 12 characters (letters, digits, space and `. + / & ' -`), as it will appear in the film list.
- **Three description lines**: up to 28 characters each, shown on the camera under the name.

The look page then shows the folder for its exports: `sample_photos/lightroom_<look>/`.

## 4. Make the "after" set in Lightroom

Import the **same RAWs** into Lightroom Classic. Select them all and apply the look, with nothing else changed:

| Setting | Value |
| --- | --- |
| Profile | your look (.xmp profile), Amount 100 |
| White balance | As Shot |
| Exposure, contrast, all tone and colour sliders | 0 |
| Lens corrections (profile, distortion, chromatic aberration) | **Off** |
| Crop, straighten, transform | None |
| Grain, vignette, local adjustments, masks | None |

Export them:

| Export setting | Value |
| --- | --- |
| Format | JPEG, quality 100 |
| Colour space | sRGB |
| Size | long edge 3240 pixels |
| Metadata | **All** (Palette reads the settings from it) |
| Filename | unchanged (`DSCF0412.jpg`) |

Save them to the folder the look page shows, or drop them on the page.

**Most common mistake: lens corrections.** They bend the image, so the before and after pixels no longer line up, and the colours smear. Palette realigns by a couple of pixels only. Turn them off before exporting.

## 5. Check and fit

On the look page, **Check the exports**. Palette reads each JPEG's Lightroom metadata and refuses or warns on:

- a missing photo, or a filename that does not match a RAW;
- a different Look, Amount other than 100, or a profile other than Adobe Standard v2;
- moved sliders, or white balance other than As Shot;
- a crop; lens corrections, grain or vignette left on;
- photos too small, or exported without metadata.

Fix what it lists, check again, then **Fit this look**. It takes a few minutes. The look page then shows how close the table gets on photos it did not train on (lower is closer), and **Compare** shows before, table and Lightroom side by side for every photo.

## 6. Put it on the camera

On **Film list**, add the look to a row, order the rows, and **Build**. Download the card files: **fast SD boot** (about 5 s) or **standard SD boot** (about 95 s). The looks are the same either way. Copy `ffboot.bin` and `ffinit.bin` to the top folder of the card, and follow the steps Palette shows under the build. Read [SAFETY.md](../SAFETY.md) before your first card.

Then shoot five or so scenes on the new row and compare them with Lightroom: the look page has a **camera check** for exactly that.

## Paid presets and profiles

A table fitted from a paid preset or profile counts as made from it. You may use it on your own camera. Do not share it, post it, or contribute it to this repo. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## Folder layout

```
sample_photos/
  DSCF0412.RAF                     your RAWs
  pro-neg-std/DSCF0412.jpg         step 2, X RAW Studio or the camera
  lightroom_<look>/DSCF0412.jpg    step 4, Lightroom, one folder per look
```

`sample_photos/`, `palette/library/` (your looks) and `palette/data/` (builds) are ignored by git. To keep them elsewhere, set `PALETTE_PHOTOS`, `PALETTE_LIBRARY` and `PALETTE_DATA` before starting Palette.
