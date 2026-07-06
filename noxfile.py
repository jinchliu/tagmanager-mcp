"""Nox sessions: format check and unit tests (run in the current env).

Sessions use sys.executable so they run against the interpreter that
runs nox itself (the project venv), not whatever 'python' is on PATH.
"""

import sys

import nox


@nox.session(venv_backend='none')
def lint(session: nox.Session) -> None:
    session.run(sys.executable, '-m', 'black', '--check', '.')


@nox.session(venv_backend='none')
def format(session: nox.Session) -> None:
    session.run(sys.executable, '-m', 'black', '.')


@nox.session(venv_backend='none')
def tests(session: nox.Session) -> None:
    session.run(
        sys.executable,
        '-m',
        'unittest',
        'discover',
        '--buffer',
        '-s=tests',
        '-p',
        '*_test.py',
    )
