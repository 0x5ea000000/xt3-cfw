#!/usr/bin/env bash
# Start Palette on this computer only (http://127.0.0.1:8877). See run.py.
exec python3 "$(dirname "$0")/run.py" "$@"
