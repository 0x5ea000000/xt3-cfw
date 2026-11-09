# Contributing

Thanks for helping. Please read [SAFETY.md](SAFETY.md) and [AGENTS.md](AGENTS.md) first: the second is the working rules for people and coding agents alike.

## How changes land

- Open an issue first for anything bigger than a fix, so we agree on the approach.
- One change per pull request, from a branch of your fork. The maintainer reviews and merges; nobody else merges.
- Every pull request runs `tools/repo_check.py`, the recipe tests and Palette's tests. They must pass.

## What a pull request may contain

- Code, documents, tests, and recipes that hold **only your own bytes**, plus copy steps from the user's official image.
- **Never** firmware files (DAT, `ffboot.bin`, `ffinit.bin`, card files), Fujifilm or FujiMod bytes, photos or RAWs, or tables and looks made from paid presets or profiles.

## Firmware changes

A firmware change is a new tested build. Describe it with its evidence: what you saw on the camera, with the SHA-256 of the exact files, or what the emulator or the code shows, labelled as such. Builders check the old bytes before writing new ones, pin their output's SHA-256, and decode what they assembled (assemblers have silently produced wrong branches before). Never ask anyone to flash anything to test a change.
