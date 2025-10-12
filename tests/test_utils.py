from vocabmaster import config_handler, utils



def test_setup_dir_defaults_to_lowercase(fake_home):
    data_dir = utils.setup_dir()

    expected = fake_home / config_handler.DEFAULT_DATA_DIR_NAME
    assert data_dir == expected
    assert data_dir.exists()

def test_setup_dir_uses_configured_path(fake_home):
    custom_dir = fake_home / "custom" / "data"
    config_handler.set_data_directory(custom_dir)

    resolved = utils.setup_dir()

    assert resolved == custom_dir
    assert resolved.exists()
