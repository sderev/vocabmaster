import os
import shutil
import string
from datetime import datetime

import click

from vocabmaster import config_handler


# Allowed characters for language names (whitelist approach)
ALLOWED_CHARS = set(string.ascii_letters + string.digits + '_-')


def validate_language_name(name: str) -> str:
    """
    Validate and normalize a language name.

    Uses a whitelist approach to prevent path traversal attacks by only
    allowing safe characters.

    Args:
        name: The language name to validate

    Returns:
        The normalized (casefolded) language name

    Raises:
        ValueError: If the language name is invalid
    """
    if not isinstance(name, str):
        raise ValueError("Language name must be a string")

    if not name:
        raise ValueError("Language name cannot be empty")

    if len(name) > 64:
        raise ValueError("Language name is too long (maximum 64 characters)")

    if not all(c in ALLOWED_CHARS for c in name):
        raise ValueError("Language names can only contain letters, numbers, underscores, and hyphens")

    return name.casefold()


def setup_dir():
    """
    Ensure the data directory exists and return its path.

    Returns:
        pathlib.Path: The application data directory.
    """
    data_dir = config_handler.get_data_directory()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        raise click.ClickException(f"Unable to create directory '{data_dir}': {err}") from err
    return data_dir


def setup_files(app_data_dir, language_to_learn, mother_tongue):
    """
    Create the vocabulary and Anki files inside the provided directory if they do not exist.

    Args:
        app_data_dir (pathlib.Path): Directory where application data files should be created.
        language_to_learn (str): Target language.
        mother_tongue (str): User's mother tongue.

    Returns:
        tuple[pathlib.Path, pathlib.Path]: Paths for the vocabulary and Anki files.
    """
    # Validate language names to prevent path traversal
    language_to_learn = validate_language_name(language_to_learn)
    mother_tongue = validate_language_name(mother_tongue)

    file_paths = (
        app_data_dir / f"vocab_list_{language_to_learn}-{mother_tongue}.csv",
        app_data_dir / f"anki_deck_{language_to_learn}-{mother_tongue}.csv",
    )
    for file in file_paths:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch(exist_ok=True)
    return file_paths


def get_pair_file_paths(language_to_learn, mother_tongue):
    """
    Return the expected vocabulary and Anki file paths for the given language pair.

    Args:
        language_to_learn (str): Target language.
        mother_tongue (str): User's mother tongue.

    Returns:
        tuple[pathlib.Path, pathlib.Path]: Paths to the vocabulary CSV and Anki deck CSV.
    """
    # Validate language names to prevent path traversal
    language_to_learn = validate_language_name(language_to_learn)
    mother_tongue = validate_language_name(mother_tongue)
    data_dir = config_handler.get_data_directory()
    return (
        data_dir / f"vocab_list_{language_to_learn}-{mother_tongue}.csv",
        data_dir / f"anki_deck_{language_to_learn}-{mother_tongue}.csv",
    )


def backup_language_pair_files(language_to_learn, mother_tongue):
    """
    Create backups for both the vocabulary and Anki files of the provided language pair.

    Missing files are ignored silently.
    """
    translations_path, anki_path = get_pair_file_paths(language_to_learn, mother_tongue)
    backup_dir = get_backup_dir(language_to_learn, mother_tongue)

    if translations_path.exists():
        backup_file(backup_dir, translations_path)
    if anki_path.exists():
        backup_file(backup_dir, anki_path)


def setup_backup_dir(language_to_learn, mother_tongue):
    """
    Ensure the backup directory for a language pair exists and return its path.

    Args:
        language_to_learn (str): Target language.
        mother_tongue (str): User's mother tongue.

    Returns:
        pathlib.Path: Backup directory for the provided language pair.
    """
    backup_dir = get_backup_dir(language_to_learn, mother_tongue)
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def get_backup_dir(language_to_learn=None, mother_tongue=None):
    """
    Return the backup directory path, optionally scoped to the provided language pair.

    Args:
        language_to_learn (str | None): Target language.
        mother_tongue (str | None): User's mother tongue.

    Returns:
        pathlib.Path: Backup directory path.
    """
    base_dir = setup_dir() / ".backup"
    base_dir.mkdir(parents=True, exist_ok=True)
    if language_to_learn and mother_tongue:
        # Validate language names to prevent path traversal
        language_to_learn = validate_language_name(language_to_learn)
        mother_tongue = validate_language_name(mother_tongue)
        backup_path = base_dir / f"{language_to_learn}-{mother_tongue}"
    else:
        backup_path = base_dir
    backup_path.mkdir(parents=True, exist_ok=True)
    return backup_path


