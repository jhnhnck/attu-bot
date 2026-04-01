"""
AttuBot - Tests for scripts/deploy.py
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from deploy import abort, check_container_health, compute_new_version, parse_version


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
