from pathlib import Path

import pytest
from click.testing import CliRunner

from vocabmaster import cli, config_handler, utils


@pytest.fixture(autouse=True)
def reset_click_defaults(monkeypatch):
    """Ensure patched click helpers don't leak between tests."""
    monkeypatch.setattr("click.prompt", cli.click.prompt, raising=False)
    monkeypatch.setattr("click.confirm", cli.click.confirm, raising=False)
    yield


@pytest.fixture
def isolated_app_dir(tmp_path, monkeypatch):
    """Redirect config and storage paths to a temporary HOME directory for each test."""

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)

    storage_dir = tmp_path / ".vocabmaster"
    storage_dir.mkdir(parents=True, exist_ok=True)

    def fake_setup_dir():
        storage_dir.mkdir(parents=True, exist_ok=True)
        return storage_dir

    def fake_get_data_directory():
        return fake_setup_dir()

    def fake_get_default_data_directory():
        return storage_dir

    def fake_set_data_directory(path):
        config_handler.write_config(
            {**(config_handler.read_config() or {}), "data_dir": str(Path(path).expanduser())}
        )

    monkeypatch.setattr(utils, "setup_dir", fake_setup_dir)
    monkeypatch.setattr(cli, "setup_dir", fake_setup_dir)
    monkeypatch.setattr(config_handler, "get_data_directory", lambda: fake_get_data_directory())
    monkeypatch.setattr(
        config_handler, "get_default_data_directory", fake_get_default_data_directory
    )
    monkeypatch.setattr(config_handler, "set_data_directory", fake_set_data_directory)

    yield storage_dir


def invoke_cli(args, input_data=None):
    """Helper to execute the CLI with Click's testing runner."""
    runner = CliRunner()
    return runner.invoke(cli.vocabmaster, args, input=input_data)


def touch_setup_files(directory, *_):
    vocab = directory / "vocab.csv"
    anki = directory / "anki.csv"
    vocab.touch()
    anki.touch()
    return vocab, anki


def make_backup(
    tmp_path,
    filename,
    backup_type="vocabulary",
    timestamp="2024-01-01T00_00_00",
    size=1024,
):
    """
    Create a mock backup metadata dict matching `utils.list_backups()` output.

    Args:
        tmp_path: pytest tmp_path fixture for generating paths
        filename: Backup filename
        backup_type: One of "vocabulary", "gpt-response", "anki-deck", "pre-restore"
        timestamp: ISO timestamp with underscores replacing colons
        size: File size in bytes

    Returns:
        dict with keys: path, filename, timestamp, type, size, mtime
    """
    return {
        "path": tmp_path / filename,
        "filename": filename,
        "timestamp": timestamp,
        "type": backup_type,
        "size": size,
        "mtime": 0.0,
    }


class TestRootCommand:
    def test_help_displayed_when_no_subcommand(self):
        result = invoke_cli([])

        assert result.exit_code == 0
        assert "Usage" in result.output

    def test_config_group_help(self):
        result = invoke_cli(["config"])

        assert result.exit_code == 0
        assert "Manage storage location and API key settings" in result.output
        assert "dir" in result.output


class TestAddCommand:
    def test_add_handles_invalid_language_pair(self, isolated_app_dir, monkeypatch):
        def fail_pair(_pair):
            raise ValueError("Invalid language pair.")

        monkeypatch.setattr(cli.config_handler, "get_language_pair", fail_pair)

        result = invoke_cli(["add", "bonjour"])

        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "Invalid language pair." in result.output

    def test_add_requires_word_argument(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(cli.csv_handler, "word_exists", lambda word, path: False)
        monkeypatch.setattr(cli.csv_handler, "append_word", lambda word, path: None)
        monkeypatch.setattr(cli, "setup_files", touch_setup_files)

        result = invoke_cli(["add"])

        assert result.exit_code == 0
        assert "Please provide a word to add." in result.output

    def test_add_notifies_when_word_exists(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(cli.csv_handler, "word_exists", lambda word, path: True)
        monkeypatch.setattr(cli.csv_handler, "append_word", lambda word, path: None)
        monkeypatch.setattr(cli, "setup_files", touch_setup_files)

        result = invoke_cli(["add", "bonjour"])

        assert result.exit_code == 0
        assert "That word is already in your list" in result.output

    def test_add_appends_word_when_missing(self, isolated_app_dir, monkeypatch):
        captured = {}

        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(cli.csv_handler, "word_exists", lambda word, path: False)

        def capture_append(word, path):
            captured["word"] = word
            captured["path"] = path

        monkeypatch.setattr(cli.csv_handler, "append_word", capture_append)
        monkeypatch.setattr(cli, "setup_files", touch_setup_files)

        result = invoke_cli(["add", "to", "learn"])

        assert result.exit_code == 0
        assert "Added to your list" in result.output
        assert captured["word"] == "to learn"
        assert captured["path"].name == "vocab.csv"


class TestTranslateCommand:
    def test_translate_handles_invalid_pair(self, isolated_app_dir, monkeypatch):
        def fail_pair(_pair):
            raise ValueError("Pair missing.")

        monkeypatch.setattr(cli.config_handler, "get_language_pair", fail_pair)

        result = invoke_cli(["translate"])

        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "Pair missing." in result.output

    def test_translate_requires_non_empty_vocabulary(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        translations = isolated_app_dir / "vocab.csv"
        anki = isolated_app_dir / "anki.csv"
        translations.touch()
        anki.touch()
        monkeypatch.setattr(cli, "setup_files", lambda *_: (translations, anki))
        monkeypatch.setattr(cli.csv_handler, "ensure_csv_has_fieldnames", lambda path: None)
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: True)

        result = invoke_cli(["translate"])

        assert result.exit_code == 0
        assert "Your vocabulary list is empty" in result.output

    def test_translate_count_option_success(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        translations = isolated_app_dir / "vocab.csv"
        anki = isolated_app_dir / "anki.csv"
        translations.touch()
        anki.touch()
        monkeypatch.setattr(cli, "setup_files", lambda *_: (translations, anki))
        monkeypatch.setattr(cli.csv_handler, "ensure_csv_has_fieldnames", lambda path: None)
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)
        monkeypatch.setattr(
            cli.csv_handler, "get_words_to_translate", lambda path: ["word1", "word2"]
        )

        result = invoke_cli(["translate", "--count"])

        assert result.exit_code == 0
        assert "Number of words to translate" in result.output
        assert "2" in result.output

    def test_translate_count_option_handles_error(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        translations = isolated_app_dir / "vocab.csv"
        anki = isolated_app_dir / "anki.csv"
        translations.touch()
        anki.touch()
        monkeypatch.setattr(cli, "setup_files", lambda *_: (translations, anki))
        monkeypatch.setattr(cli.csv_handler, "ensure_csv_has_fieldnames", lambda path: None)
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)

        def fail_get_words(_path):
            raise RuntimeError("CSV corrupted")

        monkeypatch.setattr(cli.csv_handler, "get_words_to_translate", fail_get_words)

        result = invoke_cli(["translate", "--count"])

        assert result.exit_code == 0
        assert "Status:" in result.output
        assert "CSV corrupted" in result.output

    def test_translate_requires_api_key(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )
        monkeypatch.setattr(cli.csv_handler, "ensure_csv_has_fieldnames", lambda path: None)
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: False)

        called = {"explain": False}

        def record_explain():
            called["explain"] = True

        monkeypatch.setattr(cli, "openai_api_key_explain", record_explain)

        result = invoke_cli(["translate"])

        assert result.exit_code == 0
        assert called["explain"] is True

    def test_translate_handles_rate_limit_error(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )
        monkeypatch.setattr(cli.csv_handler, "ensure_csv_has_fieldnames", lambda path: None)
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)

        def fail_add(*_args, **_kwargs):
            raise cli.openai.error.RateLimitError("Too many requests", None)

        monkeypatch.setattr(cli.csv_handler, "add_translations_and_examples_to_file", fail_add)

        called = {"handler": False}

        def record_handler():
            called["handler"] = True

        monkeypatch.setattr(cli, "handle_rate_limit_error", record_handler)
        monkeypatch.setattr(cli, "generate_anki_deck", lambda *args, **kwargs: None)

        result = invoke_cli(["translate"])

        assert result.exit_code == 1
        assert called["handler"] is True
        assert "Error:" in result.output

    def test_translate_handles_all_translated_exception(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )
        monkeypatch.setattr(cli.csv_handler, "ensure_csv_has_fieldnames", lambda path: None)
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)

        def fail_add(*_args, **_kwargs):
            raise cli.csv_handler.AllWordsTranslatedError()

        monkeypatch.setattr(cli.csv_handler, "add_translations_and_examples_to_file", fail_add)
        monkeypatch.setattr(cli, "generate_anki_deck", lambda *args, **kwargs: None)

        result = invoke_cli(["translate"])

        assert result.exit_code == 0
        assert "No action needed" in result.output

    def test_translate_handles_generic_exception(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )
        monkeypatch.setattr(cli.csv_handler, "ensure_csv_has_fieldnames", lambda path: None)
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)

        def fail_add(*_args, **_kwargs):
            raise Exception("Permission denied")

        monkeypatch.setattr(cli.csv_handler, "add_translations_and_examples_to_file", fail_add)
        monkeypatch.setattr(cli, "generate_anki_deck", lambda *args, **kwargs: None)

        result = invoke_cli(["translate"])

        assert result.exit_code == 0
        assert "Status:" in result.output
        assert "Permission denied" in result.output

    def test_translate_success_flow_triggers_generation(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )

        translations_path = isolated_app_dir / "vocab.csv"
        anki_path = isolated_app_dir / "anki.csv"

        def fake_setup_files(directory, *_):
            return translations_path, anki_path

        translations = isolated_app_dir / "vocab.csv"
        anki = isolated_app_dir / "anki.csv"
        translations.touch()
        anki.touch()
        monkeypatch.setattr(cli, "setup_files", lambda *_: (translations, anki))
        monkeypatch.setattr(cli.csv_handler, "ensure_csv_has_fieldnames", lambda path: None)
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)

        called = {"add": False, "generate": False}

        def record_add(path, pair):
            called["add"] = (path, pair)

        def record_generate(*args):
            called["generate"] = args

        monkeypatch.setattr(cli.csv_handler, "add_translations_and_examples_to_file", record_add)
        monkeypatch.setattr(cli, "generate_anki_deck", record_generate)

        result = invoke_cli(["translate"])

        assert result.exit_code == 0
        assert called["add"][0] == translations_path
        assert called["generate"][0] == translations_path
        assert called["generate"][1] == anki_path


