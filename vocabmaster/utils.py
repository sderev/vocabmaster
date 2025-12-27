import csv
import os
import shutil
import string
from datetime import datetime
from pathlib import Path

import click
import openai

from vocabmaster import config_handler

# Allowed characters for language names (whitelist approach)
ALLOWED_CHARS = set(string.ascii_letters + string.digits + "_-")


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
        raise ValueError(
            "Language names can only contain letters, numbers, underscores, and hyphens"
        )

    return name.casefold()


def validate_deck_name(name: str) -> str:
    """
    Validate a custom Anki deck name.

    Uses a blacklist approach to prevent Anki import format breakage and path
    traversal attacks while allowing user-friendly names with spaces and unicode.

    Args:
        name: The deck name to validate

    Returns:
        The validated deck name (stripped of leading/trailing whitespace)

    Raises:
        ValueError: If the deck name is invalid
    """
    if not isinstance(name, str):
        raise ValueError("Deck name must be a string")

    # Strip whitespace early to allow tabs/newlines at edges (common copy-paste errors)
    # but still catch them if they're in the middle of the name
    name = name.strip()

    if not name:
        raise ValueError("Deck name cannot be empty")

    if len(name) > 100:
        raise ValueError("Deck name is too long (maximum 100 characters)")

    # Block absolute paths FIRST (before checking for colons in unsafe_chars)
    # Unix absolute paths start with /
    # Windows absolute paths: single letter + : + \ or / (e.g., C:\, D:/)
    # Don't trigger on :: for nested Anki deck names
    if name.startswith("/"):
        raise ValueError("Deck name cannot be an absolute path")
    if len(name) > 2 and name[0].isalpha() and name[1] == ":" and name[2] in ("\\/"):
        raise ValueError("Deck name cannot be an absolute path")

    # Prevent path traversal patterns
    dangerous_patterns = ["../", "./", "..\\", ".\\"]
    for pattern in dangerous_patterns:
        if pattern in name:
            raise ValueError(f"Deck name cannot contain path traversal pattern: {pattern}")

    # Check for unsafe characters
    # Single colons break the #deck: directive format, but :: is allowed for nested decks
    # Newlines/tabs would break the file format or cause display issues
    unsafe_chars = {"\n", "\r", "\t"}
    found_unsafe = [c for c in unsafe_chars if c in name]
    if found_unsafe:
        chars_repr = ", ".join(repr(c) for c in found_unsafe)
        raise ValueError(f"Deck name contains invalid characters: {chars_repr}")

    # Check for single colons (but allow :: for nested Anki deck names)
    # Replace :: with placeholder to detect single colons
    name_without_double_colons = name.replace("::", "\x00")
    if ":" in name_without_double_colons:
        raise ValueError("Deck name cannot contain single colons (use :: for nested decks)")

    return name


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


# --- Backup Validation Functions ---


