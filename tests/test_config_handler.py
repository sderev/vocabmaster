import json

import pytest

from vocabmaster import config_handler


def test_get_config_filepath_uses_home_config(fake_home):
    config_path = config_handler.get_config_filepath()

    expected_path = fake_home / ".config" / config_handler.APP_NAME / config_handler.CONFIG_FILENAME
    assert config_path == expected_path
    assert config_path.parent.exists()


def test_get_data_directory_defaults_to_home(fake_home):
    data_dir = config_handler.get_data_directory()

    expected = fake_home / config_handler.DEFAULT_DATA_DIR_NAME
    assert data_dir == expected
    assert not data_dir.exists()


def test_legacy_config_migrated(fake_home):
    legacy_path = (
        fake_home / ".local" / "share" / config_handler.APP_NAME / config_handler.CONFIG_FILENAME
    )
    legacy_path.parent.mkdir(parents=True, exist_ok=True)

    legacy_payload = {"default": {"language_to_learn": "japanese", "mother_tongue": "english"}}
    legacy_path.write_text(json.dumps(legacy_payload))

    new_config_path = (
        fake_home / ".config" / config_handler.APP_NAME / config_handler.CONFIG_FILENAME
    )
    if new_config_path.exists():
        new_config_path.unlink()

    config = config_handler.read_config()

    assert config == legacy_payload
    assert new_config_path.exists()
    assert json.loads(new_config_path.read_text()) == legacy_payload


def test_set_and_get_data_directory(fake_home):
    custom_dir = fake_home / "Documents" / "MyVocab"
    config_handler.set_data_directory(custom_dir)

    stored_config = config_handler.read_config()
    assert stored_config["data_dir"] == str(custom_dir)

    resolved_dir = config_handler.get_data_directory()
    assert resolved_dir == custom_dir

    default_dir = config_handler.get_default_data_directory()
    assert default_dir == fake_home / config_handler.DEFAULT_DATA_DIR_NAME


def test_rename_language_pair_updates_entries(fake_home):
    config_handler.set_language_pair("english", "french")
    config_handler.set_language_pair("spanish", "english")
    config_handler.set_default_language_pair("english", "french")

    was_default = config_handler.rename_language_pair(
        "english",
        "french",
        "british",
        "french",
    )

    pairs = config_handler.get_all_language_pairs()
    assert was_default is True
    assert {"language_to_learn": "british", "mother_tongue": "french"} in pairs
    assert {"language_to_learn": "english", "mother_tongue": "french"} not in pairs
    default_pair = config_handler.get_default_language_pair()
    assert default_pair["language_to_learn"] == "british"
    assert default_pair["mother_tongue"] == "french"


def test_rename_language_pair_requires_existing_pair(fake_home):
    config_handler.set_language_pair("english", "french")

    with pytest.raises(ValueError, match="Language pair not found."):
        config_handler.rename_language_pair("spanish", "english", "german", "english")


def test_rename_language_pair_blocks_duplicates(fake_home):
    config_handler.set_language_pair("english", "french")
    config_handler.set_language_pair("spanish", "english")

    with pytest.raises(ValueError, match="already exists"):
        config_handler.rename_language_pair("english", "french", "spanish", "english")


# Tests for deck name management


def test_get_deck_name_returns_none_when_not_set(fake_home):
    """Test get_deck_name returns None when no custom deck name is configured."""
    config_handler.set_language_pair("english", "french")

    deck_name = config_handler.get_deck_name("english", "french")
    assert deck_name is None


def test_get_deck_name_returns_none_when_no_pairs_exist(fake_home):
    """Test get_deck_name returns None when no language pairs are configured."""
    deck_name = config_handler.get_deck_name("english", "french")
    assert deck_name is None


def test_get_deck_name_returns_none_when_pair_not_found(fake_home):
    """Test get_deck_name returns None when the language pair doesn't exist."""
    config_handler.set_language_pair("english", "french")

    deck_name = config_handler.get_deck_name("spanish", "english")
    assert deck_name is None


def test_set_deck_name_stores_custom_name(fake_home):
    """Test set_deck_name successfully stores a custom deck name."""
    config_handler.set_language_pair("english", "french")

    config_handler.set_deck_name("english", "french", "My Custom Deck")

    deck_name = config_handler.get_deck_name("english", "french")
    assert deck_name == "My Custom Deck"


def test_set_deck_name_persisted_in_config(fake_home):
    """Test set_deck_name persists to the config file."""
    config_handler.set_language_pair("english", "french")
    config_handler.set_deck_name("english", "french", "Business English")

    # Read config directly to verify persistence
    config = config_handler.read_config()
    pairs = config.get("language_pairs", [])
    en_fr_pair = next(
        (
            p
            for p in pairs
            if p["language_to_learn"] == "english" and p["mother_tongue"] == "french"
        ),
        None,
    )

    assert en_fr_pair is not None
    assert en_fr_pair["deck_name"] == "Business English"