class TestGenerateAnkiDeck:
    def test_generate_anki_deck_invokes_csv_handler(self, capsys, monkeypatch):
        captured = {}

        def record_generate(translations, anki, language, mother, custom_deck_name=None):
            captured["args"] = (translations, anki, language, mother, custom_deck_name)

        monkeypatch.setattr(cli.csv_handler, "generate_anki_output_file", record_generate)

        translations = Path("/tmp/trans.csv")
        anki = Path("/tmp/anki.csv")

        cli.generate_anki_deck(translations, anki, "english", "french")

        out = capsys.readouterr().out
        assert "Generating Anki deck" in out
        assert captured["args"] == (translations, anki, "english", "french", None)


class TestAnkiCommand:
    def test_anki_requires_default_pair(self, isolated_app_dir, monkeypatch):
        def fail_pair(option):
            raise ValueError("No default language pair found.")

        monkeypatch.setattr(cli.config_handler, "get_language_pair", fail_pair)

        result = invoke_cli(["anki"])

        assert result.exit_code == 1
        assert "No default language pair found." in result.output
        assert "vocabmaster pairs add" in result.output

    def test_anki_generates_deck_when_default_set(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler,
            "get_language_pair",
            lambda option: ("english", "french"),
        )
        monkeypatch.setattr(
            cli.config_handler,
            "get_deck_name",
            lambda *args: None,
        )

        translations = isolated_app_dir / "vocab.csv"
        anki = isolated_app_dir / "anki.csv"

        monkeypatch.setattr(cli, "setup_files", lambda *_args: (translations, anki))

        called = {"deck": False}

        def record_generate(*args):
            called["deck"] = args

        monkeypatch.setattr(cli, "generate_anki_deck", record_generate)

        result = invoke_cli(["anki"])

        assert result.exit_code == 0
        assert called["deck"][0] == translations
        assert called["deck"][1] == anki
        assert called["deck"][2:] == ("english", "french", None)

    def test_anki_generates_with_pair_option(self, isolated_app_dir, monkeypatch):
        def capture_pair(option):
            assert option == "spanish:english"
            return "spanish", "english"

        monkeypatch.setattr(cli.config_handler, "get_language_pair", capture_pair)
        monkeypatch.setattr(
            cli.config_handler,
            "get_deck_name",
            lambda *args: None,
        )

        translations = isolated_app_dir / "vocab.csv"
        anki = isolated_app_dir / "anki.csv"
        monkeypatch.setattr(cli, "setup_files", lambda *_args: (translations, anki))

        called = {}

        def record_generate(translations_path, anki_path, language, mother, custom_deck_name=None):
            called["translations"] = translations_path
            called["anki"] = anki_path
            called["language"] = language
            called["mother"] = mother

        monkeypatch.setattr(cli, "generate_anki_deck", record_generate)

        result = invoke_cli(["anki", "--pair", "spanish:english"])

        assert result.exit_code == 0
        assert called["language"] == "spanish"
        assert called["mother"] == "english"


class TestConfigKeyCommand:
    def test_config_key_confirms_when_present(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)

        result = invoke_cli(["config", "key"])

        assert result.exit_code == 0
        assert "OpenAI API key found!" in result.output
        assert "vocabmaster translate" in result.output

    def test_config_key_prompts_when_missing(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: False)

        called = {"explain": False}

        def record_explain():
            called["explain"] = True

        monkeypatch.setattr(cli, "openai_api_key_explain", record_explain)

        result = invoke_cli(["config", "key"])

        assert result.exit_code == 0
        assert called["explain"] is True


class TestTokensCommand:
    def test_tokens_requires_default_pair(self, isolated_app_dir, monkeypatch):
        def fail_pair(option):
            raise ValueError("No default language pair found")

        monkeypatch.setattr(cli.config_handler, "get_language_pair", fail_pair)

        result = invoke_cli(["tokens"])

        assert result.exit_code == 1
        assert "No default language pair found" in result.output

    def test_tokens_requires_words(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        translations = isolated_app_dir / "vocab.csv"
        anki = isolated_app_dir / "anki.csv"
        translations.touch()
        anki.touch()
        monkeypatch.setattr(cli, "setup_files", lambda *_: (translations, anki))
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: True)

        result = invoke_cli(["tokens"])

        assert result.exit_code == 0
        assert "The list is empty!" in result.output

    def test_tokens_handles_get_words_error(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        translations = isolated_app_dir / "vocab.csv"
        anki = isolated_app_dir / "anki.csv"
        translations.touch()
        anki.touch()
        monkeypatch.setattr(cli, "setup_files", lambda *_: (translations, anki))
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)

        def fail_words(_path):
            raise RuntimeError("Cannot parse")

        monkeypatch.setattr(cli.csv_handler, "get_words_to_translate", fail_words)

        result = invoke_cli(["tokens"])

        assert result.exit_code == 0
        assert "Status:" in result.output
        assert "Cannot parse" in result.output
        assert "Therefore, the next prompt cannot be evaluated." in result.output

    def test_tokens_outputs_estimated_cost(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        translations = isolated_app_dir / "vocab.csv"
        anki = isolated_app_dir / "anki.csv"
        translations.touch()
        anki.touch()
        monkeypatch.setattr(cli, "setup_files", lambda *_: (translations, anki))
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)
        monkeypatch.setattr(cli.csv_handler, "get_words_to_translate", lambda path: ["word"])
        monkeypatch.setattr(
            cli.gpt_integration,
            "format_prompt",
            lambda *_: [{"role": "system", "content": "prompt"}],
        )
        monkeypatch.setattr(cli.gpt_integration, "num_tokens_from_messages", lambda *_, **__: 100)

        def fake_estimate(prompt, model):
            assert model == "gpt-4.1"
            return "0.004"

        monkeypatch.setattr(cli.gpt_integration, "estimate_prompt_cost", fake_estimate)

        result = invoke_cli(["tokens"])

        assert result.exit_code == 0
        assert "Number of tokens in the prompt:" in result.output
        assert "Cost estimate for gpt-4.1 model:" in result.output
        assert "$0.004" in result.output

    def test_tokens_pair_option(self, isolated_app_dir, monkeypatch):
        def capture_pair(option):
            assert option == "spanish:english"
            return "spanish", "english"

        monkeypatch.setattr(cli.config_handler, "get_language_pair", capture_pair)
        translations = isolated_app_dir / "vocab.csv"
        anki = isolated_app_dir / "anki.csv"
        translations.touch()
        anki.touch()
        monkeypatch.setattr(cli, "setup_files", lambda *_: (translations, anki))
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)
        monkeypatch.setattr(cli.csv_handler, "get_words_to_translate", lambda path: ["palabra"])
        monkeypatch.setattr(
            cli.gpt_integration,
            "format_prompt",
            lambda *_: [{"role": "system", "content": "prompt"}],
        )
        monkeypatch.setattr(cli.gpt_integration, "num_tokens_from_messages", lambda *_, **__: 210)
        monkeypatch.setattr(
            cli.gpt_integration,
            "estimate_prompt_cost",
            lambda *args, **kwargs: {
                "tokens": 210,
                "cost": "0.010",
                "price_available": True,
            },
        )

        result = invoke_cli(["tokens", "--pair", "spanish:english"])

        assert result.exit_code == 0
        assert "Number of tokens in the prompt:" in result.output


