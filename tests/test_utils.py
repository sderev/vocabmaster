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
