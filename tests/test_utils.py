import openai
import pytest

from vocabmaster import config_handler, utils


def test_setup_dir_defaults_to_lowercase(fake_home):
    data_dir = utils.setup_dir()

    expected = fake_home / config_handler.DEFAULT_DATA_DIR_NAME
    assert data_dir == expected
    assert data_dir.exists()


def test_get_backup_dir_creates_language_directory(fake_home):
    backup_dir = utils.get_backup_dir("english", "french")

    expected = fake_home / ".vocabmaster" / ".backup" / "english-french"
    assert backup_dir == expected
    assert backup_dir.exists()


def test_get_backup_dir_respects_configured_storage(fake_home, monkeypatch):
    custom_dir = fake_home / "custom-storage"
    config_handler.set_data_directory(custom_dir)

    monkeypatch.setattr(config_handler, "get_data_directory", lambda: custom_dir)

    backup_dir = utils.get_backup_dir("english", "french")

    expected = custom_dir / ".backup" / "english-french"
    assert backup_dir == expected
    assert backup_dir.exists()


def test_setup_dir_uses_configured_path(fake_home):
    custom_dir = fake_home / "custom" / "data"
    config_handler.set_data_directory(custom_dir)

    resolved = utils.setup_dir()

    assert resolved == custom_dir
    assert resolved.exists()


def test_is_same_language_pair_exact_match():
    """Test same language detection with exact matches."""
    assert utils.is_same_language_pair("french", "french") is True
    assert utils.is_same_language_pair("english", "english") is True


def test_is_same_language_pair_case_insensitive():
    """Test same language detection is case-insensitive."""
    assert utils.is_same_language_pair("French", "french") is True
    assert utils.is_same_language_pair("ENGLISH", "english") is True
    assert utils.is_same_language_pair("SpAnIsH", "spanish") is True


def test_is_same_language_pair_different_languages():
    """Test different languages are correctly identified."""
    assert utils.is_same_language_pair("french", "english") is False
    assert utils.is_same_language_pair("spanish", "italian") is False


def test_get_pair_mode_definition_mode():
    """Test mode detection returns 'definition' for same-language pairs."""
    assert utils.get_pair_mode("french", "french") == "definition"
    assert utils.get_pair_mode("French", "FRENCH") == "definition"
    assert utils.get_pair_mode("english", "English") == "definition"


def test_get_pair_mode_translation_mode():
    """Test mode detection returns 'translation' for different-language pairs."""
    assert utils.get_pair_mode("french", "english") == "translation"
    assert utils.get_pair_mode("spanish", "italian") == "translation"
    assert utils.get_pair_mode("German", "french") == "translation"


def test_openai_api_key_exists_checks_sdk_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(openai, "api_key", "sk-test")

    assert utils.openai_api_key_exists() is True


def test_openai_api_key_exists_false_without_env_or_sdk_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(openai, "api_key", None)

    assert utils.openai_api_key_exists() is False


# Tests for validate_deck_name()


def test_validate_deck_name_valid_simple_name():
    """Test validation accepts simple deck names."""
    assert utils.validate_deck_name("My Deck") == "My Deck"
    assert utils.validate_deck_name("English Vocabulary") == "English Vocabulary"
    assert utils.validate_deck_name("French") == "French"


def test_validate_deck_name_valid_with_special_chars():
    """Test validation accepts deck names with punctuation and unicode."""
    assert utils.validate_deck_name("Business English (Advanced)") == "Business English (Advanced)"
    assert utils.validate_deck_name("Level A1-A2") == "Level A1-A2"
    assert utils.validate_deck_name("Français - Vocabulaire") == "Français - Vocabulaire"
    assert utils.validate_deck_name("日本語 Basic") == "日本語 Basic"
    assert utils.validate_deck_name("Español 🇪🇸") == "Español 🇪🇸"


def test_validate_deck_name_strips_whitespace():
    """Test validation strips leading and trailing whitespace."""
    assert utils.validate_deck_name("  My Deck  ") == "My Deck"
    assert utils.validate_deck_name("\tEnglish\t") == "English"
    assert utils.validate_deck_name("  Spanish  ") == "Spanish"