class TestRecoverGroup:
    """Tests for the recover command group."""

    def test_recover_help_displayed_when_no_subcommand(self):
        """recover shows help when no subcommand is provided."""
        result = invoke_cli(["recover"])

        assert result.exit_code == 0
        assert "Backup recovery and data restoration tools" in result.output
        assert "list" in result.output
        assert "restore" in result.output
        assert "validate" in result.output


class TestRecoverListCommand:
    """Tests for the recover list command."""

    def test_recover_list_no_backups(self, isolated_app_dir, monkeypatch):
        """recover list shows message when no backups exist."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(cli.utils, "list_backups", lambda *_: [])

        result = invoke_cli(["recover", "list"])

        assert result.exit_code == 0
        assert "No backups found for english:french" in result.output

    def test_recover_list_displays_backups(self, isolated_app_dir, monkeypatch, tmp_path):
        """recover list displays available backups with metadata."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.utils,
            "list_backups",
            lambda *_: [
                make_backup(
                    tmp_path,
                    "vocab_list_english-french_2024-01-01T00_00_00.bak",
                    backup_type="vocabulary",
                    size=2048,
                ),
                make_backup(
                    tmp_path,
                    "gpt_request_2024-01-02T14_30_00.bak",
                    backup_type="gpt-response",
                    timestamp="2024-01-02T14_30_00",
                    size=512,
                ),
            ],
        )
        monkeypatch.setattr(
            cli.recovery, "format_backup_timestamp", lambda ts: "2024-01-01 00:00:00"
        )

        result = invoke_cli(["recover", "list"])

        assert result.exit_code == 0
        assert "Backups for english:french (2 total)" in result.output
        assert "[vocabulary]" in result.output
        assert "[gpt-response]" in result.output
        assert "vocab_list_english-french_2024-01-01T00_00_00.bak" in result.output

    def test_recover_list_uses_pair_option(self, isolated_app_dir, monkeypatch):
        """recover list uses specified --pair option."""
        captured = {}

        def capture_pair(pair):
            captured["pair"] = pair
            return "spanish", "english"

        monkeypatch.setattr(cli.config_handler, "get_language_pair", capture_pair)
        monkeypatch.setattr(cli.utils, "list_backups", lambda *_: [])

        result = invoke_cli(["recover", "list", "--pair", "spanish:english"])

        assert result.exit_code == 0
        assert captured["pair"] == "spanish:english"

    def test_recover_list_requires_language_pair(self, isolated_app_dir, monkeypatch):
        """recover list shows error with hint when no language pair configured."""

        def fail_pair(_pair):
            raise ValueError("No default language pair found.")

        monkeypatch.setattr(cli.config_handler, "get_language_pair", fail_pair)

        result = invoke_cli(["recover", "list"])

        assert result.exit_code == 1
        assert "No default language pair found." in result.output
        assert "vocabmaster pairs add" in result.output


