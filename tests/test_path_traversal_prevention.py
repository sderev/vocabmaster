"""Test path traversal vulnerability prevention."""

import os
from pathlib import Path, PureWindowsPath

import pytest
from click.testing import CliRunner

from vocabmaster import config_handler, utils
from vocabmaster.cli import vocabmaster


def test_path_traversal_write_outside_data_dir(tmp_path, fake_home, monkeypatch):
    """
    Test that path traversal vulnerability exists and can write outside data dir.
    This test should FAIL initially, proving the vulnerability exists.
    After the fix, this test should PASS.
    """
    from vocabmaster import config_handler
    from vocabmaster.cli import vocabmaster
    from click.testing import CliRunner

    # Use a benign data directory
    safe = tmp_path / "safe"
    safe.mkdir()

    # Isolate config file to tmp_path
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(config_handler, "get_config_filepath", lambda: config_file)

    config_handler.set_data_directory(safe)

    runner = CliRunner()
    # This will create/write outside `safe` via traversal
    result = runner.invoke(vocabmaster, ["translate", "--pair", "../../../tmp/vm_pwn_t:en"])

    # After fix: command should fail with validation error
    assert result.exit_code == 1  # command fails due to validation
    assert "can only contain" in result.output

    p = Path("/tmp/vm_pwn_t-en.csv")
    # File should NOT exist (vulnerability prevented)
    assert not p.exists(), "Path traversal vulnerability not fixed - file created outside data directory!"


def test_validate_language_name_blocks_path_traversal():
    """Test that validate_language_name blocks various path traversal attempts."""
    # This function doesn't exist yet - will be added in the fix
    from vocabmaster.utils import validate_language_name

    # Test path traversal sequences
    with pytest.raises(ValueError, match="can only contain"):
        validate_language_name("../../../etc/passwd")

    with pytest.raises(ValueError, match="can only contain"):
        validate_language_name("..\\..\\windows\\system32")

    # Test absolute paths
    with pytest.raises(ValueError, match="can only contain"):
        validate_language_name("/etc/passwd")

    with pytest.raises(ValueError, match="can only contain"):
        validate_language_name("\\windows\\system32")

    # Test Windows drive letters
    with pytest.raises(ValueError, match="can only contain"):
        validate_language_name("C:\\test")

    with pytest.raises(ValueError, match="can only contain"):
        validate_language_name("D:/data")

    # Test path separators
    with pytest.raises(ValueError, match="can only contain"):
        validate_language_name("some/path/here")

    with pytest.raises(ValueError, match="can only contain"):
        validate_language_name("some\\path\\here")

    # Test special characters
    with pytest.raises(ValueError, match="can only contain"):
        validate_language_name("lang!@#$")

    with pytest.raises(ValueError, match="can only contain"):
        validate_language_name("lang with spaces")

    # Test valid names (should not raise)
    assert validate_language_name("english") == "english"
    assert validate_language_name("FRENCH") == "french"
    assert validate_language_name("en_US") == "en_us"
    assert validate_language_name("pt-BR") == "pt-br"
    assert validate_language_name("lang123") == "lang123"


def test_setup_files_validates_language_names(tmp_path):
    """Test that setup_files validates language names to prevent path traversal."""
    from vocabmaster.utils import setup_files

    # Test path traversal in language_to_learn
    with pytest.raises(ValueError, match="can only contain"):
        setup_files(tmp_path, "../../../tmp/evil", "english")

    # Test path traversal in mother_tongue
    with pytest.raises(ValueError, match="can only contain"):
        setup_files(tmp_path, "english", "../../../tmp/evil")

    # Test absolute path
    with pytest.raises(ValueError, match="can only contain"):
        setup_files(tmp_path, "/etc/passwd", "english")

    # Valid names should work
    vocab_path, anki_path = setup_files(tmp_path, "english", "french")
    assert vocab_path.parent == tmp_path
    assert anki_path.parent == tmp_path


def test_get_pair_file_paths_validates_language_names(tmp_path, monkeypatch):
    """Test that get_pair_file_paths validates language names."""
    from vocabmaster.utils import get_pair_file_paths

    monkeypatch.setattr(config_handler, "get_data_directory", lambda: tmp_path)

    # Test path traversal
    with pytest.raises(ValueError, match="can only contain"):
        get_pair_file_paths("../../../tmp/evil", "english")

    with pytest.raises(ValueError, match="can only contain"):
        get_pair_file_paths("english", "../../etc/passwd")

    # Valid names should work
    vocab_path, anki_path = get_pair_file_paths("english", "french")
    assert vocab_path.parent == tmp_path
    assert anki_path.parent == tmp_path


def test_cli_pairs_add_validates_input(monkeypatch):
    """Test that CLI pairs add command validates user input."""
    from vocabmaster.cli import vocabmaster
    from click.testing import CliRunner

    runner = CliRunner()

    # Simulate user entering malicious input
    malicious_inputs = [
        "../../../tmp/evil",  # language to learn
        "english",  # mother tongue
        "y",  # confirm
    ]

    result = runner.invoke(
        vocabmaster,
        ["pairs", "add"],
        input="\n".join(malicious_inputs)
    )

    # Should fail with validation error
    assert result.exit_code != 0
    assert "can only contain" in result.output


def test_config_handler_set_language_pair_validates(tmp_path, monkeypatch):
    """Test that config_handler validates language pairs before storing."""
    from vocabmaster import config_handler

    # Mock config file location
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(config_handler, "get_config_filepath", lambda: config_file)

    # Test path traversal
    with pytest.raises(ValueError, match="can only contain"):
        config_handler.set_language_pair("../../../etc", "english")

    with pytest.raises(ValueError, match="can only contain"):
        config_handler.set_language_pair("english", "/etc/passwd")

    # Valid names should work
    config_handler.set_language_pair("english", "french")
    config = config_handler.read_config()
    assert config["language_pairs"][0]["language_to_learn"] == "english"
    assert config["language_pairs"][0]["mother_tongue"] == "french"


def test_comprehensive_path_traversal_vectors():
    """Test comprehensive set of path traversal attack vectors."""
    from vocabmaster.utils import validate_language_name

    attack_vectors = [
        "../",
        "../../",
        "../../../etc/passwd",
        "..\\..\\",
        "..\\..\\windows\\system32",
        "/etc/passwd",
        "\\windows\\system32\\config",
        "C:\\",
        "C:\\Windows",
        "D:/",
        "//etc/passwd",
        "\\\\server\\share",
        "file:///etc/passwd",
        "....//",
        "..;/",
        "%2e%2e%2f",  # URL encoded ../
        "lang/../../../etc",
        "lang/../../",
        "./../",
        "./../../",
        "~/../",
        "~/../../",
    ]

    for vector in attack_vectors:
        with pytest.raises(ValueError, match="can only contain"):
            validate_language_name(vector)


def test_validate_language_name_length_limit():
    """Test that language names have a reasonable length limit."""
    from vocabmaster.utils import validate_language_name

    # Test overly long name (more than 64 characters)
    long_name = "a" * 65
    with pytest.raises(ValueError, match="too long"):
        validate_language_name(long_name)

    # 64 characters should be OK
    valid_long_name = "a" * 64
    assert validate_language_name(valid_long_name) == valid_long_name.lower()


def test_validate_language_name_normalizes_case():
    """Test that validate_language_name normalizes case consistently."""
    from vocabmaster.utils import validate_language_name

    assert validate_language_name("ENGLISH") == "english"
    assert validate_language_name("French") == "french"
    assert validate_language_name("PT_BR") == "pt_br"
    assert validate_language_name("en-US") == "en-us"