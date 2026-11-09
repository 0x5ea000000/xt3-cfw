# Firmware recipes

| File | Makes | From |
| --- | --- | --- |
| `recipes/firmware.json.xz` | the firmware image (P03), 16 example rows (SHA-256 `b8a254d5…b08f`) | FujiMod's X-T3 5.11 recovery `ffboot.bin` (`f6663dda…57df`) |
| `recipes/fast-loader.json.xz` | the fast SD loader before its data fields (`46830992…5d5d`) | FujiMod's recovery `ffinit.bin` (`c51adc52…0808`) |

Use them through `tools/xt3_build.py`; `python3 tools/xt3_build.py info` prints what a recipe holds. Each is LZMA-compressed JSON (`format: xt3-recipe-1`): a base, a pinned target, the pinned card files, and a list of `own`, `copy` and `icons` steps (see `docs/how-it-works.md`).

The camera-tested card files, as every build must produce them:

| File | SHA-256 |
| --- | --- |
| `fast/ffboot.bin` | `643350779ae05a4de34a923807b89fd30083572103547d93a061dac3c5c35139` |
| `fast/ffinit.bin` | `528d1bafca19a1ca06b1a9947b0c409e2a008524de941d15f674f8b0abeeeae6` |
| `standard/ffboot.bin` | `b8a254d55f0e7cf886736d0752bbf447d4ca12f28451e0aaf1a115af6bebb08f` |
| `standard/ffinit.bin` | `12daa41998dd20ba14dc65202f91994dde9371c115f225478d5eba8e9630f7eb` |
