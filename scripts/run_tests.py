#!/usr/bin/env python3
"""
AttuBot - Test Runner
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path


try:
    from termcolor import colored

except ImportError:
    print('error: missing dependencies\ntry running `pyenv shell doom-bot`\nor\n`pip install -r requirements-dev.txt --upgrade`', file=sys.stderr)
    sys.exit(1)


def header(n: int, total: int, title: str) -> None:
    print(colored(f'[{n}/{total}] {title}', 'white', attrs=['bold']))


def extract_counts(output: str) -> str | None:
    """extract a short count summary from pytest output, e.g. '42 passed, 1 warning'."""
    m = re.search(r'(\d+ (?:passed|failed)[^\n]*)', output)
    if not m:
        return None
    # strip trailing "in X.Xs" and warning counts to keep it short
    counts = re.sub(r',?\s*\d+ warning[s]?', '', m.group(1))
    counts = re.sub(r'\s+in\s+[\d.]+s.*', '', counts).strip()
    return counts or None


def run_suite(title: str, cmd: list[str], quiet: bool, step: int, total: int) -> tuple[bool, float, str | None]:
    """run one test suite; return (passed, elapsed_seconds, counts_summary)."""
    header(step, total, title)
    start = time.monotonic()
    result = subprocess.run(cmd, capture_output=quiet, text=True, check=False)  # noqa: S603
    elapsed = time.monotonic() - start
    combined = (result.stdout or '') + (result.stderr or '')
    counts = extract_counts(combined) if quiet else None
    if result.returncode != 0:
        if quiet:
            print(combined.strip(), file=sys.stderr)
        return False, elapsed, counts
    return True, elapsed, counts


if __name__ == '__main__':
    if not Path('/.dockerenv').exists():
        dev_dir = Path(__file__).parent.parent.resolve()
        cmd = ['docker', 'compose', 'run', '--build', '--rm', '--quiet-build', 'tests', 'scripts/run_tests.py', *sys.argv[1:]]
        sys.exit(subprocess.run(cmd, cwd=dev_dir, check=False).returncode)  # noqa: S603

    parser = argparse.ArgumentParser(description='run attubot test suites')
    parser.add_argument('-v', '--verbose', action='store_true', help='show full test output')
    parser.add_argument('-x', action='store_true', dest='exit_early', help='stop pytest on first failure within each suite')
    parser.add_argument('--coverage', action='store_true', help='print coverage report after tests')
    args = parser.parse_args()

    exit_flags = ['-x'] if args.exit_early else []

    suites = [
        ('unit tests', ['coverage', 'run', '-m', 'pytest', *exit_flags, 'tests/python/unit/']),
        ('component tests', ['coverage', 'run', '--append', '-m', 'pytest', *exit_flags, 'tests/python/component/']),
        ('integration tests', ['coverage', 'run', '--append', '-m', 'pytest', *exit_flags, 'tests/python/integration/']),
        ('javascript tests', ['npm', 'test']),
    ]
    total = len(suites)
    results: list[tuple[str, bool, float, str | None]] = []

    try:
        for i, (title, cmd) in enumerate(suites, 1):
            passed, elapsed, counts = run_suite(title, cmd, quiet=not args.verbose, step=i, total=total)
            results.append((title, passed, elapsed, counts))
    except KeyboardInterrupt:
        print(colored('\ninterrupted', 'yellow'), file=sys.stderr)
        sys.exit(130)

    if args.coverage:
        print()
        subprocess.run(['coverage', 'report'], check=False)  # noqa: S603, S607

    # --- summary ---
    print()
    print(colored('results:', 'white', attrs=['bold']))
    for title, passed, elapsed, counts in results:
        status = colored('passed', 'light_green') if passed else colored('FAILED', 'red')
        time_str = colored(f'{elapsed:.1f}s', 'dark_grey')
        count_str = colored(f'  {counts}', 'dark_grey') if counts else ''
        print(f'  {status}  {title:<22}  {time_str}{count_str}')

    print()
    failed = sum(1 for _, passed, _, _ in results if not passed)
    if failed:
        print(colored(f'{failed} suite(s) failed.', 'red'))
        sys.exit(1)
    else:
        print(colored(f'{total}/{total} test suites passed.', 'light_green'))