class TestRecoverRestoreCommand:
    """Tests for the recover restore command."""

    def test_recover_restore_requires_selection(self, isolated_app_dir, monkeypatch):
        """recover restore fails if neither --latest nor --backup-id provided."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )

        result = invoke_cli(["recover", "restore"])

        assert result.exit_code == 1
        assert "Specify --latest or --backup-id." in result.output
        assert "vocabmaster recover list" in result.output

    def test_recover_restore_rejects_both_options(self, isolated_app_dir, monkeypatch):
        """recover restore fails if both --latest and --backup-id provided."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )

        result = invoke_cli(["recover", "restore", "--latest", "--backup-id", "1"])

        assert result.exit_code == 1
        assert "Cannot use both --latest and --backup-id." in result.output

    def test_recover_restore_latest_no_backups(self, isolated_app_dir, monkeypatch):
        """recover restore --latest shows error when no vocabulary backups exist."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(cli.recovery, "get_latest_backup", lambda *_: None)

        result = invoke_cli(["recover", "restore", "--latest"])

        assert result.exit_code == 1
        assert "No vocabulary backups found." in result.output

    def test_recover_restore_backup_id_invalid(self, isolated_app_dir, monkeypatch, tmp_path):
        """recover restore fails with invalid backup ID and shows valid range."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.utils,
            "list_backups",
            lambda *_: [make_backup(tmp_path, "vocab_backup.bak", backup_type="vocabulary")],
        )

        result = invoke_cli(["recover", "restore", "--backup-id", "5"])

        assert result.exit_code == 1
        assert "Invalid backup ID" in result.output
        assert "Must be between 1 and 1" in result.output

    def test_recover_restore_backup_id_no_backups(self, isolated_app_dir, monkeypatch):
        """recover restore shows error with hint when no backups exist."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(cli.utils, "list_backups", lambda *_: [])

        result = invoke_cli(["recover", "restore", "--backup-id", "1"])

        assert result.exit_code == 1
        assert "No backups found." in result.output
        assert "vocabmaster recover list" in result.output

    def test_recover_restore_user_cancels(self, isolated_app_dir, monkeypatch, tmp_path):
        """recover restore respects user cancellation at confirmation prompt."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.recovery,
            "get_latest_backup",
            lambda *_: make_backup(tmp_path, "vocab_backup.bak", backup_type="vocabulary"),
        )

        def fail_restore(*_args, **_kwargs):
            pytest.fail("Restore should not run after user cancels.")

        monkeypatch.setattr(cli.recovery, "restore_vocabulary_from_backup", fail_restore)

        result = invoke_cli(["recover", "restore", "--latest"], input_data="n\n")

        assert result.exit_code == 0
        assert "Restore cancelled." in result.output

    def test_recover_restore_success(self, isolated_app_dir, monkeypatch, tmp_path):
        """recover restore completes successfully and shows paths."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.recovery,
            "get_latest_backup",
            lambda *_: make_backup(tmp_path, "vocab_backup.bak", backup_type="vocabulary"),
        )
        monkeypatch.setattr(
            cli.recovery,
            "restore_vocabulary_from_backup",
            lambda *_: {
                "success": True,
                "restored_path": tmp_path / "vocab.csv",
                "pre_restore_backup": tmp_path / "pre_restore.bak",
                "error": None,
            },
        )

        result = invoke_cli(["recover", "restore", "--latest"], input_data="y\n")

        assert result.exit_code == 0
        assert "Vocabulary restored successfully!" in result.output
        assert "Restored to:" in result.output
        assert "Pre-restore backup:" in result.output

    def test_recover_restore_failure(self, isolated_app_dir, monkeypatch, tmp_path):
        """recover restore shows error message on failure."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.utils,
            "list_backups",
            lambda *_: [make_backup(tmp_path, "vocab_backup.bak", backup_type="vocabulary")],
        )
        monkeypatch.setattr(
            cli.recovery,
            "restore_vocabulary_from_backup",
            lambda *_: {
                "success": False,
                "restored_path": None,
                "pre_restore_backup": None,
                "error": "Backup corrupted",
            },
        )

        result = invoke_cli(["recover", "restore", "--backup-id", "1"], input_data="y\n")

        assert result.exit_code == 1
        assert "Restore failed: Backup corrupted" in result.output

    def test_recover_restore_warns_non_vocabulary_backup(
        self, isolated_app_dir, monkeypatch, tmp_path
    ):
        """recover restore warns when selecting non-vocabulary backup."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.utils,
            "list_backups",
            lambda *_: [make_backup(tmp_path, "gpt_request.bak", backup_type="gpt-response")],
        )

        def fail_restore(*_args, **_kwargs):
            pytest.fail("Restore should not run after user declines warning.")

        monkeypatch.setattr(cli.recovery, "restore_vocabulary_from_backup", fail_restore)

        result = invoke_cli(["recover", "restore", "--backup-id", "1"], input_data="n\n")

        assert result.exit_code == 0
        assert "Selected backup is a gpt-response" in result.output
        assert "Restore cancelled." in result.output

    def test_recover_restore_non_vocabulary_backup_accepted(
        self, isolated_app_dir, monkeypatch, tmp_path
    ):
        """recover restore proceeds when user accepts non-vocabulary backup warning."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.utils,
            "list_backups",
            lambda *_: [make_backup(tmp_path, "gpt_request.bak", backup_type="gpt-response")],
        )
        monkeypatch.setattr(
            cli.recovery,
            "restore_vocabulary_from_backup",
            lambda *_: {
                "success": True,
                "restored_path": tmp_path / "vocab.csv",
                "pre_restore_backup": None,
                "error": None,
            },
        )

        # First 'y' accepts warning, second 'y' confirms restore
        result = invoke_cli(["recover", "restore", "--backup-id", "1"], input_data="y\ny\n")

        assert result.exit_code == 0
        assert "Vocabulary restored successfully!" in result.output

    def test_recover_restore_uses_pair_option(self, isolated_app_dir, monkeypatch):
        """recover restore uses specified --pair option."""
        captured = {}

        def capture_pair(pair):
            captured["pair"] = pair
            return "spanish", "english"

        monkeypatch.setattr(cli.config_handler, "get_language_pair", capture_pair)
        monkeypatch.setattr(cli.recovery, "get_latest_backup", lambda *_: None)

        result = invoke_cli(["recover", "restore", "--latest", "--pair", "spanish:english"])

        assert result.exit_code == 1
        assert captured["pair"] == "spanish:english"

    def test_recover_restore_invalid_pair(self, isolated_app_dir, monkeypatch):
        """recover restore shows error for invalid language pair."""

        def fail_pair(_pair):
            raise ValueError("Invalid language pair format.")

        monkeypatch.setattr(cli.config_handler, "get_language_pair", fail_pair)

        result = invoke_cli(["recover", "restore", "--latest"])

        assert result.exit_code == 1
        assert "Invalid language pair format." in result.output

    def test_recover_restore_backup_id_zero(self, isolated_app_dir, monkeypatch, tmp_path):
        """recover restore fails with backup ID 0 (boundary condition)."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.utils,
            "list_backups",
            lambda *_: [make_backup(tmp_path, "vocab.bak", backup_type="vocabulary")],
        )

        result = invoke_cli(["recover", "restore", "--backup-id", "0"])

        assert result.exit_code == 1
        assert "Invalid backup ID" in result.output

    def test_recover_restore_pre_restore_no_warning(self, isolated_app_dir, monkeypatch, tmp_path):
        """recover restore accepts pre-restore type without warning."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.utils,
            "list_backups",
            lambda *_: [make_backup(tmp_path, "pre_restore_backup.bak", backup_type="pre-restore")],
        )
        monkeypatch.setattr(
            cli.recovery,
            "restore_vocabulary_from_backup",
            lambda *_: {
                "success": True,
                "restored_path": tmp_path / "vocab.csv",
                "pre_restore_backup": None,
                "error": None,
            },
        )

        # Only one 'y' needed (no warning prompt for pre-restore type)
        result = invoke_cli(["recover", "restore", "--backup-id", "1"], input_data="y\n")

        assert result.exit_code == 0
        assert "Selected backup is a" not in result.output
        assert "Vocabulary restored successfully!" in result.output

    def test_recover_restore_warns_anki_deck_backup(self, isolated_app_dir, monkeypatch, tmp_path):
        """recover restore warns when selecting anki-deck backup."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.utils,
            "list_backups",
            lambda *_: [make_backup(tmp_path, "anki_deck.bak", backup_type="anki-deck")],
        )

        def fail_restore(*_args, **_kwargs):
            pytest.fail("Restore should not run after user declines warning.")

        monkeypatch.setattr(cli.recovery, "restore_vocabulary_from_backup", fail_restore)

        result = invoke_cli(["recover", "restore", "--backup-id", "1"], input_data="n\n")

        assert result.exit_code == 0
        assert "Selected backup is a anki-deck" in result.output
        assert "Restore cancelled." in result.output


class TestRecoverValidateCommand:
    """Tests for the recover validate command."""

    def test_recover_validate_no_backups(self, isolated_app_dir, monkeypatch):
        """recover validate shows message when no backups exist."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.recovery,
            "validate_all_backups",
            lambda *_: {"total": 0, "valid": 0, "invalid": 0, "results": []},
        )

        result = invoke_cli(["recover", "validate"])

        assert result.exit_code == 0
        assert "No backups found." in result.output

    def test_recover_validate_all_valid(self, isolated_app_dir, monkeypatch):
        """recover validate shows OK status for valid backups."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.recovery,
            "validate_all_backups",
            lambda *_: {
                "total": 2,
                "valid": 2,
                "invalid": 0,
                "results": [
                    {
                        "filename": "vocab_backup_1.bak",
                        "type": "vocabulary",
                        "valid": True,
                        "rows": 10,
                        "format_version": "3-col",
                        "error": None,
                    },
                    {
                        "filename": "vocab_backup_2.bak",
                        "type": "vocabulary",
                        "valid": True,
                        "rows": 5,
                        "format_version": "3-col",
                        "error": None,
                    },
                ],
            },
        )

        result = invoke_cli(["recover", "validate"])

        assert result.exit_code == 0
        assert "Validation Summary" in result.output
        assert "Total backups: 2" in result.output
        assert "Valid: 2" in result.output
        assert "OK" in result.output
        assert "Rows: 10" in result.output

    def test_recover_validate_with_invalid_backups(self, isolated_app_dir, monkeypatch):
        """recover validate shows FAIL status and error details for invalid backups."""
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(
            cli.recovery,
            "validate_all_backups",
            lambda *_: {
                "total": 2,
                "valid": 1,
                "invalid": 1,
                "results": [
                    {
                        "filename": "vocab_ok.bak",
                        "type": "vocabulary",
                        "valid": True,
                        "rows": 10,
                        "format_version": "3-col",
                        "error": None,
                    },
                    {
                        "filename": "vocab_bad.bak",
                        "type": "vocabulary",
                        "valid": False,
                        "rows": None,
                        "format_version": "unknown",
                        "error": "Missing required columns",
                    },
                ],
            },
        )

        result = invoke_cli(["recover", "validate"])

        assert result.exit_code == 0
        assert "Total backups: 2" in result.output
        assert "Valid: 1" in result.output
        assert "Invalid: 1" in result.output
        assert "FAIL" in result.output
        assert "Missing required columns" in result.output
        assert "backup(s) have issues" in result.output

    def test_recover_validate_uses_pair_option(self, isolated_app_dir, monkeypatch):
        """recover validate uses specified --pair option."""
        captured = {}

        def capture_pair(pair):
            captured["pair"] = pair
            return "spanish", "english"

        monkeypatch.setattr(cli.config_handler, "get_language_pair", capture_pair)
        monkeypatch.setattr(
            cli.recovery,
            "validate_all_backups",
            lambda *_: {"total": 0, "valid": 0, "invalid": 0, "results": []},
        )

        result = invoke_cli(["recover", "validate", "--pair", "spanish:english"])

        assert result.exit_code == 0
        assert captured["pair"] == "spanish:english"

    def test_recover_validate_invalid_pair(self, isolated_app_dir, monkeypatch):
        """recover validate shows error for invalid language pair."""

        def fail_pair(_pair):
            raise ValueError("No default language pair found.")

        monkeypatch.setattr(cli.config_handler, "get_language_pair", fail_pair)

        result = invoke_cli(["recover", "validate"])

        assert result.exit_code == 1
        assert "No default language pair found." in result.output


class TestConfigHandlerRemove:
    def test_remove_language_pair_errors_when_empty(self, isolated_app_dir):
        with pytest.raises(ValueError, match="No language pairs configured."):
            config_handler.remove_language_pair("english", "french")

    def test_remove_language_pair_errors_when_missing(self, isolated_app_dir):
        config_handler.set_language_pair("english", "french")

        with pytest.raises(ValueError, match="Language pair not found."):
            config_handler.remove_language_pair("spanish", "english")

    def test_remove_language_pair_removes_default(self, isolated_app_dir):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("spanish", "english")

        removed_default = config_handler.remove_language_pair("spanish", "english")

        assert removed_default is True
        assert config_handler.get_default_language_pair() is None
        assert config_handler.get_all_language_pairs() == [
            {"language_to_learn": "english", "mother_tongue": "french"}
        ]

    def test_remove_language_pair_non_default(self, isolated_app_dir):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        removed_default = config_handler.remove_language_pair("spanish", "english")

        assert removed_default is False
        assert config_handler.get_default_language_pair() == {
            "language_to_learn": "english",
            "mother_tongue": "french",
        }
        assert config_handler.get_all_language_pairs() == [
            {"language_to_learn": "english", "mother_tongue": "french"}
        ]


class TestHelperFunctions:
    def test_print_default_language_pair_none(self, isolated_app_dir, capsys):
        returned = cli.print_default_language_pair()

        captured = capsys.readouterr()
        assert returned is None
        assert "No default language pair configured yet." in captured.err

    def test_print_default_language_pair_existing(self, isolated_app_dir, capsys):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        returned = cli.print_default_language_pair()

        output = capsys.readouterr().out
        assert returned == {"language_to_learn": "english", "mother_tongue": "french"}
        assert "english:french" in output

    def test_print_all_language_pairs_empty(self, isolated_app_dir, capsys):
        returned = cli.print_all_language_pairs()

        captured = capsys.readouterr()
        assert returned == []
        assert "No language pairs found yet." in captured.err
        assert "vocabmaster pairs add" in captured.err

    def test_print_all_language_pairs_lists_items(self, isolated_app_dir, capsys):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")

        returned = cli.print_all_language_pairs()

        output = capsys.readouterr().out
        assert len(returned) == 2
        assert "1. english:french" in output
        assert "2. spanish:english" in output

    def test_openai_api_key_explain_windows(self, monkeypatch, capsys):
        monkeypatch.setattr(cli.platform, "system", lambda: "Windows")

        cli.openai_api_key_explain()

        captured = capsys.readouterr()
        assert "setx OPENAI_API_KEY your_key" in captured.err

    def test_openai_api_key_explain_unix(self, monkeypatch, capsys):
        monkeypatch.setattr(cli.platform, "system", lambda: "Linux")

        cli.openai_api_key_explain()

        captured = capsys.readouterr()
        assert "export OPENAI_API_KEY=YOUR_KEY" in captured.err

    def test_handle_rate_limit_error_guidance(self, capsys):
        cli.handle_rate_limit_error()

        output = capsys.readouterr().out
        assert "You might not have set a usage rate limit" in output
        assert "OpenAI rate limits" in output

    def test_config_dir_updates_data_directory(self, fake_home):
        runner = CliRunner()
        target_dir = fake_home / "storage"

        result = runner.invoke(cli.vocabmaster, ["config", "dir", str(target_dir)])

        assert result.exit_code == 0
        config = config_handler.read_config()
        assert config["data_dir"] == str(target_dir)
        assert target_dir.exists()

    def test_config_dir_show_only_prints_directory(self, fake_home):
        runner = CliRunner()

        result = runner.invoke(cli.vocabmaster, ["config", "dir", "--show"])

        assert result.exit_code == 0
        assert "Current storage directory:" in result.output
        assert str(fake_home / ".vocabmaster") in result.output
        assert "Enter the directory" not in result.output

    def test_config_dir_show_with_directory_errors(self, fake_home):
        runner = CliRunner()
        target_dir = fake_home / "storage"

        result = runner.invoke(
            cli.vocabmaster,
            ["config", "dir", "--show", str(target_dir)],
        )

        assert result.exit_code == 2
        assert "Cannot use '--show' together with a directory path." in result.output

    def test_print_current_storage_directory_returns_path(self, fake_home, capsys):
        custom_dir = fake_home / "custom"
        config_handler.set_data_directory(custom_dir)

        returned = cli.print_current_storage_directory()

        output = capsys.readouterr().out
        assert returned == custom_dir
        assert "Current storage directory:" in output
        assert str(custom_dir) in output


class TestPairsGroup:
    def test_pairs_group_help(self):
        result = invoke_cli(["pairs"])

        assert result.exit_code == 0
        assert "Manage language pairs" in result.output
        assert "add" in result.output
        assert "list" in result.output
        assert "set-deck-name" in result.output

    def test_pair_alias_help(self):
        result = invoke_cli(["pair"])

        assert result.exit_code == 0
        assert "Manage language pairs" in result.output

    def test_pair_alias_hidden_from_root_help(self):
        result = invoke_cli([])

        assert "pairs      Manage language pairs" in result.output
        assert "pair       Manage language pairs" not in result.output


class TestPairsListCommand:
    def test_pairs_list_handles_absent_pairs(self, isolated_app_dir):
        result = invoke_cli(["pairs", "list"])

        assert result.exit_code == 0
        assert "No language pairs found yet." in result.output

    def test_pairs_list_displays_pairs(self, isolated_app_dir):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")

        result = invoke_cli(["pairs", "list"])

        assert result.exit_code == 0
        assert "1. english:french" in result.output
        assert "2. spanish:english" in result.output


class TestPairsAddCommand:
    def test_pairs_add_creates_files_and_sets_default(self, isolated_app_dir, monkeypatch):
        prompts = iter(["English", "French"])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["pairs", "add"])

        config = config_handler.read_config()
        assert result.exit_code == 0
        assert config["default"]["language_to_learn"] == "english"
        assert config["default"]["mother_tongue"] == "french"
        assert Path(config_handler.get_config_filepath()).exists()

    def test_pairs_add_canceled_keeps_state(self, isolated_app_dir, monkeypatch):
        # Set up initial state
        config_handler.set_language_pair("french", "english")
        config_handler.set_default_language_pair("french", "english")

        prompts = iter(["German", "English"])
        confirmations = iter([False])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: next(confirmations))

        result = invoke_cli(["pairs", "add"])

        config = config_handler.read_config()
        assert result.exit_code == 0
        assert "Creation canceled" in result.output
        # Verify the original state is preserved
        assert config["default"]["language_to_learn"] == "french"
        assert config["default"]["mother_tongue"] == "english"

    def test_pairs_add_existing_default_sets_new_when_confirmed(
        self, isolated_app_dir, monkeypatch
    ):
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("spanish", "english")

        prompts = iter(["Italian", "French"])
        confirmations = iter([True, True])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: next(confirmations))

        result = invoke_cli(["pairs", "add"])

        default_pair = config_handler.get_default_language_pair()
        assert result.exit_code == 0
        assert default_pair["language_to_learn"] == "italian"
        assert default_pair["mother_tongue"] == "french"

    def test_pairs_add_existing_default_keeps_current_when_declined(
        self, isolated_app_dir, monkeypatch
    ):
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("spanish", "english")

        prompts = iter(["Italian", "French"])
        confirmations = iter([True, False])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: next(confirmations))

        result = invoke_cli(["pairs", "add"])

        default_pair = config_handler.get_default_language_pair()
        assert result.exit_code == 0
        assert "Keeping the existing default language pair." in result.output
        assert default_pair["language_to_learn"] == "spanish"
        assert default_pair["mother_tongue"] == "english"


class TestPairsDefaultCommand:
    def test_pairs_default_handles_missing_default(self, isolated_app_dir):
        result = invoke_cli(["pairs", "default"])

        assert result.exit_code == 0
        assert "No default language pair configured yet." in result.output

    def test_pairs_default_shows_current_default(self, isolated_app_dir):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        result = invoke_cli(["pairs", "default"])

        assert result.exit_code == 0
        assert "english:french" in result.output
        assert "vocabmaster pairs set-default" in result.output


class TestPairsSetDefaultCommand:
    def test_pairs_set_default_requires_pairs(self, isolated_app_dir):
        result = invoke_cli(["pairs", "set-default"])

        assert result.exit_code == 1
        assert "No language pairs found yet." in result.output

    def test_pairs_set_default_select_by_number(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "2")

        result = invoke_cli(["pairs", "set-default"])

        default_pair = config_handler.get_default_language_pair()
        assert result.exit_code == 0
        assert default_pair["language_to_learn"] == "spanish"
        assert default_pair["mother_tongue"] == "english"

    def test_pairs_set_default_number_out_of_range(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "5")

        result = invoke_cli(["pairs", "set-default"])

        assert result.exit_code == 1
        assert "Invalid choice" in result.output

    def test_pairs_set_default_invalid_pair_format(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "english-french")

        result = invoke_cli(["pairs", "set-default"])

        assert result.exit_code == 1
        assert "Invalid language pair." in result.output
        assert "language_to_learn:mother_tongue" in result.output

    def test_pairs_set_default_accepts_pair_string(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "spanish:english")

        result = invoke_cli(["pairs", "set-default"])

        default_pair = config_handler.get_default_language_pair()
        assert result.exit_code == 0
        assert default_pair["language_to_learn"] == "spanish"
        assert default_pair["mother_tongue"] == "english"

    def test_pair_alias_set_default(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "2")

        result = invoke_cli(["pair", "set-default"])

        default_pair = config_handler.get_default_language_pair()
        assert result.exit_code == 0
        assert default_pair["language_to_learn"] == "spanish"
        assert default_pair["mother_tongue"] == "english"


class TestPairsRemoveCommand:
    def test_pairs_remove_requires_pairs(self, isolated_app_dir):
        result = invoke_cli(["pairs", "remove"])

        assert result.exit_code == 1
        assert "No language pairs found yet." in result.output

    def test_pairs_remove_invalid_number(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "3")

        result = invoke_cli(["pairs", "remove"])

        assert result.exit_code == 1
        assert "Invalid choice" in result.output

    def test_pairs_remove_invalid_pair_format(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "english-french")

        result = invoke_cli(["pairs", "remove"])

        assert result.exit_code == 1
        assert "Invalid language pair." in result.output

    def test_pairs_remove_pair_not_found(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "spanish:english")

        result = invoke_cli(["pairs", "remove"])

        assert result.exit_code == 1
        assert "was not found" in result.output

    def test_pairs_remove_decline_confirmation(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "1")
        monkeypatch.setattr("click.confirm", lambda *_, **__: False)

        result = invoke_cli(["pairs", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert "No changes made." in result.output
        assert len(pairs) == 2

    def test_pairs_remove_by_number(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "2")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["pairs", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert "has been removed" in result.output
        assert "spanish:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }

    def test_pairs_remove_by_pair_string(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "Spanish:English")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["pairs", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert "has been removed" in result.output
        assert "spanish:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }

    def test_pairs_remove_no_selection(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "   ")

        result = invoke_cli(["pairs", "remove"])

        assert result.exit_code == 1
        assert "No language pairs selected for removal." in result.output

    def test_pairs_remove_multiple_numbers(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_language_pair("german", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "2, 3")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["pairs", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert "spanish:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }
        assert "german:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }
        assert result.output.count("has been removed") == 2

    def test_pairs_remove_multiple_pairs(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_language_pair("german", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "spanish:english, GERMAN:english")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["pairs", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert "spanish:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }
        assert "german:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }
        assert result.output.count("has been removed") == 2

    def test_pairs_remove_removes_default(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "1")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["pairs", "remove"])

        default_pair = config_handler.get_default_language_pair()
        assert result.exit_code == 0
        assert "default language pair was removed" in result.output
        assert "Run 'vocabmaster pairs set-default' to choose a new default." in result.output
        assert default_pair is None

    def test_pairs_remove_last_pair(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "1")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["pairs", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert pairs == []
        assert "There are no language pairs configured now." in result.output
        assert "Use 'vocabmaster pairs add' to add a new language pair." in result.output


class TestPairsRenameCommand:
    def test_pairs_rename_success(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        translations, anki = utils.setup_files(isolated_app_dir, "english", "french")
        translations.write_text(
            'word,translation,example\nbonjour,hello,"example"', encoding="utf-8"
        )
        anki.write_text("#header\nrow", encoding="utf-8")

        prompts = iter(["1", "british:french"])
        confirmations = iter([True])

        backup_calls = []
        original_backup_file = utils.backup_file

        def tracking_backup(backup_dir, filepath):
            backup_calls.append(filepath.name)
            return original_backup_file(backup_dir, filepath)

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: next(confirmations))
        monkeypatch.setattr(cli.utils, "backup_file", tracking_backup)

        result = invoke_cli(["pairs", "rename"])

        storage_files = sorted(p.name for p in isolated_app_dir.glob("*"))
        assert result.exit_code == 0
        assert "english:french has been renamed to british:french" in result.output
        assert "vocab_list_british-french.csv" in storage_files
        assert "anki_deck_british-french.csv" in storage_files
        assert "vocab_list_english-french.csv" not in storage_files
        assert "anki_deck_english-french.csv" not in storage_files

        default_pair = config_handler.get_default_language_pair()
        assert default_pair["language_to_learn"] == "british"
        assert default_pair["mother_tongue"] == "french"
        assert {"vocab_list_english-french.csv", "anki_deck_english-french.csv"} <= set(
            backup_calls
        )

    def test_pairs_rename_decline_confirmation(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")

        prompts = iter(["english:french", "british:french"])
        confirmations = iter([False])

        translations, anki = utils.setup_files(isolated_app_dir, "english", "french")
        translations.write_text("", encoding="utf-8")
        anki.write_text("", encoding="utf-8")

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: next(confirmations))

        result = invoke_cli(["pairs", "rename"])

        assert result.exit_code == 0
        assert "No changes made." in result.output
        assert (isolated_app_dir / "vocab_list_english-french.csv").exists()
        assert (isolated_app_dir / "anki_deck_english-french.csv").exists()

    def test_pairs_rename_invalid_new_format(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")

        prompts = iter(["english:french", "british-french"])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["pairs", "rename"])

        assert result.exit_code == 1
        assert "Invalid language pair." in result.output

    def test_pairs_rename_pair_not_found(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")

        prompts = iter(["spanish:english"])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["pairs", "rename"])

        assert result.exit_code == 1
        assert "was not found" in result.output

    def test_pairs_rename_target_exists(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")

        prompts = iter(["english:french", "spanish:english"])
        confirmations = iter([True])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: next(confirmations))

        result = invoke_cli(["pairs", "rename"])

        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_pairs_rename_same_name(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")

        prompts = iter(["english:french", "english:french"])
        confirmations = iter([True])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: next(confirmations))

        result = invoke_cli(["pairs", "rename"])

        assert result.exit_code == 1
        assert "New language pair must be different" in result.output

    def test_pairs_rename_confirmation_default_is_false(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")

        prompts = iter(["english:french", "british:french"])

        confirmation_defaults = {}

        def capture_confirm(prompt, default=False):
            confirmation_defaults["value"] = default
            return False

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", capture_confirm)

        result = invoke_cli(["pairs", "rename"])

        assert result.exit_code == 0
        assert "No changes made." in result.output
        assert confirmation_defaults["value"] is False


class TestPairsInspectCommand:
    def test_pairs_inspect_requires_existing_pair(self, isolated_app_dir):
        result = invoke_cli(["pairs", "inspect", "--pair", "english:french"])

        assert result.exit_code == 1
        assert "The language pair english:french was not found." in result.output

    def test_pairs_inspect_displays_metrics(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        translations, anki = utils.setup_files(isolated_app_dir, "english", "french")
        translations.write_text(
            'word,translation,example\nbonjour,hello,"example"\nchien,,\n',
            encoding="utf-8",
        )
        anki.write_text("#header\nrow", encoding="utf-8")

        monkeypatch.setattr(
            cli.gpt_integration,
            "format_prompt",
            lambda *args: [{"role": "system", "content": "prompt"}],
        )
        monkeypatch.setattr(cli.gpt_integration, "num_tokens_from_messages", lambda *_, **__: 100)
        monkeypatch.setattr(
            cli.gpt_integration,
            "estimate_prompt_cost",
            lambda *args, **kwargs: "0.123",
        )

        result = invoke_cli(["pairs", "inspect", "--pair", "english:french"])

        assert result.exit_code == 0
        assert "english:french" in result.output
        assert "Default: Yes" in result.output
        assert f"Vocabulary file: {translations}" in result.output
        assert f"Anki deck: {anki}" in result.output
        assert "Total words: 2" in result.output
        assert "Translated: 1" in result.output
        assert "Pending: 1" in result.output
        assert "Number of tokens in the prompt:" in result.output
        assert "Cost estimate for gpt-4.1 model:" in result.output
        assert "$0.123" in result.output

    def test_pairs_inspect_uses_default_when_no_argument(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        translations, anki = utils.setup_files(isolated_app_dir, "english", "french")
        translations.write_text("word,translation,example\nbonjour,,\n", encoding="utf-8")
        anki.write_text("#header\nrow", encoding="utf-8")

        monkeypatch.setattr(
            cli.gpt_integration,
            "format_prompt",
            lambda *args: [{"role": "system", "content": "prompt"}],
        )
        monkeypatch.setattr(cli.gpt_integration, "num_tokens_from_messages", lambda *_, **__: 100)
        monkeypatch.setattr(
            cli.gpt_integration,
            "estimate_prompt_cost",
            lambda *args, **kwargs: "0.456",
        )

        result = invoke_cli(["pairs", "inspect"])

        assert result.exit_code == 0
        assert "Language pair: english:french" in result.output
        assert "Default: Yes" in result.output
        assert "Cost estimate for gpt-4.1 model:" in result.output
        assert "$0.456" in result.output

    def test_pairs_inspect_non_default_pair(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("spanish", "english")

        translations, anki = utils.setup_files(isolated_app_dir, "english", "french")
        translations.write_text("word,translation,example\nhola,,\n", encoding="utf-8")
        anki.write_text("#header\nrow", encoding="utf-8")

        monkeypatch.setattr(
            cli.gpt_integration,
            "format_prompt",
            lambda *args: [{"role": "system", "content": "prompt"}],
        )
        monkeypatch.setattr(cli.gpt_integration, "num_tokens_from_messages", lambda *_, **__: 100)
        monkeypatch.setattr(
            cli.gpt_integration,
            "estimate_prompt_cost",
            lambda *args, **kwargs: "0.111",
        )

        result = invoke_cli(["pairs", "inspect", "--pair", "english:french"])

        assert result.exit_code == 0
        assert "Default: No" in result.output
        assert "Pending: 1" in result.output
        assert "Cost estimate for gpt-4.1 model:" in result.output
        assert "$0.111" in result.output

    def test_pairs_inspect_handles_missing_files(self, isolated_app_dir):
        config_handler.set_language_pair("english", "french")

        result = invoke_cli(["pairs", "inspect", "--pair", "english:french"])

        assert result.exit_code == 0
        assert "Vocabulary file:" in result.output
        assert "Anki deck:" in result.output
        assert "Total words: 0" in result.output
        assert "Translated: 0" in result.output
        assert "Number of tokens in the prompt: N/A (vocabulary file not found)" in result.output


class TestPairsSetDeckNameCommand:
    def test_set_deck_name_requires_pairs(self, isolated_app_dir):
        """Test command fails when no language pairs exist."""
        result = invoke_cli(["pairs", "set-deck-name"])

        assert result.exit_code == 1
        assert "No language pairs found" in result.output

    def test_set_deck_name_with_pair_and_name_options(self, isolated_app_dir):
        """Test setting deck name using --pair and --name options."""
        config_handler.set_language_pair("english", "french")

        result = invoke_cli(
            ["pairs", "set-deck-name", "--pair", "english:french", "--name", "My Custom Deck"]
        )

        assert result.exit_code == 0
        assert "Custom deck name set" in result.output
        assert "My Custom Deck" in result.output
        assert config_handler.get_deck_name("english", "french") == "My Custom Deck"

    def test_set_deck_name_interactively(self, isolated_app_dir, monkeypatch):
        """Test setting deck name through interactive prompts."""
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")

        prompts = iter(["1", "Business English"])
        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))

        result = invoke_cli(["pairs", "set-deck-name"])

        assert result.exit_code == 0
        assert "Business English" in result.output
        assert config_handler.get_deck_name("english", "french") == "Business English"

    def test_set_deck_name_shows_current_custom_name(self, isolated_app_dir, monkeypatch):
        """Test command shows existing custom deck name."""
        config_handler.set_language_pair("english", "french")
        config_handler.set_deck_name("english", "french", "Existing Name")

        prompts = iter(["english:french", "New Name"])
        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))

        result = invoke_cli(["pairs", "set-deck-name"])

        assert result.exit_code == 0
        assert "Current custom deck name: Existing Name" in result.output
        assert config_handler.get_deck_name("english", "french") == "New Name"

    def test_set_deck_name_shows_auto_generated_name(self, isolated_app_dir, monkeypatch):
        """Test command shows auto-generated name when no custom name set."""
        config_handler.set_language_pair("english", "french")

        prompts = iter(["1", "My Deck"])
        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))

        result = invoke_cli(["pairs", "set-deck-name"])

        assert result.exit_code == 0
        assert "Currently using auto-generated name:" in result.output
        assert "English vocabulary" in result.output

    def test_set_deck_name_cancel_with_blank_input(self, isolated_app_dir, monkeypatch):
        """Test canceling deck name change with blank input."""
        config_handler.set_language_pair("english", "french")

        prompts = iter(["1", ""])
        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))

        result = invoke_cli(["pairs", "set-deck-name"])

        assert result.exit_code == 0
        assert "No changes made" in result.output
        assert config_handler.get_deck_name("english", "french") is None

    def test_set_deck_name_invalid_characters(self, isolated_app_dir):
        """Test validation rejects invalid characters."""
        config_handler.set_language_pair("english", "french")

        result = invoke_cli(
            ["pairs", "set-deck-name", "--pair", "english:french", "--name", "Invalid:Name"]
        )

        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "single colons" in result.output

    def test_set_deck_name_path_traversal(self, isolated_app_dir):
        """Test validation blocks path traversal attempts."""
        config_handler.set_language_pair("english", "french")

        result = invoke_cli(
            ["pairs", "set-deck-name", "--pair", "english:french", "--name", "../malicious"]
        )

        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "path traversal" in result.output

    def test_set_deck_name_invalid_pair(self, isolated_app_dir):
        """Test error when specified pair doesn't exist."""
        config_handler.set_language_pair("english", "french")

        result = invoke_cli(
            ["pairs", "set-deck-name", "--pair", "spanish:english", "--name", "My Deck"]
        )

        assert result.exit_code == 1
        assert "Error:" in result.output

    def test_set_deck_name_interactive_invalid_choice(self, isolated_app_dir, monkeypatch):
        """Test error handling for invalid interactive selection."""
        config_handler.set_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "5")

        result = invoke_cli(["pairs", "set-deck-name"])

        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "Invalid choice" in result.output

    def test_set_deck_name_remove_flag(self, isolated_app_dir, monkeypatch):
        """Test removing custom deck name with --remove flag."""
        config_handler.set_language_pair("english", "french")
        config_handler.set_deck_name("english", "french", "Custom Deck")

        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["pairs", "set-deck-name", "--pair", "english:french", "--remove"])

        assert result.exit_code == 0
        assert "Custom deck name removed" in result.output
        assert config_handler.get_deck_name("english", "french") is None

    def test_set_deck_name_remove_when_none_set(self, isolated_app_dir):
        """Test removing when no custom deck name is set."""
        config_handler.set_language_pair("english", "french")

        result = invoke_cli(["pairs", "set-deck-name", "--pair", "english:french", "--remove"])

        assert result.exit_code == 0
        assert "No custom deck name set" in result.output
        assert "Nothing to remove" in result.output

    def test_set_deck_name_remove_decline_confirmation(self, isolated_app_dir, monkeypatch):
        """Test declining removal confirmation."""
        config_handler.set_language_pair("english", "french")
        config_handler.set_deck_name("english", "french", "Custom Deck")

        monkeypatch.setattr("click.confirm", lambda *_, **__: False)

        result = invoke_cli(["pairs", "set-deck-name", "--pair", "english:french", "--remove"])

        assert result.exit_code == 0
        assert "No changes made" in result.output
        assert config_handler.get_deck_name("english", "french") == "Custom Deck"

    def test_set_deck_name_updates_existing(self, isolated_app_dir):
        """Test updating an existing custom deck name."""
        config_handler.set_language_pair("english", "french")
        config_handler.set_deck_name("english", "french", "Old Name")

        result = invoke_cli(
            ["pairs", "set-deck-name", "--pair", "english:french", "--name", "New Name"]
        )

        assert result.exit_code == 0
        assert "New Name" in result.output
        assert config_handler.get_deck_name("english", "french") == "New Name"

    def test_set_deck_name_remove_nonexistent_pair_fails(self, isolated_app_dir):
        """Test that --remove with non-existent pair raises error."""
        config_handler.set_language_pair("english", "french")

        result = invoke_cli(["pairs", "set-deck-name", "--pair", "nonexistent:pair", "--remove"])

        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "not found" in result.output

    def test_set_deck_name_handles_invalid_stored_name_on_remove(
        self, isolated_app_dir, monkeypatch
    ):
        """Allow removing an invalid stored deck name instead of crashing."""
        config_handler.set_language_pair("english", "french")
        config = config_handler.read_config()
        config["language_pairs"][0]["deck_name"] = "Bad:Name"
        config_handler.write_config(config)
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["pairs", "set-deck-name", "--pair", "english:french", "--remove"])

        assert result.exit_code == 0
        assert "invalid" in result.output.lower()
        assert "Custom deck name removed" in result.output
        assert config_handler.get_deck_name("english", "french") is None

    def test_set_deck_name_replaces_invalid_stored_name(self, isolated_app_dir):
        """Allow setting a new name when config contains an invalid deck name."""
        config_handler.set_language_pair("english", "french")
        config = config_handler.read_config()
        config["language_pairs"][0]["deck_name"] = "Bad\nName"
        config_handler.write_config(config)

        result = invoke_cli(
            ["pairs", "set-deck-name", "--pair", "english:french", "--name", "Valid Name"]
        )

        assert result.exit_code == 0
        assert "Stored deck name is invalid" in result.output
        assert config_handler.get_deck_name("english", "french") == "Valid Name"


