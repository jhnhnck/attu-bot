"""
AttuBot - Tests for scripts/run_tests.py
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import subprocess
from unittest.mock import patch

from run_tests import extract_counts, run_suite


def _proc(returncode: int = 0, stdout: str = '', stderr: str = '') -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# extract_counts
# ---------------------------------------------------------------------------


class TestExtractCounts:
    def test_simple_pass(self):
        assert extract_counts('5 passed in 1.2s') == '5 passed'

    def test_pass_and_fail(self):
        assert extract_counts('3 passed, 1 failed in 0.5s') == '3 passed, 1 failed'

    def test_warnings_stripped(self):
        assert extract_counts('2 passed, 1 warning in 0.1s') == '2 passed'

    def test_multiple_warnings_stripped(self):
        assert extract_counts('10 passed, 3 warnings in 2.0s') == '10 passed'

    def test_no_match_returns_none(self):
        assert extract_counts('no tests ran') is None

    def test_empty_string_returns_none(self):
        assert extract_counts('') is None

    def test_extracts_from_multiline_output(self):
        output = 'collecting ... \ntests/unit/test_foo.py::test_bar PASSED\ntests/unit/test_foo.py::test_baz FAILED\n======= 1 passed, 1 failed in 0.3s =======\n'
        result = extract_counts(output)
        assert result == '1 passed, 1 failed'

    def test_failed_only(self):
        assert extract_counts('2 failed in 0.8s') == '2 failed'

    def test_error_count_not_extracted(self):
        # "errors" don't match the pattern — only passed/failed
        assert extract_counts('1 error in 0.1s') is None


# ---------------------------------------------------------------------------
# run_suite
# ---------------------------------------------------------------------------


class TestRunSuite:
    _cmd = ['pytest', 'tests/']

    def test_success_returns_true(self):
        stdout = '5 passed in 1.0s'
        with patch('run_tests.subprocess.run', return_value=_proc(stdout=stdout)):
            passed, _, _ = run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        assert passed is True

    def test_success_elapsed_is_non_negative(self):
        with patch('run_tests.subprocess.run', return_value=_proc()):
            _, elapsed, _ = run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        assert elapsed >= 0

    def test_success_quiet_extracts_counts(self):
        stdout = '42 passed in 3.1s'
        with patch('run_tests.subprocess.run', return_value=_proc(stdout=stdout)):
            _, _, counts = run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        assert counts == '42 passed'

    def test_failure_returns_false(self):
        with patch('run_tests.subprocess.run', return_value=_proc(returncode=1, stdout='1 failed in 0.2s')):
            passed, _, _ = run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        assert passed is False

    def test_failure_quiet_prints_output_to_stderr(self, capsys):
        with patch('run_tests.subprocess.run', return_value=_proc(returncode=1, stdout='FAILED test_foo')):
            run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        captured = capsys.readouterr()
        assert 'FAILED test_foo' in captured.err

    def test_not_quiet_no_count_extraction(self):
        # when quiet=False, subprocess output is not captured, so counts is None
        with patch('run_tests.subprocess.run', return_value=_proc(returncode=0)):
            _, _, counts = run_suite('unit tests', self._cmd, quiet=False, step=1, total=4)
        assert counts is None

    def test_header_printed(self, capsys):
        with patch('run_tests.subprocess.run', return_value=_proc()):
            run_suite('unit tests', self._cmd, quiet=True, step=2, total=4)
        captured = capsys.readouterr()
        assert '[2/4]' in captured.out
        assert 'unit tests' in captured.out

    def test_failure_quiet_still_returns_counts(self):
        stdout = '1 passed, 3 failed in 0.9s'
        with patch('run_tests.subprocess.run', return_value=_proc(returncode=1, stdout=stdout)):
            _, _, counts = run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        assert counts == '1 passed, 3 failed'
