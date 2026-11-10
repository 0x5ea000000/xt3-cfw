# Firmware recipes

| File | Makes | From |
| --- | --- | --- |
| `recipes/firmware.json.xz` | the firmware image (P05b): 16 example rows, Classic Negative, Bleach Bypass, FX Blue, large grain (SHA-256 `8c4c5b93…5b90`) | FujiMod's X-T3 5.11 recovery `ffboot.bin` (`f6663dda…57df`) and Fujifilm's X-T4 2.12 `FWUP0024.DAT` (`853d273b…3bc5`), read only |
| `recipes/fast-loader.json.xz` | the fast SD loader before its data fields (`46830992…5d5d`) | FujiMod's recovery `ffinit.bin` (`c51adc52…0808`) |

Use them through `tools/xt3_build.py`; `python3 tools/xt3_build.py info` prints what a recipe holds. Each is LZMA-compressed JSON (`format: xt3-recipe-1`): a base, a pinned target, the pinned card files, and a list of steps (`own`, `copy`, `icons`, `x4copy`, `x4derive`; see `docs/how-it-works.md`).

The camera-tested card files, as every build must produce them:

| File | SHA-256 |
| --- | --- |
| `fast/ffboot.bin` | `be9598d48d8dc9c00161c17fec8a835983b94cb6d19e7cf50bfd640397011e96` |
| `fast/ffinit.bin` | `af22c0ff21db99fd2f773fe396e07e42721e27a82adddb9dd92e8a7a3ba230b8` |
| `standard/ffboot.bin` | `8c4c5b931d3ccef1dd71f44bb38c2691b1e7bb502465d1ddfff2830903875b90` |
| `standard/ffinit.bin` | `2d60c5030f8c09896adcffc902947302fe52f39ef802372c834d0d266ede1264` |
