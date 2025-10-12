import pytest
from click.testing import CliRunner

from vocabmaster import cli, utils


@pytest.fixture
def isolated_app_dir(tmp_path, monkeypatch):
    """Redirect the vocabmaster data directory to a temporary location."""

    def fake_setup_dir():
        tmp_path.mkdir(parents=True, exist_ok=True)
        return tmp_path

    monkeypatch.setattr(utils, "setup_dir", fake_setup_dir)
    monkeypatch.setattr(utils, "app_data_dir", tmp_path)

    config_file = tmp_path / "config.json"
    if config_file.exists():
        config_file.unlink()

    yield tmp_path

    if config_file.exists():
        config_file.unlink()


def invoke_cli(args):
    """Helper to execute the CLI with Click's testing runner."""
    runner = CliRunner()
    return runner.invoke(cli.vocabmaster, args)


class TestMissingConfiguration:
    """Scenarios where the CLI should handle absent default language configuration."""

    def test_anki_requires_default_pair(self, isolated_app_dir):
        result = invoke_cli(["anki"])

        assert result.exit_code == 1
        assert "No default language pair found" in result.output

    def test_config_default_requires_existing_pairs(self, isolated_app_dir):
        result = invoke_cli(["config", "default"])

        assert result.exit_code == 1
        assert "No language pairs found yet." in result.output
        assert "Run 'vocabmaster setup' to add one" in result.output

    def test_tokens_requires_default_pair(self, isolated_app_dir):
        result = invoke_cli(["tokens"])

        assert result.exit_code == 1
        assert "No default language pair found" in result.output

    def test_show_handles_absent_pairs(self, isolated_app_dir):
        result = invoke_cli(["show"])

        assert result.exit_code == 0
        assert "No language pairs found yet." in result.output
