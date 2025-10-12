import json

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
