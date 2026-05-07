"""
AttuBot - Tests for scripts/run_tests.py
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import subprocess
from unittest.mock import patch

import pytest

from run_tests import extract_counts, run_suite


class _FakePopen:
    """minimal Popen stand-in covering the surface run_suite uses."""

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = '',
        stderr: str = '',
        interrupt_first: bool = False,
        timeout_on_drain: bool = False,
    ) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._interrupt_first = interrupt_first
        self._timeout_on_drain = timeout_on_drain
        self._calls = 0
        self.killed = False

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self._calls += 1
        if self._calls == 1 and self._interrupt_first:
            raise KeyboardInterrupt
        if self._calls == 2 and self._timeout_on_drain:
            raise subprocess.TimeoutExpired(cmd=[], timeout=timeout or 0)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


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
        # "errors" don't match the pattern - only passed/failed
        assert extract_counts('1 error in 0.1s') is None

    def test_vitest_single_suite(self):
        output = ' Test Files  1 passed (1)\n      Tests  15 passed (15)\n'
        assert extract_counts(output) == '15 passed'

    def test_vitest_multi_suite(self):
        output = ' Test Files  2 passed (2)\n      Tests  23 passed (23)\n'
        assert extract_counts(output) == '23 passed'

    def test_vitest_with_failures(self):
        output = ' Test Files  1 failed | 1 passed (2)\n      Tests  2 failed | 21 passed (23)\n'
        assert extract_counts(output) == '2 failed | 21 passed'


# ---------------------------------------------------------------------------
# run_suite
# ---------------------------------------------------------------------------


class TestRunSuite:
    _cmd = ['pytest', 'tests/']

    def test_success_returns_true(self):
        fake = _FakePopen(stdout='5 passed in 1.0s')
        with patch('run_tests.subprocess.Popen', return_value=fake):
            passed, _, _ = run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        assert passed is True

    def test_success_elapsed_is_non_negative(self):
        with patch('run_tests.subprocess.Popen', return_value=_FakePopen()):
            _, elapsed, _ = run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        assert elapsed >= 0

    def test_success_quiet_extracts_counts(self):
        fake = _FakePopen(stdout='42 passed in 3.1s')
        with patch('run_tests.subprocess.Popen', return_value=fake):
            _, _, counts = run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        assert counts == '42 passed'

    def test_failure_returns_false(self):
        fake = _FakePopen(returncode=1, stdout='1 failed in 0.2s')
        with patch('run_tests.subprocess.Popen', return_value=fake):
            passed, _, _ = run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        assert passed is False

    def test_failure_quiet_prints_output_to_stderr(self, capsys):
        fake = _FakePopen(returncode=1, stdout='FAILED test_foo')
        with patch('run_tests.subprocess.Popen', return_value=fake):
            run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        captured = capsys.readouterr()
        assert 'FAILED test_foo' in captured.err

    def test_not_quiet_no_count_extraction(self):
        # when quiet=False, subprocess output is not captured, so counts is None
        with patch('run_tests.subprocess.Popen', return_value=_FakePopen()):
            _, _, counts = run_suite('unit tests', self._cmd, quiet=False, step=1, total=4)
        assert counts is None

    def test_header_printed(self, capsys):
        with patch('run_tests.subprocess.Popen', return_value=_FakePopen()):
            run_suite('unit tests', self._cmd, quiet=True, step=2, total=4)
        captured = capsys.readouterr()
        assert '[2/4]' in captured.out
        assert 'unit tests' in captured.out

    def test_failure_quiet_still_returns_counts(self):
        fake = _FakePopen(returncode=1, stdout='1 passed, 3 failed in 0.9s')
        with patch('run_tests.subprocess.Popen', return_value=fake):
            _, _, counts = run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        assert counts == '1 passed, 3 failed'

    def test_interrupt_drains_output_and_reraises(self, capsys):
        # ^C during communicate(); the second communicate() drains the buffered output cleanly
        fake = _FakePopen(returncode=130, stdout='partial pytest output\nKeyboardInterrupt', interrupt_first=True)
        with patch('run_tests.subprocess.Popen', return_value=fake), pytest.raises(KeyboardInterrupt):
            run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        captured = capsys.readouterr()
        assert 'partial pytest output' in captured.err
        assert not fake.killed

    def test_interrupt_with_drain_timeout_kills_then_reraises(self, capsys):
        # ^C, then the drain communicate() times out -> kill, drain again, re-raise
        fake = _FakePopen(stdout='hung output', interrupt_first=True, timeout_on_drain=True)
        with patch('run_tests.subprocess.Popen', return_value=fake), pytest.raises(KeyboardInterrupt):
            run_suite('unit tests', self._cmd, quiet=True, step=1, total=4)
        captured = capsys.readouterr()
        assert 'hung output' in captured.err
        assert fake.killed
