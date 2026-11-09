# Firmware recipes

| File | Makes | From |
| --- | --- | --- |
| `recipes/p02f.json.xz` | the firmware image, 16 example rows (SHA-256 `09185227…3ba8`) | FujiMod's X-T3 5.11 recovery `ffboot.bin` (`f6663dda…57df`) |
| `recipes/fast-loader.json.xz` | the fast SD loader before its data fields (`46830992…5d5d`) | FujiMod's recovery `ffinit.bin` (`c51adc52…0808`) |

Use them through `tools/xt3_build.py`; `python3 tools/xt3_build.py info` prints what a recipe holds. Each is LZMA-compressed JSON (`format: xt3-recipe-1`): a base, a pinned target, the pinned card files, and a list of `own`, `copy` and `icons` steps (see `docs/how-it-works.md`).

The camera-tested card files, as every build must produce them:

| File | SHA-256 |
| --- | --- |
| `fast/ffboot.bin` | `e2497e18a5e03a022d77a291086af2cbbef6957b6d8c09065ec357d852b56672` |
| `fast/ffinit.bin` | `a32b41d0d350926f633845555bc8088bd6361f85815c1b3611cb1310d3641604` |
| `standard/ffboot.bin` | `091852273e19849de0f772578dd51ca77718f36d127f44ed1911e223029b3ba8` |
| `standard/ffinit.bin` | `527088af273d9253a956d8d75b2f5bb12f780bce33e4eeed598d10fb76b6af6f` |
