#!/usr/bin/env python3
"""First run: make an empty row list. Your looks are yours: add them in the app; the library folder is not in git."""
import library as L


def run():
    L.LIBRARY.mkdir(parents=True, exist_ok=True)
    if not L.ROWS.exists():
        L.set_rows([])


if __name__ == '__main__':
    run(); print(L.rows())
