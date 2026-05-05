"""
AttuBot - Tests for scripts/deploy.py
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from deploy import abort, check_container_health, compute_new_version, deploy_only_run, parse_version


def _proc(returncode: int = 0, stdout: str = '', stderr: str = '') -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# parse_version
# ---------------------------------------------------------------------------


class TestParseVersion:
    def test_returns_version_and_assignment(self):
        content = "# comment\n__version__ = '1.2.3'\n"
        ver, assignment = parse_version(content)
        assert ver == '1.2.3'
        assert assignment == "__version__ = '1.2.3'"

    def test_missing_version_aborts(self):
        with pytest.raises(SystemExit) as exc_info:
            parse_version('# no version here\n')
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# compute_new_version
# ---------------------------------------------------------------------------


class TestComputeNewVersion:
    def test_minor_bump_two_part(self):
        with patch('deploy.compute_attu_year', return_value=1):
            ver, tag = compute_new_version('1.2', 'minor')
        assert ver == '1.3'
        assert tag == '1.3.0'

    def test_minor_bump_three_part(self):
        # patch part is stripped; base is still bumped
        with patch('deploy.compute_attu_year', return_value=1):
            ver, tag = compute_new_version('1.2.1', 'minor')
        assert ver == '1.3'
        assert tag == '1.3.0'

    def test_minor_bump_attu_year_rollover(self):
        # when attu year has advanced, major resets and minor starts at 0
        with patch('deploy.compute_attu_year', return_value=2):
            ver, tag = compute_new_version('1.9', 'minor')
        assert ver == '2.0'
        assert tag == '2.0.0'

    def test_patch_bump_no_existing_tags(self):
        with patch('deploy.git_cmd', return_value=''):
            ver, tag = compute_new_version('1.2', 'patch')
        assert ver == '1.2.0'
        assert tag == '1.2.0'

    def test_patch_bump_increments_beyond_max(self):
        with patch('deploy.git_cmd', return_value='1.2.0\n1.2.1\n1.2.2'):
            ver, tag = compute_new_version('1.2', 'patch')
        assert ver == '1.2.3'
        assert tag == '1.2.3'

    def test_patch_bump_ignores_unrelated_tags(self):
        # tags from a different major.minor must not affect the result
        with patch('deploy.git_cmd', return_value='1.1.9\n1.3.0\notherformat'):
            ver, tag = compute_new_version('1.2', 'patch')
        assert ver == '1.2.0'
        assert tag == '1.2.0'


# ---------------------------------------------------------------------------
# check_container_health
# ---------------------------------------------------------------------------


class TestCheckContainerHealth:
    _cwd = Path('/fake')

    def _run(self, stdout: str = '', returncode: int = 0, stderr: str = '') -> list[str]:
        with patch('deploy.subprocess.run', return_value=_proc(returncode, stdout, stderr)):
            return check_container_health(self._cwd)

    def test_all_healthy_returns_empty(self):
        data = json.dumps([{'Name': 'bot', 'State': 'running', 'Health': 'healthy'}])
        assert self._run(data) == []

    def test_running_no_health_field_is_ok(self):
        data = json.dumps([{'Name': 'bot', 'State': 'running'}])
        assert self._run(data) == []

    def test_exited_container_is_problem(self):
        data = json.dumps([{'Name': 'bot', 'State': 'exited'}])
        problems = self._run(data)
        assert problems == ['bot: state=exited']

    def test_dead_container_is_problem(self):
        data = json.dumps([{'Name': 'bot', 'State': 'dead'}])
        problems = self._run(data)
        assert problems == ['bot: state=dead']

    def test_unhealthy_container_is_problem(self):
        data = json.dumps([{'Name': 'bot', 'State': 'running', 'Health': 'unhealthy'}])
        problems = self._run(data)
        assert problems == ['bot: health=unhealthy']

    def test_multiple_problems_all_reported(self):
        data = json.dumps([
            {'Name': 'bot', 'State': 'exited'},
            {'Name': 'db', 'State': 'running', 'Health': 'unhealthy'},
        ])
        problems = self._run(data)
        assert 'bot: state=exited' in problems
        assert 'db: health=unhealthy' in problems
        assert len(problems) == 2

    def test_docker_compose_failure_returns_error(self):
        problems = self._run(stdout='', returncode=1, stderr='permission denied')
        assert len(problems) == 1
        assert 'docker compose ps failed' in problems[0]

    def test_unparseable_json_returns_error(self):
        problems = self._run(stdout='not valid json at all')
        assert len(problems) == 1
        assert 'could not parse' in problems[0]

    def test_jsonl_format_parsed_correctly(self):
        # one JSON object per line (JSONL), not an array
        lines = '\n'.join([
            json.dumps({'Name': 'bot', 'State': 'running'}),
            json.dumps({'Name': 'db', 'State': 'exited'}),
        ])
        problems = self._run(lines)
        assert problems == ['db: state=exited']

    def test_json_array_format_parsed_correctly(self):
        data = json.dumps([
            {'Name': 'bot', 'State': 'running'},
            {'Name': 'db', 'State': 'running'},
        ])
        assert self._run(data) == []

    def test_empty_output_returns_empty(self):
        assert self._run('') == []

    def test_service_name_falls_back_to_service_key(self):
        data = json.dumps([{'Service': 'worker', 'State': 'exited'}])
        problems = self._run(data)
        assert problems == ['worker: state=exited']

    def test_service_name_falls_back_to_question_mark(self):
        data = json.dumps([{'State': 'dead'}])
        problems = self._run(data)
        assert problems == ['?: state=dead']


# ---------------------------------------------------------------------------
# abort
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# pyproject.toml version bump regex
# ---------------------------------------------------------------------------


class TestPyprojectVersionBump:
    """the deploy script uses re.sub to update the version in pyproject.toml"""

    _pattern = r'^version = "[^"]+"'

    def test_replaces_version_line(self):
        content = '[project]\nname = "attubot"\nversion = "1.2"\ndescription = "a bot"\n'
        result = re.sub(self._pattern, 'version = "1.3"', content, count=1, flags=re.MULTILINE)
        assert 'version = "1.3"' in result
        assert 'version = "1.2"' not in result

    def test_preserves_other_lines(self):
        content = '[project]\nname = "attubot"\nversion = "1.2"\ndescription = "a bot"\n'
        result = re.sub(self._pattern, 'version = "1.3"', content, count=1, flags=re.MULTILINE)
        assert 'name = "attubot"' in result
        assert 'description = "a bot"' in result

    def test_only_replaces_first_match(self):
        content = '[project]\nversion = "1.2"\n\n[tool.other]\nversion = "0.9"\n'
        result = re.sub(self._pattern, 'version = "1.3"', content, count=1, flags=re.MULTILINE)
        assert result.count('version = "1.3"') == 1
        assert 'version = "0.9"' in result


# ---------------------------------------------------------------------------
# abort
# ---------------------------------------------------------------------------


class TestAbort:
    def test_exits_with_code_1(self):
        with pytest.raises(SystemExit) as exc_info:
            abort('something went wrong')
        assert exc_info.value.code == 1

    def test_message_written_to_stderr(self, capsys):
        with pytest.raises(SystemExit):
            abort('something went wrong')
        captured = capsys.readouterr()
        assert 'something went wrong' in captured.err


# ---------------------------------------------------------------------------
# deploy_only_run
# ---------------------------------------------------------------------------


class TestDeployOnlyRun:
    """resume-deploy path: trunk is already at the new tag; just restart + push (with rollback on failure)"""

    def _patches(self, *, dirty: str = '', tests_raise: Exception | None = None, restart_raise: Exception | None = None, health: list[str] | None = None):
        """build the stack of patches the deploy_only_run path needs"""
        health = health or []

        def fake_git(args, cwd=None):
            if args[:2] == ['status', '--porcelain']:
                return dirty
            if args[:2] == ['rev-parse', 'HEAD']:
                return 'abc123'
            if args[:2] == ['describe', '--tags']:
                return '78.2.0'
            if args[:2] == ['push', 'origin']:
                return ''
            return ''

        def fake_run_cmd(*_a, **_kw):
            if tests_raise is not None:
                raise tests_raise
            return ''

        # only the bare ['docker', 'compose', 'up', ...] subprocess.run calls go through this mock; tests path goes through run_cmd above
        def fake_subprocess_run(cmd, *_a, **kw):
            if cmd[:3] == ['docker', 'compose', 'up'] and restart_raise is not None and not kw.get('check', False) is False:
                # only the initial restart raises, not the rollback rebuild (which uses check=False)
                raise restart_raise
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        return [
            patch('deploy.git_cmd', side_effect=fake_git),
            patch('deploy.run_cmd', side_effect=fake_run_cmd),
            patch('deploy.subprocess.run', side_effect=fake_subprocess_run),
            patch('deploy.time.sleep'),
            patch('deploy.check_container_health', return_value=health),
        ]

    def _enter(self, patches):
        return [p.__enter__() for p in patches]

    def _exit(self, patches):
        for p in patches:
            p.__exit__(None, None, None)

    def test_happy_path_pushes_trunk(self):
        patches = self._patches()
        mocks = self._enter(patches)
        try:
            git_mock, run_cmd_mock, subprocess_mock, sleep_mock, health_mock = mocks
            deploy_only_run(skip_tests=False, dry_run=False)

            # tests ran, containers restarted, health checked, push happened
            assert run_cmd_mock.called
            restart_calls = [c for c in subprocess_mock.call_args_list if c[0][0][:3] == ['docker', 'compose', 'up']]
            assert len(restart_calls) == 1
            sleep_mock.assert_called_once_with(60)
            health_mock.assert_called_once()
            push_calls = [c for c in git_mock.call_args_list if c[0][0][:2] == ['push', 'origin']]
            assert len(push_calls) == 1
        finally:
            self._exit(patches)

    def test_dirty_trunk_aborts_before_any_action(self):
        patches = self._patches(dirty=' M attubot/foo.py\n')
        mocks = self._enter(patches)
        try:
            _, run_cmd_mock, subprocess_mock, sleep_mock, _ = mocks
            with pytest.raises(SystemExit) as exc:
                deploy_only_run()
            assert exc.value.code == 1
            run_cmd_mock.assert_not_called()
            sleep_mock.assert_not_called()
            subprocess_mock.assert_not_called()
        finally:
            self._exit(patches)

    def test_skip_tests_omits_test_run(self):
        patches = self._patches()
        mocks = self._enter(patches)
        try:
            _, run_cmd_mock, _, _, _ = mocks
            deploy_only_run(skip_tests=True, dry_run=False)
            run_cmd_mock.assert_not_called()
        finally:
            self._exit(patches)

    def test_unhealthy_containers_trigger_rollback(self):
        patches = self._patches(health=['bot: state=exited'])
        mocks = self._enter(patches)
        try:
            _, _, subprocess_mock, _, _ = mocks
            with pytest.raises(SystemExit) as exc:
                deploy_only_run(skip_tests=True, dry_run=False)
            assert exc.value.code == 1

            # rollback ran: git reset --hard + docker compose up
            reset_calls = [c for c in subprocess_mock.call_args_list if c[0][0][:3] == ['git', 'reset', '--hard']]
            rebuild_calls = [c for c in subprocess_mock.call_args_list if c[0][0][:3] == ['docker', 'compose', 'up']]
            assert len(reset_calls) == 1
            assert reset_calls[0][0][0] == ['git', 'reset', '--hard', 'abc123']
            # one initial restart + one rollback rebuild
            assert len(rebuild_calls) == 2
        finally:
            self._exit(patches)

    def test_dry_run_skips_subprocess_and_push(self):
        patches = self._patches()
        mocks = self._enter(patches)
        try:
            git_mock, _, subprocess_mock, sleep_mock, health_mock = mocks
            deploy_only_run(skip_tests=True, dry_run=True)
            subprocess_mock.assert_not_called()
            sleep_mock.assert_not_called()
            health_mock.assert_not_called()
            push_calls = [c for c in git_mock.call_args_list if c[0][0][:2] == ['push', 'origin']]
            assert push_calls == []
        finally:
            self._exit(patches)


# ---------------------------------------------------------------------------
# pyproject lock file in bump commit
# ---------------------------------------------------------------------------


class TestUvLockInBumpCommit:
    """the bump commit step git-adds uv.lock alongside __init__.py and pyproject.toml so lockfile updates ride along"""

    def test_uv_lock_in_git_add_call(self):
        import deploy as _deploy

        source = Path(_deploy.__file__).read_text()
        # locate the commit-and-tag step and confirm uv.lock is included in the git add invocation
        match = re.search(r"git_cmd\(\['add',\s*str\(version_file\),\s*str\(pyproject_file\),\s*str\(lock_file\)\]\)", source)
        assert match is not None, 'expected git add to include uv.lock alongside version_file and pyproject_file'
