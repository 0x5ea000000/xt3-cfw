#!/usr/bin/env python3
"""Start Palette on this computer only: http://127.0.0.1:8877. The first run sets up palette/.venv.

  python3 palette/run.py            (Windows: py palette\\run.py)
PALETTE_HOST and PALETTE_PORT override the address. Only set PALETTE_HOST if you mean other machines to reach it: Palette has no login.
"""
import os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / '.venv'
PY = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

if not PY.exists():
    print('First run: setting up palette/.venv', flush=True)
    subprocess.check_call([sys.executable, '-m', 'venv', str(VENV)])
    subprocess.check_call([str(PY), '-m', 'pip', '-q', 'install', '--prefer-binary', '-r', str(HERE / 'requirements.txt')])
host, port = os.environ.get('PALETTE_HOST', '127.0.0.1'), os.environ.get('PALETTE_PORT', '8877')
print(f'Palette: open http://{host}:{port}', flush=True)
raise SystemExit(subprocess.call([str(PY), str(HERE / 'server.py'), '--host', host, '--port', port], cwd=HERE))