def validate_backup_parseable(backup_path):
    """
    Check if a backup file can be parsed as valid CSV.

    Args:
        backup_path (pathlib.Path | str): Path to the backup file.

    Returns:
        dict: Validation result with keys:
            - valid (bool): True if parseable
            - rows (int): Number of data rows (excluding header) if valid
            - error (str | None): Error message if invalid
    """
    backup_path = Path(backup_path)

    if not backup_path.exists():
        return {"valid": False, "rows": 0, "error": "File does not exist"}

    try:
        with open(backup_path, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            rows = list(reader)

            # Check that we have the expected fieldnames
            if reader.fieldnames is None:
                return {"valid": False, "rows": 0, "error": "No header row found"}

            expected_fields = {"word", "translation", "example"}
            actual_fields = set(reader.fieldnames)

            if not expected_fields.issubset(actual_fields):
                missing = expected_fields - actual_fields
                return {
                    "valid": False,
                    "rows": 0,
                    "error": f"Missing required columns: {', '.join(sorted(missing))}",
                }

            return {"valid": True, "rows": len(rows), "error": None}

    except csv.Error as e:
        return {"valid": False, "rows": 0, "error": f"CSV parse error: {e}"}
    except UnicodeDecodeError as e:
        return {"valid": False, "rows": 0, "error": f"File decode error: {e}"}
    except OSError as e:
        return {"valid": False, "rows": 0, "error": f"File read error: {e}"}


def get_backup_format_version(backup_path):
    """
    Detect the format version of a backup file.

    The application historically used 3-column format (word, translation, example)
    for GPT response backups and vocabulary files. The format is determined by
    examining the content structure.

    Args:
        backup_path (pathlib.Path | str): Path to the backup file.

    Returns:
        dict: Format information with keys:
            - version (str): "3-col", "4-col", "mixed", or "unknown"
            - columns (list): Detected column names
            - error (str | None): Error message if detection failed
    """
    backup_path = Path(backup_path)

    if not backup_path.exists():
        return {"version": "unknown", "columns": [], "error": "File does not exist"}

    try:
        content = backup_path.read_text(encoding="utf-8")

        # GPT response backups are typically raw text (TSV without header)
        if backup_path.suffix == ".bak" and "gpt_request_" in backup_path.name:
            lines = [line for line in content.splitlines() if line.strip()]
            if not lines:
                return {"version": "unknown", "columns": [], "error": "Empty file"}

            column_counts = set()
            for line_number, line in enumerate(lines, start=1):
                columns = line.split("\t")
                column_count = len(columns)
                if column_count == 3:
                    column_counts.add(3)
                elif column_count == 4:
                    column_counts.add(4)
                else:
                    return {
                        "version": "unknown",
                        "columns": [],
                        "error": f"Line {line_number} has {column_count} columns",
                    }

            if column_counts == {3}:
                return {
                    "version": "3-col",
                    "columns": ["word", "translation", "example"],
                    "error": None,
                }
            if column_counts == {4}:
                return {
                    "version": "4-col",
                    "columns": ["original_word", "recognized_word", "translation", "example"],
                    "error": None,
                }
            return {
                "version": "mixed",
                "columns": [],
                "error": "Mixed column counts in GPT response backup",
            }

        # CSV vocabulary backups have a header row
        with open(backup_path, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None:
                return {"version": "unknown", "columns": [], "error": "No header row"}

            columns = list(reader.fieldnames)
            if set(columns) == {"word", "translation", "example"}:
                return {"version": "3-col", "columns": columns, "error": None}
            elif len(columns) >= 4:
                return {"version": "4-col", "columns": columns, "error": None}
            else:
                return {"version": "unknown", "columns": columns, "error": None}

    except UnicodeDecodeError as e:
        return {"version": "unknown", "columns": [], "error": f"File decode error: {e}"}
    except OSError as e:
        return {"version": "unknown", "columns": [], "error": f"File read error: {e}"}


def list_backups(language_to_learn, mother_tongue):
    """
    List all backup files for a language pair with metadata.

    Args:
        language_to_learn (str): Target language.
        mother_tongue (str): User's mother tongue.

    Returns:
        list[dict]: List of backup info dictionaries, each with keys:
            - path (pathlib.Path): Full path to backup file
            - filename (str): Backup filename
            - timestamp (str): Extracted timestamp from filename
            - type (str): "vocabulary", "gpt-response", "anki-deck", or "pre-restore"
            - size (int): File size in bytes
            - mtime (float): Modification time
    """
    # Validate language names
    language_to_learn = validate_language_name(language_to_learn)
    mother_tongue = validate_language_name(mother_tongue)

    backup_dir = get_backup_dir(language_to_learn, mother_tongue)

    if not backup_dir.exists():
        return []

    backups = []

    for backup_file in sorted(backup_dir.glob("*.bak"), key=lambda p: p.stat().st_mtime):
        filename = backup_file.name
        stat = backup_file.stat()

        # Determine backup type and extract timestamp based on known prefixes
        # Timestamps use ISO format with colons replaced by underscores: 2024-01-01T12_34_56.789012
        timestamp = ""
        backup_type = "unknown"

        if filename.startswith("gpt_request_"):
            backup_type = "gpt-response"
            # Format: gpt_request_TIMESTAMP.bak
            timestamp = filename[len("gpt_request_") : -len(".bak")]
        elif filename.startswith("vocab_list_"):
            backup_type = "vocabulary"
            # Format: vocab_list_lang-lang_TIMESTAMP.bak
            # Find the lang-lang pattern (contains hyphen), timestamp follows
            pair_pattern = f"{language_to_learn}-{mother_tongue}_"
            prefix = f"vocab_list_{pair_pattern}"
            if filename.startswith(prefix):
                timestamp = filename[len(prefix) : -len(".bak")]
        elif filename.startswith("anki_deck_"):
            backup_type = "anki-deck"
            # Format: anki_deck_lang-lang_TIMESTAMP.bak
            pair_pattern = f"{language_to_learn}-{mother_tongue}_"
            prefix = f"anki_deck_{pair_pattern}"
            if filename.startswith(prefix):
                timestamp = filename[len(prefix) : -len(".bak")]
        elif filename.startswith("pre_restore_"):
            backup_type = "pre-restore"
            # Format: pre_restore_TIMESTAMP.bak
            timestamp = filename[len("pre_restore_") : -len(".bak")]

        backups.append(
            {
                "path": backup_file,
                "filename": filename,
                "timestamp": timestamp,
                "type": backup_type,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
        )

    return backups


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
    return bool(os.environ.get("OPENAI_API_KEY") or openai.api_key)


BLUE = "\x1b[94m"
BOLD = "\x1b[1m"
GREEN = "\x1b[92m"
ORANGE = "\x1b[93m"
RED = "\x1b[91m"
RESET = "\x1b[0m"
