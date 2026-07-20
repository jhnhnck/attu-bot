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
    """extract a short count summary from pytest or vitest output."""
    matches = re.findall(r'(\d+ (?:passed|failed)[^\n]*)', output)
    if not matches:
        return None
    raw = matches[-1]
    # strip trailing "in X.Xs", warning counts, and vitest "(N)" suffixes
    counts = re.sub(r',?\s*\d+ warning[s]?', '', raw)
    counts = re.sub(r'\s+in\s+[\d.]+s.*', '', counts)
    counts = re.sub(r'\s*\(\d+\)', '', counts).strip()
    return counts or None


def run_suite(title: str, cmd: list[str], quiet: bool, step: int, total: int) -> tuple[bool, float, str | None]:
    """run one test suite; return (passed, elapsed_seconds, counts_summary)."""
    header(step, total, title)
    start = time.monotonic()
    pipe = subprocess.PIPE if quiet else None
    proc = subprocess.Popen(cmd, stdout=pipe, stderr=pipe, text=True)  # noqa: S603
    interrupted = False
    try:
        stdout, stderr = proc.communicate()
    except KeyboardInterrupt:
        # ^C reached the child via the shared process group; let it shut down and drain its output
        interrupted = True
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
    elapsed = time.monotonic() - start
    combined = (stdout or '') + (stderr or '')
    counts = extract_counts(combined) if quiet else None
    if quiet and (proc.returncode != 0 or interrupted) and combined.strip():
        print(combined.strip(), file=sys.stderr)
    if interrupted:
        raise KeyboardInterrupt
    return proc.returncode == 0, elapsed, counts


if __name__ == '__main__':
    if not Path('/.dockerenv').exists():
        dev_dir = Path(__file__).parent.parent.resolve()
        cmd = ['docker', 'compose', 'run', '--build', '--rm', '--quiet-build', 'tests', 'scripts/run_tests.py', *sys.argv[1:]]
        proc = subprocess.Popen(cmd, cwd=dev_dir)  # noqa: S603
        # docker compose run shares our process group, so ^C reaches it directly; keep waiting
        # while it forwards the signal and tears down the container instead of exiting early
        while True:
            try:
                rc = proc.wait()
                break
            except KeyboardInterrupt:
                pass
        sys.exit(rc)

    parser = argparse.ArgumentParser(description='run doom_bot test suites')
    parser.add_argument('-v', '--verbose', action='store_true', help='show full test output')
    parser.add_argument('-x', action='store_true', dest='exit_early', help='stop pytest on first failure within each suite')
    parser.add_argument('--coverage', action='store_true', help='print coverage report after tests')
    parser.add_argument('--coverage-json', action='store_true', help='emit coverage json to stdout; all other output goes to stderr')
    args = parser.parse_args()

    real_stdout = sys.stdout
    if args.coverage_json:
        # redirect all script prints to stderr; reserve real stdout for the json payload
        sys.stdout = sys.stderr
        args.verbose = False  # force capture so subprocess output cannot leak to fd 1

    exit_flags = ['-x'] if args.exit_early else []

    suites = [
        ('unit tests', ['coverage', 'run', '-m', 'pytest', *exit_flags, 'tests/python/unit/']),
        ('component tests', ['coverage', 'run', '--append', '-m', 'pytest', *exit_flags, 'tests/python/component/']),
        ('integration tests', ['coverage', 'run', '--append', '-m', 'pytest', *exit_flags, 'tests/python/integration/']),
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
        report_stdout = sys.stderr if args.coverage_json else None
        subprocess.run(['coverage', 'report'], stdout=report_stdout, check=False)  # noqa: S607

    if args.coverage_json:
        subprocess.run(['coverage', 'json', '-o', '-'], stdout=real_stdout, check=False)  # noqa: S607

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
