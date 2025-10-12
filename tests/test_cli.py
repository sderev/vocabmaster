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


class TestRootCommand:
    def test_help_displayed_when_no_subcommand(self):
        result = invoke_cli([])

        assert result.exit_code == 0
        assert "Usage" in result.output

    def test_config_group_help(self):
        result = invoke_cli(["config"])

        assert result.exit_code == 0
        assert "Manage VocabMaster configuration" in result.output
        assert "config dir" in result.output


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
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )

        result = invoke_cli(["add"])

        assert result.exit_code == 0
        assert "Please provide a word to add." in result.output

    def test_add_notifies_when_word_exists(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler, "get_language_pair", lambda pair: ("english", "french")
        )
        monkeypatch.setattr(cli.csv_handler, "word_exists", lambda word, path: True)
        monkeypatch.setattr(cli.csv_handler, "append_word", lambda word, path: None)
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )

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
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )

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
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )
        monkeypatch.setattr(cli.csv_handler, "ensure_csv_has_fieldnames", lambda path: None)
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: True)

        result = invoke_cli(["translate"])

        assert result.exit_code == 0
        assert "Your vocabulary list is empty" in result.output

    def test_translate_count_option_success(self, isolated_app_dir, monkeypatch):
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
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )
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
            raise Exception(
                "All the words in the vocabulary list already have translations and examples"
            )

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

        monkeypatch.setattr(cli, "setup_files", fake_setup_files)
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

        def record_generate(translations, anki, language, mother):
            captured["args"] = (translations, anki, language, mother)

        monkeypatch.setattr(cli.csv_handler, "generate_anki_output_file", record_generate)

        translations = Path("/tmp/trans.csv")
        anki = Path("/tmp/anki.csv")

        cli.generate_anki_deck(translations, anki, "english", "french")

        out = capsys.readouterr().out
        assert "Generating the Anki deck" in out
        assert captured["args"] == (translations, anki, "english", "french")


class TestAnkiCommand:
    def test_anki_requires_default_pair(self, isolated_app_dir):
        result = invoke_cli(["anki"])

        assert result.exit_code == 1
        assert "No default language pair found" in result.output

    def test_anki_generates_deck_when_default_set(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler,
            "get_default_language_pair",
            lambda: {"language_to_learn": "english", "mother_tongue": "french"},
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


class TestSetupCommand:
    def test_setup_creates_files_and_sets_default(self, isolated_app_dir, monkeypatch):
        prompts = iter(["English", "French"])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["setup"])

        config = config_handler.read_config()
        assert result.exit_code == 0
        assert config["default"]["language_to_learn"] == "english"
        assert config["default"]["mother_tongue"] == "french"
        assert Path(config_handler.get_config_filepath()).exists()

    def test_setup_canceled_keeps_state(self, isolated_app_dir, monkeypatch):
        prompts = iter(["German", "English"])

        confirmations = iter([False])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: next(confirmations))

        result = invoke_cli(["setup"])

        config = config_handler.read_config()
        assert result.exit_code == 0
        assert "Setup canceled" in result.output
        assert config["default"]["language_to_learn"] == "German"
        assert config["default"]["mother_tongue"] == "English"

    def test_setup_existing_default_sets_new_when_confirmed(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("spanish", "english")

        prompts = iter(["Italian", "French"])
        confirmations = iter([True, True])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: next(confirmations))

        result = invoke_cli(["setup"])

        default_pair = config_handler.get_default_language_pair()
        assert result.exit_code == 0
        assert default_pair["language_to_learn"] == "italian"
        assert default_pair["mother_tongue"] == "french"

    def test_setup_existing_default_keeps_current_when_declined(
        self, isolated_app_dir, monkeypatch
    ):
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("spanish", "english")

        prompts = iter(["Italian", "French"])
        confirmations = iter([True, False])

        monkeypatch.setattr("click.prompt", lambda *_, **__: next(prompts))
        monkeypatch.setattr("click.confirm", lambda *_, **__: next(confirmations))

        result = invoke_cli(["setup"])

        default_pair = config_handler.get_default_language_pair()
        assert result.exit_code == 0
        assert "Keeping the existing default language pair." in result.output
        assert default_pair["language_to_learn"] == "spanish"
        assert default_pair["mother_tongue"] == "english"


