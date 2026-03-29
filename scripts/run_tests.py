#!/usr/bin/env python3
"""AttuBot test runner."""

import subprocess
import sys

from termcolor import colored


def run(title: str, cmd: list[str], env: dict | None = None, quiet: bool = True, step: int | None = None, total: int | None = None) -> None:
    prefix = f'[{step}/{total}] ' if step is not None and total is not None else ''
    print(colored(f'{prefix}running: {title}', 'cyan'))

    result = subprocess.run(cmd, capture_output=quiet, text=True, env=env, check=False)  # noqa: S603

    if result.returncode != 0:
        if quiet:
            print((result.stdout + result.stderr).strip(), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    verbose = '-v' in sys.argv
    exit_early = ['-x'] if '-x' in sys.argv else []
    coverage = '--coverage' in sys.argv

    steps = [
        ('unit tests',        ['coverage', 'run', '-m', 'pytest', *exit_early, 'tests/python/unit/']),
        ('component tests',   ['coverage', 'run', '--append', '-m', 'pytest', *exit_early, 'tests/python/component/']),
        ('integration tests', ['coverage', 'run', '--append', '-m', 'pytest', *exit_early, 'tests/python/integration/']),
        ('javascript tests',  ['npm', 'test']),
    ]
    total = len(steps)

    for i, (title, cmd) in enumerate(steps, 1):
        run(title, cmd, quiet=not verbose, step=i, total=total)

    if coverage:
        run('coverage report', ['coverage', 'report'], quiet=False)

    print(colored(f'{total}/{total} test suites passed.', 'light_green'))
