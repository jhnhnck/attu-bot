#!/usr/bin/env python3
"""AttuBot test runner."""

import subprocess
import sys

from termcolor import colored


def run(title: str, cmd: list[str], env: dict | None = None, quiet: bool = True) -> None:
    print(colored(f'running: {title}', 'cyan'))

    result = subprocess.run(cmd, capture_output=quiet, text=True, env=env, check=False)  # noqa: S603

    if result.returncode != 0:
        if quiet:
            print((result.stdout + result.stderr).strip(), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    verbose = '-v' in sys.argv

    run('unit tests', ['coverage', 'run', '-m', 'pytest', '-x', 'tests/python/unit/'], quiet=not verbose)
    run('component tests', ['coverage', 'run', '--append', '-m', 'pytest', '-x', 'tests/python/component/'], quiet=not verbose)
    run('integration tests', ['coverage', 'run', '--append', '-m', 'pytest', '-x', 'tests/python/integration/'], quiet=not verbose)

    run('javascript tests', ['npm', 'test'], quiet=not verbose)

    if '--coverage' in sys.argv:
        run('coverage report', ['coverage', 'report'], quiet=False)

    print(colored('tests completed successfully.', 'light_green'))