def test_validate_deck_name_empty_after_strip():
    """Test validation rejects names that are empty after stripping whitespace."""
    with pytest.raises(ValueError, match="Deck name cannot be empty"):
        utils.validate_deck_name("")
    with pytest.raises(ValueError, match="Deck name cannot be empty"):
        utils.validate_deck_name("   ")
    with pytest.raises(ValueError, match="Deck name cannot be empty"):
        utils.validate_deck_name("\t\n")


def test_validate_deck_name_not_string():
    """Test validation rejects non-string inputs."""
    with pytest.raises(ValueError, match="Deck name must be a string"):
        utils.validate_deck_name(123)
    with pytest.raises(ValueError, match="Deck name must be a string"):
        utils.validate_deck_name(None)
    with pytest.raises(ValueError, match="Deck name must be a string"):
        utils.validate_deck_name(["list"])


def test_validate_deck_name_too_long():
    """Test validation rejects names exceeding 100 characters."""
    long_name = "a" * 101
    with pytest.raises(ValueError, match="Deck name is too long"):
        utils.validate_deck_name(long_name)

    # Should accept exactly 100 characters
    exactly_100 = "a" * 100
    assert utils.validate_deck_name(exactly_100) == exactly_100


def test_validate_deck_name_rejects_newline():
    """Test validation rejects deck names containing newlines in the middle."""
    with pytest.raises(ValueError, match="invalid characters"):
        utils.validate_deck_name("My\nDeck")
    with pytest.raises(ValueError, match="invalid characters"):
        utils.validate_deck_name("First\nSecond\nThird")


def test_validate_deck_name_rejects_tab():
    """Test validation rejects deck names containing tabs in the middle."""
    with pytest.raises(ValueError, match="invalid characters"):
        utils.validate_deck_name("My\tDeck")
    with pytest.raises(ValueError, match="invalid characters"):
        utils.validate_deck_name("One\tTwo\tThree")


def test_validate_deck_name_rejects_carriage_return():
    """Test validation rejects deck names containing carriage returns."""
    with pytest.raises(ValueError, match="invalid characters"):
        utils.validate_deck_name("My\rDeck")


def test_validate_deck_name_rejects_single_colon():
    """Test validation rejects deck names containing single colons (breaks Anki format)."""
    with pytest.raises(ValueError, match="single colons"):
        utils.validate_deck_name("My:Deck")
    with pytest.raises(ValueError, match="single colons"):
        utils.validate_deck_name("English: Advanced")
    with pytest.raises(ValueError, match="single colons"):
        utils.validate_deck_name("Parent::Child:Bad")  # Single colon after double
    with pytest.raises(ValueError, match="single colons"):
        utils.validate_deck_name("Bad:Parent::Child")  # Single colon before double


def test_validate_deck_name_allows_double_colon():
    """Test validation allows :: for nested Anki deck names."""
    assert utils.validate_deck_name("English::Business") == "English::Business"
    assert (
        utils.validate_deck_name("Languages::Spanish::Vocabulary")
        == "Languages::Spanish::Vocabulary"
    )
    assert utils.validate_deck_name("Parent::Child") == "Parent::Child"
    assert utils.validate_deck_name("A::B::C::D") == "A::B::C::D"


def test_validate_deck_name_rejects_path_traversal():
    """Test validation rejects path traversal patterns."""
    with pytest.raises(ValueError, match="path traversal pattern"):
        utils.validate_deck_name("../etc/passwd")
    with pytest.raises(ValueError, match="path traversal pattern"):
        utils.validate_deck_name("./malicious")
    with pytest.raises(ValueError, match="path traversal pattern"):
        utils.validate_deck_name("..\\windows")
    with pytest.raises(ValueError, match="path traversal pattern"):
        utils.validate_deck_name(".\\temp")


def test_validate_deck_name_rejects_absolute_paths():
    """Test validation rejects absolute file paths."""
    with pytest.raises(ValueError, match="absolute path"):
        utils.validate_deck_name("/etc/passwd")
    with pytest.raises(ValueError, match="absolute path"):
        utils.validate_deck_name("/home/user/deck")
    with pytest.raises(ValueError, match="absolute path"):
        utils.validate_deck_name("C:\\Windows\\System32")
    with pytest.raises(ValueError, match="absolute path"):
        utils.validate_deck_name("D:\\Data")