class TestDefaultCommand:
    def test_default_command_handles_missing_default(self, isolated_app_dir):
        result = invoke_cli(["default"])

        assert result.exit_code == 0
        assert "No default language pair configured yet." in result.output

    def test_default_command_shows_current_default(self, isolated_app_dir):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        result = invoke_cli(["default"])

        assert result.exit_code == 0
        assert "english:french" in result.output
        assert "vocabmaster config default" in result.output


class TestConfigDefaultCommand:
    def test_config_default_requires_pairs(self, isolated_app_dir):
        result = invoke_cli(["config", "default"])

        assert result.exit_code == 1
        assert "No language pairs found yet." in result.output

    def test_config_default_select_by_number(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "2")

        result = invoke_cli(["config", "default"])

        default_pair = config_handler.get_default_language_pair()
        assert result.exit_code == 0
        assert default_pair["language_to_learn"] == "spanish"
        assert default_pair["mother_tongue"] == "english"

    def test_config_default_number_out_of_range(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "5")

        result = invoke_cli(["config", "default"])

        assert result.exit_code == 1
        assert "Invalid choice" in result.output

    def test_config_default_invalid_pair_format(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "english-french")

        result = invoke_cli(["config", "default"])

        assert result.exit_code == 1
        assert "Invalid language pair." in result.output
        assert "language_to_learn:mother_tongue" in result.output

    def test_config_default_accepts_pair_string(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "spanish:english")

        result = invoke_cli(["config", "default"])

        default_pair = config_handler.get_default_language_pair()
        assert result.exit_code == 0
        assert default_pair["language_to_learn"] == "spanish"
        assert default_pair["mother_tongue"] == "english"


