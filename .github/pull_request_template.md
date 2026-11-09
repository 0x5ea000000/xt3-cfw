## What this changes

<!-- One change per pull request. A firmware feature is a new numbered test with builds/<nn>-<name>/README.md. -->

## Evidence

<!-- Label each claim: camera (seen on an X-T3, with the exact file hashes), emulator, or static (reading the code). -->

- [ ] camera:
- [ ] emulator:
- [ ] static:

## Checklist

- [ ] No firmware files (DAT, ffboot.bin, ffinit.bin), photos, RAWs or card files. Byte patches (`.xt3p`) only.
- [ ] No tables or looks made from paid presets or profiles.
- [ ] Builders check old bytes before writing, pin their output SHA-256, and decode their output (see `AGENTS.md`).
- [ ] `python3 tools/repo_check.py`, `python3 tools/make_firmware.py` and the tests pass locally.
- [ ] Nothing in this change needs a DAT to be flashed to test it.
