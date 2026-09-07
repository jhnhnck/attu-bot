#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""scripts.deploy | deploy and version management script for nova_core."""

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from datetime import date, datetime
from pathlib import Path
from typing import NoReturn
from zoneinfo import ZoneInfo


try:
    from termcolor import colored

except ImportError:
    print('error: missing dependencies\ntry running `pyenv shell doom-bot`\nor\n`pip install -r requirements-dev.txt --upgrade`', file=sys.stderr)
    sys.exit(1)


# worktree roots
dev_dir = Path(__file__).parent.parent.resolve()
prod_dir = Path('/srv/services/doom-bot')
version_file = dev_dir / 'apps' / 'bot' / 'nova_core' / '__init__.py'
lock_file = dev_dir / 'uv.lock'

_epoch_file = Path.home() / '.attu-epoch.toml'

# the live config is gitignored, so a `git reset` across a config-format change
# leaves the old image facing a config it cannot parse. snapshot it per tag so a
# revert can put the matching one back.
prod_config = prod_dir / '.secrets' / 'attu-bot.toml'


def config_snapshot(tag: str) -> Path:
    """path of the config snapshot belonging to a version tag."""
    return prod_config.with_name(f'{prod_config.name}.{tag}')


def save_config_snapshot(tag: str, dry_run: bool = False) -> None:
    """copy the live prod config aside under its version tag; overwrites an existing one."""
    dest = config_snapshot(tag)
    if dry_run:
        print(colored(f'  (dry run) would snapshot config to {dest.name}', 'dark_grey'))
        return
    if not prod_config.exists():
        print(colored(f'  warning: {prod_config} not found; no config snapshot saved', 'yellow'), file=sys.stderr)
        return
    shutil.copy2(prod_config, dest)  # copy2 keeps mode and ownership bits the containers rely on
    print(colored(f'  config snapshot saved as {dest.name}', 'green'))


def require_config_snapshot(tag: str, force: bool = False) -> None:
    """abort unless a config snapshot for `tag` exists, or the caller forced past it."""
    snapshot = config_snapshot(tag)
    if snapshot.exists():
        print(colored(f'  found {snapshot.name}', 'green'))
        return
    if force:
        print(colored(f'  no {snapshot.name}; --force given, keeping the current config', 'yellow'), file=sys.stderr)
        return
    abort(f'no config snapshot for {tag} at {snapshot}.\n  reverting the code without it leaves {prod_config.name} in a format the\n  {tag} image may not parse, which is how the bot stays down after a revert.\n  put the config that shipped with {tag} there, or pass --force to keep the current one.')


def restore_config_snapshot(tag: str, dry_run: bool = False) -> bool:
    """put the snapshot for `tag` back in place; return False when none exists."""
    src = config_snapshot(tag)
    if dry_run:
        print(colored(f'  (dry run) would restore config from {src.name}', 'dark_grey'))
        return True
    if not src.exists():
        return False
    shutil.copy2(src, prod_config)
    print(colored(f'  config restored from {src.name}', 'green'))
    return True


# --- helpers ---


def run_cmd(cmd: list[str], cwd: Path | None = None, capture: bool = True, dry_run: bool = False) -> str:
    """run a command; raise RuntimeError on failure; return stdout."""
    if dry_run:
        print(colored(f'    (dry run) {shlex.join(str(c) for c in cmd)}', 'dark_grey'))
        return ''
    result = subprocess.run(cmd, capture_output=capture, text=True, check=False, cwd=cwd)  # noqa: S603 - cmd is a trusted list built from local config, not user input
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
        abort('could not find __version__ in apps/bot/nova_core/__init__.py')
    return m.group(1), m.group(0)