def backup_content(backup_dir, content):
    """
    Create a timestamped backup file for the provided content in the backup_dir directory.

    A maximum of 15 backup files will be saved, after which the oldest backup file will be deleted.

    Args:
        backup_dir (pathlib.Path): Backup directory path.
        content (str): Content to write to the backup file.
    """
    iso_timestamp = generate_iso_timestamp()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file = backup_dir / f"gpt_request_{iso_timestamp}.bak"
    with backup_file.open("w", encoding="UTF-8") as file:
        file.write(str(content))

    backup_files = sorted(
        list(backup_dir.glob("gpt_request_*.bak")),
        key=lambda p: p.stat().st_mtime,
    )
    if len(backup_files) > 15:
        oldest_backup_file = backup_files[0]
        oldest_backup_file.unlink(missing_ok=True)


def backup_file(backup_dir, filepath):
    """
    Create a timestamped backup file for the provided filepath in the backup_dir directory.

    A maximum of 10 backup files will be saved, after which the oldest backup file will be deleted.

    Args:
        backup_dir (pathlib.Path): Backup directory path.
        filepath (pathlib.Path): File to back up.
    """
    iso_timestamp = generate_iso_timestamp()

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_voc_list = backup_dir / f"{filepath.stem}_{iso_timestamp}.bak"
    shutil.copy(filepath, backup_voc_list)

    backup_files = sorted(
        list(backup_dir.glob(f"{filepath.stem}_*.bak")),
        key=lambda p: p.stat().st_mtime,
    )
    if len(backup_files) > 10:
        oldest_backup_file = backup_files[0]
        oldest_backup_file.unlink()


def generate_iso_timestamp():
    """
    Generate an ISO 8601 formatted timestamp with colons replaced by underscores.
    """
    now = datetime.now()
    return now.isoformat().replace(":", "_")


def get_language_pair_from_option(pair):
    """
    Get the language pair based on the input option string or the default language pair.

    Args:
        pair (str): Language pair in the format "language_to_learn:mother_tongue".

    Returns:
        tuple[str, str]: Language to learn and mother tongue.
    """
    if pair:
        language_to_learn, mother_tongue = pair.split(":")
    else:
        default_pair = config_handler.get_default_language_pair()
        language_to_learn = default_pair["language_to_learn"]
        mother_tongue = default_pair["mother_tongue"]

    return language_to_learn, mother_tongue


def is_same_language_pair(language_to_learn, mother_tongue):
    """
    Determine whether a language pair represents the same language.

    Args:
        language_to_learn (str): Target language.
        mother_tongue (str): User's mother tongue.

    Returns:
        bool: True if both languages are the same (case-insensitive), False otherwise.
    """
    return language_to_learn.casefold() == mother_tongue.casefold()


def get_pair_mode(language_to_learn, mother_tongue):
    """
    Determine the mode for a language pair.

    Args:
        language_to_learn (str): Target language.
        mother_tongue (str): User's mother tongue.

    Returns:
        str: "definition" if the languages match, "translation" otherwise.
    """
    return (
        "definition" if is_same_language_pair(language_to_learn, mother_tongue) else "translation"
    )


def openai_api_key_exists():
    """
    Check if an OpenAI API key is set on the system.
    """
    return bool(os.environ.get("OPENAI_API_KEY"))


BLUE = "\x1b[94m"
BOLD = "\x1b[1m"
GREEN = "\x1b[92m"
ORANGE = "\x1b[93m"
RED = "\x1b[91m"
RESET = "\x1b[0m"