class TestAnkiCommandWithDeckName:
    def test_anki_with_deck_name_option(self, isolated_app_dir, monkeypatch):
        """Test anki command with --deck-name option."""
        config_handler.set_language_pair("english", "french")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))

        result = invoke_cli(["anki", "--pair", "english:french", "--deck-name", "Test Deck"])

        assert result.exit_code == 0
        content = anki_path.read_text()
        assert "#deck:Test Deck" in content
        assert "#deck:English vocabulary" not in content

    def test_anki_uses_config_deck_name(self, isolated_app_dir, monkeypatch):
        """Test anki command uses deck name from config when no --deck-name provided."""
        config_handler.set_language_pair("english", "french")
        config_handler.set_deck_name("english", "french", "Config Deck")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))

        result = invoke_cli(["anki", "--pair", "english:french"])

        assert result.exit_code == 0
        content = anki_path.read_text()
        assert "#deck:Config Deck" in content

    def test_anki_deck_name_option_overrides_config(self, isolated_app_dir, monkeypatch):
        """Test --deck-name option overrides config setting."""
        config_handler.set_language_pair("english", "french")
        config_handler.set_deck_name("english", "french", "Config Deck")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))

        result = invoke_cli(["anki", "--pair", "english:french", "--deck-name", "CLI Override"])

        assert result.exit_code == 0
        content = anki_path.read_text()
        assert "#deck:CLI Override" in content
        assert "#deck:Config Deck" not in content

    def test_anki_auto_generates_when_no_custom_name(self, isolated_app_dir, monkeypatch):
        """Test anki command auto-generates deck name when no custom name set."""
        config_handler.set_language_pair("english", "french")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))

        result = invoke_cli(["anki", "--pair", "english:french"])

        assert result.exit_code == 0
        content = anki_path.read_text()
        assert "#deck:English vocabulary" in content

    def test_anki_invalid_config_deck_name_exits(self, isolated_app_dir, monkeypatch):
        """Test anki exits when config deck name is invalid."""
        config_handler.set_language_pair("english", "french")
        config = config_handler.read_config()
        config["language_pairs"][0]["deck_name"] = "Bad:Name"
        config_handler.write_config(config)

        def fail_setup(*_args, **_kwargs):
            raise AssertionError("setup_files should not be called when deck name is invalid")

        monkeypatch.setattr(utils, "setup_files", fail_setup)

        result = invoke_cli(["anki", "--pair", "english:french"])

        assert result.exit_code == 1
        assert "Invalid deck name for english:french" in result.output


