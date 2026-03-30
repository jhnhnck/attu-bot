#!/usr/bin/env python3
"""
AttuBot - Deploy Script
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn

from termcolor import colored


# worktree roots
dev_dir = Path(__file__).parent.parent.resolve()
prod_dir = Path('/srv/services/doom-bot')
version_file = dev_dir / 'attubot' / '__init__.py'


# --- helpers ---


def run_cmd(cmd: list[str], cwd: Path | None = None, capture: bool = True, dry_run: bool = False) -> str:
    """run a command; raise RuntimeError on failure; return stdout."""
    if dry_run:
        print(colored(f'    (dry run) {shlex.join(str(c) for c in cmd)}', 'dark_grey'))
        return ''
    result = subprocess.run(cmd, capture_output=capture, text=True, check=False, cwd=cwd)  # noqa: S603
    if result.returncode != 0:
        out = (result.stdout + result.stderr).strip() if capture else ''
        raise RuntimeError(out or f'{cmd[0]} exited with code {result.returncode}')
    return (result.stdout or '').strip()


def git_cmd(args: list[str], cwd: Path | None = None) -> str:
    """run a git command; always captures; raises RuntimeError on failure."""
    return run_cmd(['git', *args], cwd=cwd, capture=True)


def abort(msg: str) -> NoReturn:
    print(colored(f'abort: {msg}', 'red'), file=sys.stderr)
    sys.exit(1)


def header(n: int, total: int, title: str) -> None:
    print(colored(f'[{n}/{total}] {title}', 'white', attrs=['bold']))


# --- version logic ---


def parse_version(content: str) -> tuple[str, str]:
    """extract __version__ value and its full assignment string from file contents."""
    m = re.search(r"__version__ = '([^']+)'", content)
    if not m:
        abort('could not find __version__ in attubot/__init__.py')
    return m.group(1), m.group(0)


def compute_new_version(current: str, bump: str) -> tuple[str, str]:
    """return (new_version, tag) for the given bump type."""
    parts = current.split('.')
    if bump == 'minor':
        new_ver = f'{parts[0]}.{int(parts[1]) + 1}'
        return new_ver, f'{new_ver}.0'

    # patch - find latest tag matching current base, increment patch
    base = f'{parts[0]}.{parts[1]}'
    tags_out = git_cmd(['tag', '-l', f'{base}.*'])
    max_patch = -1
    for tag in tags_out.splitlines():
        tag_parts = tag.strip().split('.')
        if len(tag_parts) == 3 and tag_parts[2].isdigit():
            max_patch = max(max_patch, int(tag_parts[2]))
    new_ver = f'{base}.{max_patch + 1}'
    return new_ver, new_ver


# --- health check ---


def check_container_health(cwd: Path) -> list[str]:
    """return a list of problem descriptions for any containers that are unhealthy or exited."""
    result = subprocess.run(
        ['docker', 'compose', 'ps', '--format', 'json'],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        return [f'docker compose ps failed: {result.stderr.strip()}']

    problems = []
    # output is one json object per line (or a json array)
    raw = result.stdout.strip()
    try:
        entries = json.loads(raw) if raw.startswith('[') else [json.loads(line) for line in raw.splitlines() if line.strip()]
    except json.JSONDecodeError:
        return [f'could not parse docker compose ps output: {raw[:120]}']

    for svc in entries:
        name = svc.get('Name') or svc.get('Service') or '?'
        state = svc.get('State', '')
        health = svc.get('Health', '')
        if state in ('exited', 'dead'):
            problems.append(f'{name}: state={state}')
        elif health == 'unhealthy':
            problems.append(f'{name}: health=unhealthy')

    return problems


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='bump version, tag, and optionally deploy attubot')
    parser.add_argument('bump', nargs='?', default='minor', choices=['minor', 'patch'], help='version bump type (default: minor)')
    parser.add_argument('--no-tests', action='store_true', help='skip all test runs')
    parser.add_argument('--dry-run', action='store_true', help='print steps without making changes')
    parser.add_argument('--deploy', action='store_true', help='merge to trunk and restart the bot after tagging')
    args = parser.parse_args()

    dry_run: bool = args.dry_run
    do_deploy: bool = args.deploy
    skip_tests: bool = args.no_tests

    # count total steps up front
    total = 4  # branch check, clean dev, version bump, commit+tag
    if not skip_tests:
        total += 1  # dev tests
    if do_deploy:
        total += 3  # clean trunk, merge+push, restart
        if not skip_tests:
            total += 1  # trunk tests

    n = 0

    # --- 1. branch check ---
    n += 1
    header(n, total, 'checking branch')
    branch = git_cmd(['rev-parse', '--abbrev-ref', 'HEAD'])
    if branch != 'dev':
        abort(f"must be on the dev branch (currently on '{branch}')")
    print(colored('  on dev', 'green'))

    # --- 2. clean dev working directory ---
    n += 1
    header(n, total, 'checking dev working directory')
    dev_status = git_cmd(['status', '--porcelain'])
    dev_dirty = [line for line in dev_status.splitlines() if not line.startswith('??')]
    if dev_dirty:
        abort('dev working directory is not clean - commit or stash changes first:\n  ' + '\n  '.join(dev_dirty))
    print(colored('  dev is clean', 'green'))

    # --- 3. clean trunk working directory (deploy only) ---
    if do_deploy:
        n += 1
        header(n, total, 'checking trunk working directory')
        trunk_status = git_cmd(['status', '--porcelain'], cwd=prod_dir)
        trunk_dirty = [line for line in trunk_status.splitlines() if not line.startswith('??')]
        if trunk_dirty:
            abort('trunk working directory is not clean:\n  ' + '\n  '.join(trunk_dirty))
        print(colored('  trunk is clean', 'green'))

    # --- 4. run tests in dev ---
    if not skip_tests:
        n += 1
        header(n, total, 'running tests in dev')
        try:
            run_cmd(
                ['docker', 'compose', '-f', 'docker-compose.dev.yml', 'run', '--build', '--rm', '--quiet-build', 'tests'],
                cwd=dev_dir,
                capture=False,
                dry_run=dry_run,
            )
        except RuntimeError as e:
            abort(f'dev tests failed: {e}')
        print(colored('  tests passed', 'green'))

    # --- 5. version bump ---
    n += 1
    header(n, total, 'bumping version')
    content = version_file.read_text()
    current_ver, old_assignment = parse_version(content)
    new_ver, new_tag = compute_new_version(current_ver, args.bump)
    print(colored(f'  {current_ver} -> {new_ver}  (tag: {new_tag})', 'cyan'))

    if not dry_run:
        updated = content.replace(old_assignment, f"__version__ = '{new_ver}'", 1)
        version_file.write_text(updated)

    # --- 6. commit and tag ---
    n += 1
    header(n, total, 'committing and tagging')
    if not dry_run:
        try:
            git_cmd(['add', str(version_file)])
            git_cmd(['commit', '-m', f'chore(deploy): bump version to {new_ver}'])
            git_cmd(['tag', new_tag])
        except RuntimeError as e:
            # restore the file if commit failed before any git state changed
            version_file.write_text(content)
            abort(f'git commit/tag failed: {e}')
        print(colored(f'  committed and tagged {new_tag}', 'green'))
    else:
        print(colored(f'  (dry run) would commit version bump and create tag {new_tag}', 'dark_grey'))

    # --- deploy ---
    if not do_deploy:
        print()
        print(colored('version bump complete. to deploy:', 'white'))
        print(colored(f'  cd {prod_dir} && git merge --ff-only dev && git push origin trunk', 'cyan'))
        print(colored(f'  cd {prod_dir} && docker compose up --build -d', 'cyan'))
        sys.exit(0)

    saved_sha = git_cmd(['rev-parse', 'HEAD'], cwd=prod_dir)
    merged = False

    try:
        # --- 7. merge into trunk ---
        n += 1
        header(n, total, 'merging dev into trunk')
        if not dry_run:
            git_cmd(['merge', '--ff-only', 'dev'], cwd=prod_dir)
            merged = True
            print(colored('  merged', 'green'))
        else:
            print(colored('  (dry run) would merge dev into trunk', 'dark_grey'))

        # --- 8. run tests in trunk (optional) ---
        if not skip_tests:
            n += 1
            header(n, total, 'running tests in trunk')
            run_cmd(
                ['docker', 'compose', '-f', 'docker-compose.dev.yml', 'run', '--build', '--rm', '--quiet-build', 'tests'],
                cwd=prod_dir,
                capture=False,
                dry_run=dry_run,
            )
            print(colored('  tests passed', 'green'))

        # --- 9. restart containers, health check, then push ---
        n += 1
        header(n, total, 'restarting containers')
        if not dry_run:
            subprocess.run(
                ['docker', 'compose', 'up', '--build', '-d'],  # noqa: S607
                check=True,
                cwd=prod_dir,
            )
            print(colored('  waiting 60s for containers to stabilize...', 'cyan'))
            time.sleep(60)
            problems = check_container_health(prod_dir)
            if problems:
                raise RuntimeError('unhealthy containers after deploy:\n  ' + '\n  '.join(problems))
            print(colored('  all containers healthy', 'green'))
            # push only after everything is confirmed good
            git_cmd(['push', 'origin', 'trunk'], cwd=prod_dir)
            print(colored('  pushed trunk to remote', 'green'))
        else:
            print(colored('  (dry run) would run docker compose up --build -d, health check, then push', 'dark_grey'))

    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(colored(f'\ndeploy failed: {exc}', 'red'), file=sys.stderr)
        if merged and not dry_run:
            print(colored('rolling back trunk to previous commit...', 'yellow'), file=sys.stderr)
            reset = subprocess.run(['git', 'reset', '--hard', saved_sha], cwd=prod_dir, check=False)  # noqa: S603, S607
            rebuild = subprocess.run(['docker', 'compose', 'up', '--build', '-d'], cwd=prod_dir, check=False)  # noqa: S607
            if reset.returncode != 0 or rebuild.returncode != 0:
                print(colored('warning: rollback may have failed - check trunk manually', 'red'), file=sys.stderr)
            else:
                print(colored('rollback complete - containers rebuilt from previous state', 'yellow'), file=sys.stderr)
            print(colored(f'note: dev still has the version bump commit and tag {new_tag} - remove with: git tag -d {new_tag}', 'yellow'), file=sys.stderr)
        sys.exit(1)

    print(colored(f'\ndeployed version {new_ver} successfully', 'light_green'))