class TestConfigRemoveCommand:
    def test_config_remove_requires_pairs(self, isolated_app_dir):
        result = invoke_cli(["config", "remove"])

        assert result.exit_code == 1
        assert "No language pairs found yet." in result.output

    def test_config_remove_invalid_number(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "3")

        result = invoke_cli(["config", "remove"])

        assert result.exit_code == 1
        assert "Invalid choice" in result.output

    def test_config_remove_invalid_pair_format(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "english-french")

        result = invoke_cli(["config", "remove"])

        assert result.exit_code == 1
        assert "Invalid language pair." in result.output

    def test_config_remove_pair_not_found(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "spanish:english")

        result = invoke_cli(["config", "remove"])

        assert result.exit_code == 1
        assert "was not found" in result.output

    def test_config_remove_decline_confirmation(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "1")
        monkeypatch.setattr("click.confirm", lambda *_, **__: False)

        result = invoke_cli(["config", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert "No changes made." in result.output
        assert len(pairs) == 2

    def test_config_remove_by_number(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "2")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["config", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert "has been removed" in result.output
        assert "spanish:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }

    def test_config_remove_by_pair_string(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "Spanish:English")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["config", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert "has been removed" in result.output
        assert "spanish:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }

    def test_config_remove_no_selection(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "   ")

        result = invoke_cli(["config", "remove"])

        assert result.exit_code == 1
        assert "No language pairs selected for removal." in result.output

    def test_config_remove_multiple_numbers(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_language_pair("german", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "2, 3")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["config", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert "spanish:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }
        assert "german:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }
        assert result.output.count("has been removed") == 2

    def test_config_remove_multiple_pairs(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_language_pair("german", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "spanish:english, GERMAN:english")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["config", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert "spanish:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }
        assert "german:english" not in {
            f"{pair['language_to_learn']}:{pair['mother_tongue']}" for pair in pairs
        }
        assert result.output.count("has been removed") == 2

    def test_config_remove_removes_default(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "1")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["config", "remove"])

        default_pair = config_handler.get_default_language_pair()
        assert result.exit_code == 0
        assert "default language pair was removed" in result.output
        assert "Run 'vocabmaster config default' to choose a new default." in result.output
        assert default_pair is None

    def test_config_remove_last_pair(self, isolated_app_dir, monkeypatch):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        monkeypatch.setattr("click.prompt", lambda *_, **__: "1")
        monkeypatch.setattr("click.confirm", lambda *_, **__: True)

        result = invoke_cli(["config", "remove"])

        pairs = config_handler.get_all_language_pairs()
        assert result.exit_code == 0
        assert pairs == []
        assert "There are no language pairs configured now." in result.output
        assert "Use 'vocabmaster setup' to add a new language pair." in result.output


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


class TestShowCommand:
    def test_show_handles_absent_pairs(self, isolated_app_dir):
        result = invoke_cli(["show"])

        assert result.exit_code == 0
        assert "No language pairs found yet." in result.output

    def test_show_lists_pairs(self, isolated_app_dir):
        config_handler.set_language_pair("english", "french")
        config_handler.set_language_pair("spanish", "english")

        result = invoke_cli(["show"])

        assert result.exit_code == 0
        assert "1. english:french" in result.output
        assert "2. spanish:english" in result.output


class TestTokensCommand:
    def test_tokens_requires_default_pair(self, isolated_app_dir):
        result = invoke_cli(["tokens"])

        assert result.exit_code == 1
        assert "No default language pair found" in result.output

    def test_tokens_requires_words(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler,
            "get_default_language_pair",
            lambda: {"language_to_learn": "english", "mother_tongue": "french"},
        )
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: True)

        result = invoke_cli(["tokens"])

        assert result.exit_code == 0
        assert "The list is empty!" in result.output

    def test_tokens_handles_get_words_error(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler,
            "get_default_language_pair",
            lambda: {"language_to_learn": "english", "mother_tongue": "french"},
        )
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)

        def fail_words(_path):
            raise RuntimeError("Cannot parse")

        monkeypatch.setattr(cli.csv_handler, "get_words_to_translate", fail_words)

        result = invoke_cli(["tokens"])

        assert result.exit_code == 0
        assert "Status:" in result.output
        assert "Cannot parse" in result.output
        assert "Therefore, the cost of the next prompt cannot be estimated." in result.output

    def test_tokens_outputs_estimated_cost(self, isolated_app_dir, monkeypatch):
        monkeypatch.setattr(
            cli.config_handler,
            "get_default_language_pair",
            lambda: {"language_to_learn": "english", "mother_tongue": "french"},
        )
        monkeypatch.setattr(
            cli,
            "setup_files",
            lambda directory, *_: (directory / "vocab.csv", directory / "anki.csv"),
        )
        monkeypatch.setattr(cli.csv_handler, "vocabulary_list_is_empty", lambda path: False)
        monkeypatch.setattr(cli.csv_handler, "get_words_to_translate", lambda path: ["word"])
        monkeypatch.setattr(cli.gpt_integration, "format_prompt", lambda *_: "prompt")
        monkeypatch.setattr(
            cli.gpt_integration, "estimate_prompt_cost", lambda *_: {"gpt-3.5-turbo": "0.004"}
        )

        result = invoke_cli(["tokens"])

        assert result.exit_code == 0
        assert "$0.004" in result.output


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

        output = capsys.readouterr().out
        assert returned is None
        assert "No default language pair configured yet." in output

    def test_print_default_language_pair_existing(self, isolated_app_dir, capsys):
        config_handler.set_language_pair("english", "french")
        config_handler.set_default_language_pair("english", "french")

        returned = cli.print_default_language_pair()

        output = capsys.readouterr().out
        assert returned == {"language_to_learn": "english", "mother_tongue": "french"}
        assert "english:french" in output

    def test_print_all_language_pairs_empty(self, isolated_app_dir, capsys):
        returned = cli.print_all_language_pairs()

        output = capsys.readouterr().out
        assert returned == []
        assert "No language pairs found yet." in output

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

        output = capsys.readouterr().out
        assert "set it up by running `setx OPENAI_API_KEY your_key`" in output

    def test_openai_api_key_explain_unix(self, monkeypatch, capsys):
        monkeypatch.setattr(cli.platform, "system", lambda: "Linux")

        cli.openai_api_key_explain()

        output = capsys.readouterr().out
        assert "export OPENAI_API_KEY=YOUR_KEY" in output

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