def test_set_deck_name_updates_existing_name(fake_home):
    """Test set_deck_name can update an already-set custom deck name."""
    config_handler.set_language_pair("english", "french")
    config_handler.set_deck_name("english", "french", "First Name")
    config_handler.set_deck_name("english", "french", "Second Name")

    deck_name = config_handler.get_deck_name("english", "french")
    assert deck_name == "Second Name"


def test_set_deck_name_validates_deck_name(fake_home):
    """Test set_deck_name rejects invalid deck names."""
    config_handler.set_language_pair("english", "french")

    # Invalid: contains single colon
    with pytest.raises(ValueError, match="single colons"):
        config_handler.set_deck_name("english", "french", "My:Deck")

    # Invalid: path traversal
    with pytest.raises(ValueError, match="path traversal"):
        config_handler.set_deck_name("english", "french", "../malicious")


def test_set_deck_name_requires_existing_pair(fake_home):
    """Test set_deck_name raises error when language pair doesn't exist."""
    # First add a different pair, so we test "pair not found" not "no pairs configured"
    config_handler.set_language_pair("spanish", "english")

    with pytest.raises(ValueError, match="Language pair .* not found"):
        config_handler.set_deck_name("english", "french", "My Deck")


def test_set_deck_name_requires_configured_pairs(fake_home):
    """Test set_deck_name raises error when no language pairs are configured."""
    with pytest.raises(ValueError, match="No language pairs configured"):
        config_handler.set_deck_name("english", "french", "My Deck")


def test_get_deck_name_validates_stored_value(fake_home):
    """Test get_deck_name validates deck names loaded from config."""
    config_handler.set_language_pair("english", "french")
    config = config_handler.read_config()
    config["language_pairs"][0]["deck_name"] = "Bad:Name"
    config_handler.write_config(config)

    with pytest.raises(ValueError, match="Invalid deck name for english:french"):
        config_handler.get_deck_name("english", "french")


def test_set_deck_name_multiple_pairs_independent(fake_home):
    """Test each language pair can have its own custom deck name."""
    config_handler.set_language_pair("english", "french")
    config_handler.set_language_pair("spanish", "english")

    config_handler.set_deck_name("english", "french", "French Vocabulary")
    config_handler.set_deck_name("spanish", "english", "Spanish Basics")

    assert config_handler.get_deck_name("english", "french") == "French Vocabulary"
    assert config_handler.get_deck_name("spanish", "english") == "Spanish Basics"


def test_remove_deck_name_clears_custom_name(fake_home):
    """Test remove_deck_name successfully removes a custom deck name."""
    config_handler.set_language_pair("english", "french")
    config_handler.set_deck_name("english", "french", "My Deck")

    config_handler.remove_deck_name("english", "french")

    deck_name = config_handler.get_deck_name("english", "french")
    assert deck_name is None


def test_remove_deck_name_when_not_set(fake_home):
    """Test remove_deck_name is safe when no custom name was set."""
    config_handler.set_language_pair("english", "french")

    config_handler.remove_deck_name("english", "french")

    deck_name = config_handler.get_deck_name("english", "french")
    assert deck_name is None


def test_remove_deck_name_requires_existing_pair(fake_home):
    """Test remove_deck_name raises error when language pair doesn't exist."""
    # First add a different pair, so we test "pair not found" not "no pairs configured"
    config_handler.set_language_pair("spanish", "english")

    with pytest.raises(ValueError, match="Language pair .* not found"):
        config_handler.remove_deck_name("english", "french")


def test_remove_deck_name_requires_configured_pairs(fake_home):
    """Test remove_deck_name raises error when no language pairs are configured."""
    with pytest.raises(ValueError, match="No language pairs configured"):
        config_handler.remove_deck_name("english", "french")


def test_deck_name_case_insensitive_matching(fake_home):
    """Test deck name functions use case-insensitive language matching."""
    config_handler.set_language_pair("english", "french")
    config_handler.set_deck_name("english", "french", "My Deck")

    # Should find with different case
    assert config_handler.get_deck_name("English", "French") == "My Deck"
    assert config_handler.get_deck_name("ENGLISH", "FRENCH") == "My Deck"

    # Should update with different case
    config_handler.set_deck_name("ENGLISH", "FRENCH", "Updated Deck")
    assert config_handler.get_deck_name("english", "french") == "Updated Deck"

    # Should remove with different case
    config_handler.remove_deck_name("English", "French")
    assert config_handler.get_deck_name("english", "french") is None
