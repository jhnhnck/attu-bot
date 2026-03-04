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
    run('python tests', ['coverage', 'run', '-m', 'pytest', '-m', 'not integration'])

    run('javascript tests', ['npm', 'test'])

    run('integration tests', ['coverage', 'run', '--append', '-m', 'pytest', '-m', 'integration', '-v'])

    if '--coverage' in sys.argv:
        run('coverage report', ['coverage', 'report'], quiet=False)

    print(colored('tests completed successfully.', 'light_green'))