class TestTranslateCommandWithDeckName:
    def test_translate_with_deck_name_option(self, isolated_app_dir, monkeypatch):
        """Test translate command with --deck-name option."""
        config_handler.set_language_pair("english", "french")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)
        monkeypatch.setattr(
            "vocabmaster.csv_handler.add_translations_and_examples_to_file", lambda *_: None
        )

        result = invoke_cli(
            ["translate", "--pair", "english:french", "--deck-name", "Custom Translate Deck"]
        )

        assert result.exit_code == 0
        content = anki_path.read_text()
        assert "#deck:Custom Translate Deck" in content

    def test_translate_invalid_config_deck_name_exits(self, isolated_app_dir, monkeypatch):
        """Test translate exits early when config deck name is invalid."""
        config_handler.set_language_pair("english", "french")
        config = config_handler.read_config()
        config["language_pairs"][0]["deck_name"] = "Bad:Name"
        config_handler.write_config(config)

        def fail_setup(*_args, **_kwargs):
            raise AssertionError("setup_files should not be called when deck name is invalid")

        monkeypatch.setattr(utils, "setup_files", fail_setup)

        result = invoke_cli(["translate", "--pair", "english:french"])

        assert result.exit_code == 1
        assert "Invalid deck name for english:french" in result.output

    def test_translate_uses_config_deck_name(self, isolated_app_dir, monkeypatch):
        """Test translate command uses deck name from config."""
        config_handler.set_language_pair("english", "french")
        config_handler.set_deck_name("english", "french", "Translation Deck")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)
        monkeypatch.setattr(
            "vocabmaster.csv_handler.add_translations_and_examples_to_file", lambda *_: None
        )

        result = invoke_cli(["translate", "--pair", "english:french"])

        assert result.exit_code == 0
        content = anki_path.read_text()
        assert "#deck:Translation Deck" in content

    def test_translate_deck_name_option_overrides_config(self, isolated_app_dir, monkeypatch):
        """Test --deck-name option overrides config in translate command."""
        config_handler.set_language_pair("english", "french")
        config_handler.set_deck_name("english", "french", "Config Name")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)
        monkeypatch.setattr(
            "vocabmaster.csv_handler.add_translations_and_examples_to_file", lambda *_: None
        )

        result = invoke_cli(
            ["translate", "--pair", "english:french", "--deck-name", "Override Name"]
        )

        assert result.exit_code == 0
        content = anki_path.read_text()
        assert "#deck:Override Name" in content
        assert "#deck:Config Name" not in content

    def test_translate_deck_name_rejects_newline(self, isolated_app_dir, monkeypatch):
        """Test --deck-name rejects names with newline characters in translate command."""
        config_handler.set_language_pair("english", "french")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)
        monkeypatch.setattr(
            "vocabmaster.csv_handler.add_translations_and_examples_to_file", lambda *_: None
        )

        result = invoke_cli(["translate", "--pair", "english:french", "--deck-name", "Bad\nName"])

        assert result.exit_code == 1
        assert "Deck name contains invalid characters" in result.output
        assert "'\\n'" in result.output

    def test_translate_deck_name_rejects_colon(self, isolated_app_dir, monkeypatch):
        """Test --deck-name rejects names with colon characters in translate command."""
        config_handler.set_language_pair("english", "french")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)
        monkeypatch.setattr(
            "vocabmaster.csv_handler.add_translations_and_examples_to_file", lambda *_: None
        )

        result = invoke_cli(["translate", "--pair", "english:french", "--deck-name", "Bad:Name"])

        assert result.exit_code == 1
        assert "single colons" in result.output

    def test_translate_deck_name_rejects_tab(self, isolated_app_dir, monkeypatch):
        """Test --deck-name rejects names with tab characters in translate command."""
        config_handler.set_language_pair("english", "french")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)
        monkeypatch.setattr(
            "vocabmaster.csv_handler.add_translations_and_examples_to_file", lambda *_: None
        )

        result = invoke_cli(["translate", "--pair", "english:french", "--deck-name", "Bad\tName"])

        assert result.exit_code == 1
        assert "Deck name contains invalid characters" in result.output
        assert "'\\t'" in result.output

    def test_translate_deck_name_rejects_path_traversal(self, isolated_app_dir, monkeypatch):
        """Test --deck-name rejects path traversal patterns in translate command."""
        config_handler.set_language_pair("english", "french")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))
        monkeypatch.setattr(cli, "openai_api_key_exists", lambda: True)
        monkeypatch.setattr(
            "vocabmaster.csv_handler.add_translations_and_examples_to_file", lambda *_: None
        )

        result = invoke_cli(["translate", "--pair", "english:french", "--deck-name", "../evil"])

        assert result.exit_code == 1
        assert "path traversal pattern" in result.output

    def test_anki_deck_name_rejects_newline(self, isolated_app_dir, monkeypatch):
        """Test --deck-name rejects names with newline characters in anki command."""
        config_handler.set_language_pair("english", "french")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))

        result = invoke_cli(["anki", "--pair", "english:french", "--deck-name", "Bad\nName"])

        assert result.exit_code == 1
        assert "Deck name contains invalid characters" in result.output
        assert "'\\n'" in result.output

    def test_anki_deck_name_rejects_colon(self, isolated_app_dir, monkeypatch):
        """Test --deck-name rejects names with colon characters in anki command."""
        config_handler.set_language_pair("english", "french")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))

        result = invoke_cli(["anki", "--pair", "english:french", "--deck-name", "Bad:Name"])

        assert result.exit_code == 1
        assert "single colons" in result.output

    def test_anki_deck_name_rejects_tab(self, isolated_app_dir, monkeypatch):
        """Test --deck-name rejects names with tab characters in anki command."""
        config_handler.set_language_pair("english", "french")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))

        result = invoke_cli(["anki", "--pair", "english:french", "--deck-name", "Bad\tName"])

        assert result.exit_code == 1
        assert "Deck name contains invalid characters" in result.output
        assert "'\\t'" in result.output

    def test_anki_deck_name_rejects_path_traversal(self, isolated_app_dir, monkeypatch):
        """Test --deck-name rejects path traversal patterns in anki command."""
        config_handler.set_language_pair("english", "french")
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )

        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))

        result = invoke_cli(["anki", "--pair", "english:french", "--deck-name", "../evil"])

        assert result.exit_code == 1
        assert "path traversal pattern" in result.output