def compute_attu_year() -> int:
    """compute the current attu year from ~/.attu-epoch.toml."""
    if not _epoch_file.exists():
        abort(f'epoch file not found: {_epoch_file}')
    epoch = tomllib.loads(_epoch_file.read_text())['epoch']
    tz = ZoneInfo('UTC')
    rollover_minutes: int = epoch['rollover_minutes']
    rollover_time = datetime.min.time().replace(hour=rollover_minutes // 60, minute=rollover_minutes % 60, tzinfo=tz)
    epoch_dt = datetime.combine(datetime.fromtimestamp(epoch['time']).astimezone(), rollover_time)
    today_dt = datetime.combine(date.today(), rollover_time)
    elapsed_days = int((today_dt - epoch_dt).total_seconds() / 86400)
    year: int = epoch['year'] + (elapsed_days // epoch['length'])
    if (elapsed_days % epoch['length']) == 0 and datetime.now().astimezone() < today_dt:
        year -= 1
    return year


def compute_new_version(current: str, bump: str) -> tuple[str, str]:
    """return (new_version, tag) for the given bump type."""
    parts = current.split('.')
    if bump == 'minor':
        attu_year = compute_attu_year()
        new_ver = f'{attu_year}.0' if attu_year != int(parts[0]) else f'{parts[0]}.{int(parts[1]) + 1}'
        return new_ver, f'{new_ver}.0'

    # patch - find latest tag matching current base, increment patch
    base = f'{parts[0]}.{parts[1]}'
    tags_out = git_cmd(['tag', '-l', f'{base}.*'])
    max_patch = -1
    for tag in tags_out.splitlines():
        tag_parts = tag.strip().split('.')
        if len(tag_parts) == 3 and tag_parts[2].isdigit() and f'{tag_parts[0]}.{tag_parts[1]}' == base:
            max_patch = max(max_patch, int(tag_parts[2]))
    new_ver = f'{base}.{max_patch + 1}'
    return new_ver, new_ver


# --- health check ---


def check_container_health(cwd: Path) -> list[str]:
    """return a list of problem descriptions for any containers that are unhealthy or exited."""
    result = subprocess.run(
        ['docker', 'compose', 'ps', '--format', 'json'],  # noqa: S607 - partial path intentional; docker is on PATH in the deploy environment
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


def rebuild_and_check(what: str, dry_run: bool = False) -> None:
    """bring prod's containers up and fail if any are unhealthy after they settle."""
    run_cmd(['docker', 'compose', 'up', '--build', '-d'], cwd=prod_dir, capture=False, dry_run=dry_run)
    if dry_run:
        print(colored('  (dry run) would run docker compose up --build -d, then check health', 'dark_grey'))
        return
    print(colored('  waiting 60s for containers to stabilize', 'cyan'))
    time.sleep(60)
    problems = check_container_health(prod_dir)
    if problems:
        abort(f'unhealthy containers after {what}:\n  ' + '\n  '.join(problems))
    print(colored('  all containers healthy', 'green'))


def revert_to_tag(tag: str, dry_run: bool = False, force: bool = False) -> None:
    """revert prod to a previous version tag, restore that tag's config, and rebuild."""
    total = 6
    n = 0

    n += 1
    header(n, total, f'verifying tag {tag}')
    try:
        git_cmd(['rev-parse', '--verify', tag])
    except RuntimeError:
        abort(f"tag {tag!r} not found in dev repo; check with: git tag -l '*{tag.rsplit('.', 1)[-1]}*'")
    print(colored(f'  tag {tag} found', 'green'))

    n += 1
    header(n, total, 'checking prod working directory')
    trunk_status = git_cmd(['status', '--porcelain'], cwd=prod_dir)
    trunk_dirty = [line for line in trunk_status.splitlines() if not line.startswith('??')]
    if trunk_dirty:
        abort('prod working directory is not clean:\n  ' + '\n  '.join(trunk_dirty))
    current_sha = git_cmd(['rev-parse', '--short', 'HEAD'], cwd=prod_dir)
    print(colored(f'  prod is clean (currently at {current_sha})', 'green'))

    n += 1
    header(n, total, f'checking for the config snapshot of {tag}')
    require_config_snapshot(tag, force=force)

    n += 1
    header(n, total, f'resetting prod to {tag}')
    # snapshot the config we are leaving, under the tag it belongs to, so rolling
    # forward again does not need it reconstructed by hand
    outgoing_tag = git_cmd(['describe', '--tags', '--abbrev=0'], cwd=prod_dir)
    if outgoing_tag and outgoing_tag != tag:
        save_config_snapshot(outgoing_tag, dry_run=dry_run)
    if not dry_run:
        try:
            git_cmd(['reset', '--hard', tag], cwd=prod_dir)
            git_cmd(['push', '--force', 'origin', 'prod'], cwd=prod_dir)
        except RuntimeError as e:
            abort(f'revert failed: {e}')
        print(colored(f'  prod reset to {tag} and pushed', 'green'))
    else:
        print(colored(f'  (dry run) would git reset --hard {tag} and force-push origin prod', 'dark_grey'))

    n += 1
    header(n, total, 'restoring config')
    if not restore_config_snapshot(tag, dry_run=dry_run):
        print(colored('  no snapshot restored; keeping the current config (--force)', 'yellow'), file=sys.stderr)

    n += 1
    header(n, total, 'rebuilding containers and checking health')
    rebuild_and_check('revert', dry_run=dry_run)

    print(colored(f'\nreverted to {tag} successfully', 'light_green'))
    print(colored('  note: trunk branch still points to the pre-revert state; adjust manually if needed', 'cyan'))


def deploy_only_run(skip_tests: bool = False, dry_run: bool = False) -> None:
    """resume a deploy: prod is already at the new tag from a prior bump run; restart containers and push."""
    total = 2  # prod check + restart
    if not skip_tests:
        total += 1  # prod tests
    n = 0

    n += 1
    header(n, total, 'checking prod working directory')
    trunk_status = git_cmd(['status', '--porcelain'], cwd=prod_dir)
    trunk_dirty = [line for line in trunk_status.splitlines() if not line.startswith('??')]
    if trunk_dirty:
        abort('prod working directory is not clean:\n  ' + '\n  '.join(trunk_dirty))
    saved_sha = git_cmd(['rev-parse', 'HEAD'], cwd=prod_dir)
    print(colored('  prod is clean', 'green'))

    try:
        if not skip_tests:
            n += 1
            header(n, total, 'running tests in prod')
            run_cmd(
                ['docker', 'compose', '-f', 'docker-compose.dev.yml', 'run', '--build', '--rm', '--quiet-build', 'tests'],
                cwd=prod_dir,
                capture=False,
                dry_run=dry_run,
            )
            print(colored('  tests passed', 'green'))

        n += 1
        header(n, total, 'restarting containers')
        deploy_tag = git_cmd(['describe', '--tags', '--abbrev=0'], cwd=prod_dir)
        if not dry_run:
            subprocess.run(
                ['docker', 'compose', 'up', '--build', '-d'],  # noqa: S607 - partial path intentional; docker is on PATH in the deploy environment
                check=True,
                cwd=prod_dir,
            )
            print(colored('  waiting 60s for containers to stabilize', 'cyan'))
            time.sleep(60)
            problems = check_container_health(prod_dir)
            if problems:
                raise RuntimeError('unhealthy containers after deploy:\n  ' + '\n  '.join(problems))
            print(colored('  all containers healthy', 'green'))
            git_cmd(['push', 'origin', 'prod', deploy_tag], cwd=prod_dir)
            print(colored('  pushed prod to remote', 'green'))
        else:
            print(colored('  (dry run) would run docker compose up --build -d, health check, then push', 'dark_grey'))

    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(colored(f'\ndeploy failed: {exc}', 'red'), file=sys.stderr)
        if not dry_run:
            print(colored('rolling back prod to previous state', 'yellow'), file=sys.stderr)
            trunk_reset = subprocess.run(['git', 'reset', '--hard', saved_sha], cwd=prod_dir, check=False)  # noqa: S603, S607 - rollback: trusted list, partial paths intentional
            rebuild = subprocess.run(['docker', 'compose', 'up', '--build', '-d'], cwd=prod_dir, check=False)  # noqa: S607 - rollback: partial path intentional
            if trunk_reset.returncode != 0 or rebuild.returncode != 0:
                print(colored('warning: rollback may have failed; check prod manually', 'red'), file=sys.stderr)
            else:
                print(colored('rollback complete: prod reset, containers rebuilt', 'yellow'), file=sys.stderr)
        sys.exit(1)

    print(colored(f'\ndeployed {deploy_tag} successfully', 'light_green'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='bump version, tag, and optionally deploy nova_core')
    parser.add_argument('bump', nargs='?', default=None, choices=['minor', 'patch'], help='version bump type; omitting it with --deploy resumes an already-bumped deploy instead of bumping')
    parser.add_argument('--no-tests', action='store_true', help='skip all test runs')
    parser.add_argument('--dry-run', action='store_true', help='print steps without making changes')
    parser.add_argument('--deploy', action='store_true', help='rebuild containers and push to remote after tagging and merging trunk')
    parser.add_argument('--revert', metavar='TAG', help='revert trunk to a previous version tag, restore that tag config, and rebuild containers')
    parser.add_argument('--snapshot-config', metavar='TAG', help="copy prod's live config aside as the config belonging to TAG; run before migrating the config forward")
    parser.add_argument('--force', action='store_true', help='with --revert, proceed even when TAG has no config snapshot')
    args = parser.parse_args()

    dry_run: bool = args.dry_run
    do_deploy: bool = args.deploy
    skip_tests: bool = args.no_tests

    if args.snapshot_config:
        if dry_run:
            print(colored(f'  (dry run) would snapshot config as {config_snapshot(args.snapshot_config).name}', 'dark_grey'))
        elif not prod_config.exists():
            abort(f'no config at {prod_config}; nothing to snapshot')
        else:
            save_config_snapshot(args.snapshot_config)
        sys.exit(0)

    if args.revert:
        try:
            revert_to_tag(args.revert, dry_run=dry_run, force=args.force)
        except KeyboardInterrupt:
            print(colored('\ninterrupted', 'yellow'), file=sys.stderr)
            sys.exit(130)
        sys.exit(0)

    deploy_only: bool = do_deploy and args.bump is None
    bump: str = args.bump or 'minor'

    if deploy_only:
        try:
            deploy_only_run(skip_tests=skip_tests, dry_run=dry_run)
        except KeyboardInterrupt:
            print(colored('\ninterrupted', 'yellow'), file=sys.stderr)
            sys.exit(130)
        sys.exit(0)

    total = 7  # branch check, new commits check, stash dev, trunk clean, version bump, commit+tag, merge
    if not skip_tests:
        total += 1  # dev tests
    if do_deploy:
        total += 1  # restart
        if not skip_tests:
            total += 1  # trunk tests

    n = 0

    n += 1
    header(n, total, 'checking branch')
    branch = git_cmd(['rev-parse', '--abbrev-ref', 'HEAD'])
    if branch != 'trunk':
        abort(f"must be on the trunk branch (currently on '{branch}')")
    print(colored('  on trunk', 'green'))

    n += 1
    header(n, total, 'checking for new commits')
    new_commits = git_cmd(['log', 'prod..trunk', '--oneline'])
    if not new_commits:
        abort('trunk has no new commits ahead of prod; nothing to deploy')
    print(colored(f'  {len(new_commits.splitlines())} commit(s) ahead of prod', 'green'))

    n += 1
    header(n, total, 'stashing trunk changes')
    dev_status = git_cmd(['status', '--porcelain'])
    dev_dirty = [line for line in dev_status.splitlines() if not line.startswith('??')]
    stashed = False

    script_rel = str(Path(__file__).relative_to(dev_dir))
    if any(script_rel in line for line in dev_dirty):
        abort(f'{script_rel} has uncommitted changes; commit or reset before deploying')

    if dev_dirty:
        if not dry_run:
            git_cmd(['stash', 'push', '-m', 'deploy-script auto-stash'])
            stashed = True
            print(colored('  stashed uncommitted changes', 'cyan'))
        else:
            print(colored('  (dry run) would stash uncommitted changes', 'dark_grey'))
    else:
        print(colored('  trunk is clean', 'green'))

    merged = False
    committed = False
    version_modified = False
    content = ''
    pyproject_content = ''
    pyproject_file: Path | None = None
    lock_content = ''
    saved_sha: str | None = None
    # trunk's pre-bump sha; rollback resets to this rather than HEAD~1 so a
    # second rollback (interrupt during the first) cannot eat a real commit
    saved_trunk_sha: str = git_cmd(['rev-parse', 'HEAD'])
    new_tag: str | None = None
    new_ver: str | None = None

    try:
        n += 1
        header(n, total, 'checking prod working directory')
        trunk_status = git_cmd(['status', '--porcelain'], cwd=prod_dir)
        trunk_dirty = [line for line in trunk_status.splitlines() if not line.startswith('??')]
        if trunk_dirty:
            abort('prod working directory is not clean:\n  ' + '\n  '.join(trunk_dirty))
        saved_sha = git_cmd(['rev-parse', 'HEAD'], cwd=prod_dir)
        # warn now, not mid-incident, if the version we are replacing has no config
        # snapshot; --revert to it would restore the code but leave a config the
        # older image may refuse to parse
        outgoing_tag = git_cmd(['describe', '--tags', '--abbrev=0'], cwd=prod_dir)
        if outgoing_tag and not config_snapshot(outgoing_tag).exists():
            print(
                colored(
                    f'  warning: no config snapshot for the current version {outgoing_tag};\n  --revert {outgoing_tag} will not be able to restore its config.\n  capture it first with: deploy.py --snapshot-config {outgoing_tag}',
                    'yellow',
                ),
                file=sys.stderr,
            )
        print(colored('  prod is clean', 'green'))

        if not skip_tests:
            n += 1
            header(n, total, 'running tests in trunk')
            try:
                run_cmd(
                    ['docker', 'compose', '-f', 'docker-compose.dev.yml', 'run', '--build', '--rm', '--quiet-build', 'tests'],
                    cwd=dev_dir,
                    capture=False,
                    dry_run=dry_run,
                )
            except RuntimeError as e:
                abort(f'trunk tests failed: {e}')
            print(colored('  tests passed', 'green'))

        n += 1
        header(n, total, 'bumping version')
        content = version_file.read_text()
        current_ver, old_assignment = parse_version(content)
        new_ver, new_tag = compute_new_version(current_ver, bump)
        print(colored(f'  {current_ver} -> {new_ver}  (tag: {new_tag})', 'cyan'))

        pyproject_file = dev_dir / 'apps' / 'bot' / 'pyproject.toml'
        if not dry_run:
            updated = content.replace(old_assignment, f"__version__ = '{new_ver}'", 1)
            version_file.write_text(updated)
            pyproject_content = pyproject_file.read_text()
            pyproject_updated = re.sub(r'^version = "[^"]+"', f'version = "{new_ver}"', pyproject_content, count=1, flags=re.MULTILINE)
            pyproject_file.write_text(pyproject_updated)
            version_modified = True

            # uv copies the workspace member's version into uv.lock; relock here so the bump
            # commit carries it, otherwise the next `uv run` dirties the tree one deploy later
            lock_content = lock_file.read_text()
            try:
                run_cmd(['uv', 'lock'], cwd=dev_dir)
            except RuntimeError as e:
                version_file.write_text(content)
                pyproject_file.write_text(pyproject_content)
                lock_content = ''
                version_modified = False
                abort(f'uv lock failed after version bump (bump reverted): {e}')
            print(colored('  uv.lock synced', 'green'))
        else:
            print(colored('  (dry run) would sync uv.lock', 'dark_grey'))

        n += 1
        header(n, total, 'committing and tagging')
        if not dry_run:
            try:
                git_cmd(['add', str(version_file), str(pyproject_file), str(lock_file)])
                git_cmd(['commit', '-m', f'chore(deploy): bump version to {new_ver}'])
                committed = True
                git_cmd(['tag', new_tag])
            except RuntimeError as e:
                # restore the files if commit failed before any git state changed
                version_file.write_text(content)
                pyproject_file.write_text(pyproject_content)
                if lock_content:
                    lock_file.write_text(lock_content)
                abort(f'git commit/tag failed: {e}')
            print(colored(f'  committed and tagged {new_tag}', 'green'))
        else:
            print(colored(f'  (dry run) would commit version bump and create tag {new_tag}', 'dark_grey'))

        n += 1
        header(n, total, 'merging trunk into prod')
        if not dry_run:
            try:
                git_cmd(['merge', '--ff-only', 'trunk'], cwd=prod_dir)
                merged = True
                print(colored('  merged', 'green'))
            except RuntimeError as e:
                # undo the version bump commit and tag before aborting
                subprocess.run(['git', 'reset', '--hard', saved_trunk_sha], check=False)  # noqa: S603, S607 - rollback on merge failure; saved_trunk_sha is a local `git rev-parse` result, not user input
                subprocess.run(['git', 'tag', '-d', new_tag], check=False)  # noqa: S603, S607 - rollback on merge failure
                abort(f'merge into prod failed (version bump rolled back): {e}')
        else:
            print(colored('  (dry run) would merge trunk into prod', 'dark_grey'))

        if not do_deploy:
            print()
            print(colored(f'version {new_ver} tagged and prod fast-forwarded', 'white'))
            print(colored('  run with --deploy to rebuild containers and push to remote', 'cyan'))
            sys.exit(0)

        try:
            if not skip_tests:
                n += 1
                header(n, total, 'running tests in prod')
                run_cmd(
                    ['docker', 'compose', '-f', 'docker-compose.dev.yml', 'run', '--build', '--rm', '--quiet-build', 'tests'],
                    cwd=prod_dir,
                    capture=False,
                    dry_run=dry_run,
                )
                print(colored('  tests passed', 'green'))

            n += 1
            header(n, total, 'restarting containers')
            # record the config this version runs with, so a later --revert to it
            # restores a config the image can parse. only the new tag is captured
            # here: by now the live config has already been migrated forward, so
            # writing it under the outgoing tag would be a lie.
            save_config_snapshot(new_tag, dry_run=dry_run)
            if not dry_run:
                subprocess.run(
                    ['docker', 'compose', 'up', '--build', '-d'],  # noqa: S607 - partial path intentional; docker is on PATH in the deploy environment
                    check=True,
                    cwd=prod_dir,
                )
                print(colored('  waiting 60s for containers to stabilize', 'cyan'))
                time.sleep(60)
                problems = check_container_health(prod_dir)
                if problems:
                    raise RuntimeError('unhealthy containers after deploy:\n  ' + '\n  '.join(problems))
                print(colored('  all containers healthy', 'green'))
                # push only after everything is confirmed good
                git_cmd(['push', 'origin', 'prod', new_tag], cwd=prod_dir)
                print(colored('  pushed prod to remote', 'green'))
            else:
                print(colored('  (dry run) would run docker compose up --build -d, health check, then push', 'dark_grey'))

        except (RuntimeError, subprocess.CalledProcessError) as exc:
            print(colored(f'\ndeploy failed: {exc}', 'red'), file=sys.stderr)
            if merged and not dry_run:
                print(colored('rolling back prod and trunk to previous state', 'yellow'), file=sys.stderr)
                trunk_reset = subprocess.run(['git', 'reset', '--hard', saved_sha], cwd=prod_dir, check=False)  # noqa: S603, S607 - rollback: trusted list, partial paths intentional
                dev_reset = subprocess.run(['git', 'reset', '--hard', saved_trunk_sha], check=False)  # noqa: S603, S607 - reset trunk to its pre-bump sha, idempotent across repeated rollbacks; sha is a local `git rev-parse` result, not user input
                subprocess.run(['git', 'tag', '-d', new_tag], check=False)  # noqa: S603, S607 - undo version tag on trunk
                # the code is going back; the config has to go with it or the older
                # image starts against a config it cannot parse
                if outgoing_tag and not restore_config_snapshot(outgoing_tag):
                    print(
                        colored(
                            f'warning: no config snapshot for {outgoing_tag}; prod code is rolled back but\n  {prod_config.name} is still the migrated one. restore it by hand before the\n  containers settle, or the bot will not come up.',
                            'red',
                        ),
                        file=sys.stderr,
                    )
                rebuild = subprocess.run(['docker', 'compose', 'up', '--build', '-d'], cwd=prod_dir, check=False)  # noqa: S607 - rollback: partial path intentional
                if trunk_reset.returncode != 0 or dev_reset.returncode != 0 or rebuild.returncode != 0:
                    print(colored('warning: rollback may have failed; check prod and trunk manually', 'red'), file=sys.stderr)
                else:
                    print(colored('rollback complete: prod and trunk reset, containers rebuilt from previous state', 'yellow'), file=sys.stderr)
            sys.exit(1)

        print(colored(f'\ndeployed version {new_ver} successfully', 'light_green'))

    except KeyboardInterrupt:
        print(colored('\ninterrupted', 'yellow'), file=sys.stderr)
        if not dry_run:
            if merged and saved_sha and new_tag:
                print(colored('rolling back prod and trunk to previous state', 'yellow'), file=sys.stderr)
                subprocess.run(['git', 'reset', '--hard', saved_sha], cwd=prod_dir, check=False)  # noqa: S603, S607 - rollback on interrupt
                subprocess.run(['git', 'reset', '--hard', saved_trunk_sha], check=False)  # noqa: S603, S607 - rollback on interrupt; saved_trunk_sha is a local `git rev-parse` result, not user input
                subprocess.run(['git', 'tag', '-d', new_tag], check=False)  # noqa: S603, S607 - rollback on interrupt
                if outgoing_tag and not restore_config_snapshot(outgoing_tag):
                    print(colored(f'warning: no config snapshot for {outgoing_tag}; {prod_config.name} left as-is', 'red'), file=sys.stderr)
            elif committed and new_tag:
                print(colored('rolling back version commit and tag', 'yellow'), file=sys.stderr)
                subprocess.run(['git', 'reset', '--hard', saved_trunk_sha], check=False)  # noqa: S603, S607 - rollback on interrupt; saved_trunk_sha is a local `git rev-parse` result, not user input
                subprocess.run(['git', 'tag', '-d', new_tag], check=False)  # noqa: S603, S607 - rollback on interrupt
            elif version_modified and content:
                version_file.write_text(content)
                if pyproject_content and pyproject_file is not None:
                    pyproject_file.write_text(pyproject_content)
                if lock_content:
                    lock_file.write_text(lock_content)
        sys.exit(130)

    finally:
        if stashed and not dry_run:
            try:
                git_cmd(['stash', 'pop'])
                print(colored('  restored stashed changes', 'green'))
            except RuntimeError as e:
                print(colored(f'  warning: could not restore stash: {e}', 'yellow'), file=sys.stderr)
