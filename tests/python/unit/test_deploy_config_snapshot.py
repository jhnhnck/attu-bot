# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_deploy_config_snapshot | per-tag config snapshots in scripts/deploy.py."""

import pytest


pytestmark = pytest.mark.unit


@pytest.fixture
def deploy(tmp_path, monkeypatch):
    """import deploy with prod_config pointed at a temp file."""
    import deploy as _deploy

    secrets = tmp_path / '.secrets'
    secrets.mkdir()
    monkeypatch.setattr(_deploy, 'prod_config', secrets / 'attu-bot.toml')
    return _deploy


# --- snapshot paths ---


def test_snapshot_path_is_config_name_plus_tag(deploy):
    assert deploy.config_snapshot('85.0.0').name == 'attu-bot.toml.85.0.0'


def test_snapshot_sits_beside_the_live_config(deploy):
    assert deploy.config_snapshot('85.0.0').parent == deploy.prod_config.parent


# --- save / restore round trip ---


def test_save_then_restore_returns_original_content(deploy):
    deploy.prod_config.write_text('config_version = "2.5.4"\n')
    deploy.save_config_snapshot('80.0.0')

    # migrate the live config forward, as an operator would before deploying
    deploy.prod_config.write_text('config_version = "2.9.0"\n')

    assert deploy.restore_config_snapshot('80.0.0') is True
    assert deploy.prod_config.read_text() == 'config_version = "2.5.4"\n'


def test_save_preserves_file_mode(deploy):
    deploy.prod_config.write_text('x = 1\n')
    deploy.prod_config.chmod(0o660)
    deploy.save_config_snapshot('80.0.0')
    # the containers mount this by uid/gid; copy2 must not widen it
    assert deploy.config_snapshot('80.0.0').stat().st_mode & 0o777 == 0o660


def test_restore_reports_false_when_absent(deploy):
    assert deploy.restore_config_snapshot('does-not-exist') is False


def test_save_without_a_live_config_does_not_raise(deploy):
    deploy.save_config_snapshot('80.0.0')
    assert not deploy.config_snapshot('80.0.0').exists()


def test_dry_run_writes_nothing(deploy):
    deploy.prod_config.write_text('x = 1\n')
    deploy.save_config_snapshot('80.0.0', dry_run=True)
    assert not deploy.config_snapshot('80.0.0').exists()


# --- the guard that keeps a revert from stranding prod ---


def test_require_aborts_when_snapshot_missing(deploy):
    # this is the regression: reverting code without its config left the bot down
    with pytest.raises(SystemExit) as exc:
        deploy.require_config_snapshot('80.0.0')
    assert exc.value.code == 1


def test_require_passes_when_snapshot_exists(deploy):
    deploy.prod_config.write_text('x = 1\n')
    deploy.save_config_snapshot('80.0.0')
    deploy.require_config_snapshot('80.0.0')  # must not raise


def test_require_force_proceeds_without_snapshot(deploy):
    deploy.require_config_snapshot('80.0.0', force=True)  # must not raise