class TestCustomDeckNameEndToEndWorkflow:
    def test_full_workflow_set_name_then_generate_deck(self, isolated_app_dir, monkeypatch):
        """End-to-end test: set custom deck name, then generate deck using it."""
        # Step 1: Create language pair
        config_handler.set_language_pair("english", "french")

        # Step 2: Set custom deck name via CLI
        result_set = invoke_cli(
            ["pairs", "set-deck-name", "--pair", "english:french", "--name", "My Learning Deck"]
        )
        assert result_set.exit_code == 0
        assert "Custom deck name set" in result_set.output

        # Step 3: Verify config was updated
        assert config_handler.get_deck_name("english", "french") == "My Learning Deck"

        # Step 4: Generate Anki deck (should use custom name from config)
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text(
            "word,translation,example\nbonjour,hello,Hello world", encoding="utf-8"
        )
        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))

        result_anki = invoke_cli(["anki", "--pair", "english:french"])
        assert result_anki.exit_code == 0

        # Step 5: Verify deck uses custom name
        content = anki_path.read_text()
        assert "#deck:My Learning Deck" in content
        assert "#deck:English vocabulary" not in content

    def test_workflow_remove_custom_name_reverts_to_auto(self, isolated_app_dir, monkeypatch):
        """Test removing custom name reverts to auto-generation."""
        # Set up language pair with custom name
        config_handler.set_language_pair("english", "french")
        config_handler.set_deck_name("english", "french", "Custom Name")

        # Remove custom name
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)
        result_remove = invoke_cli(
            ["pairs", "set-deck-name", "--pair", "english:french", "--remove"]
        )
        assert result_remove.exit_code == 0
        assert config_handler.get_deck_name("english", "french") is None

        # Generate deck should use auto-generated name
        vocab_path, anki_path = utils.setup_files(isolated_app_dir, "english", "french")
        vocab_path.write_text("word,translation,example\ntest,test,test", encoding="utf-8")
        monkeypatch.setattr(utils, "setup_files", lambda *_: (vocab_path, anki_path))

        result_anki = invoke_cli(["anki", "--pair", "english:french"])
        assert result_anki.exit_code == 0

        content = anki_path.read_text()
        assert "#deck:English vocabulary" in content
