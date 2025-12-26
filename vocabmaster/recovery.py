"""
Recovery functions for VocabMaster backup restoration.

This module provides utilities to restore vocabulary files from backups,
validate backup integrity, and migrate between format versions.
"""

import csv
import shutil
from datetime import datetime
from pathlib import Path

from vocabmaster import utils


def _is_valid_headerless_backup(backup_path):
    """
    Check if a file is a valid headerless legacy backup.

    Legacy backups were tab-separated files without headers, containing
    3 columns (word, translation, example) or 4 columns (original_word,
    recognized_word, translation, example).

    Args:
        backup_path (pathlib.Path): Path to the backup file.

    Returns:
        bool: True if the file is a valid headerless backup.
    """
    try:
        content = backup_path.read_text(encoding="utf-8")
        lines = [line for line in content.strip().split("\n") if line.strip()]

        if not lines:
            return False

        for line in lines:
            parts = line.split("\t")
            if len(parts) not in (3, 4):
                return False

        return True
    except OSError:
        return False


def _migrate_headerless_to_csv(backup_path, output_path):
    """
    Migrate a headerless TSV backup to proper CSV format with headers.

    Args:
        backup_path (pathlib.Path): Path to the headerless backup.
        output_path (pathlib.Path): Path to write the migrated CSV.

    Returns:
        bool: True if migration succeeded.
    """
    try:
        content = backup_path.read_text(encoding="utf-8")
        lines = [line for line in content.strip().split("\n") if line.strip()]

        with open(output_path, "w", encoding="utf-8", newline="") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=["word", "translation", "example"])
            writer.writeheader()

            for line in lines:
                parts = line.split("\t")
                if len(parts) == 3:
                    # 3-col: word, translation, example
                    row = {
                        "word": parts[0],
                        "translation": parts[1],
                        "example": parts[2],
                    }
                elif len(parts) == 4:
                    # 4-col: original_word, recognized_word, translation, example
                    # Use recognized_word as the canonical word
                    row = {
                        "word": parts[1],
                        "translation": parts[2],
                        "example": parts[3],
                    }
                else:
                    return False
                writer.writerow(row)

        return True
    except (OSError, csv.Error):
        return False


def restore_vocabulary_from_backup(backup_path, language_to_learn, mother_tongue):
    """
    Restore a vocabulary file from a backup.

    Creates a backup of the current file before restoring, then copies the
    backup content to the active vocabulary file location.

    Args:
        backup_path (pathlib.Path | str): Path to the backup file to restore.
        language_to_learn (str): Target language.
        mother_tongue (str): User's mother tongue.

    Returns:
        dict: Result with keys:
            - success (bool): True if restoration succeeded
            - restored_path (pathlib.Path): Path to the restored file
            - pre_restore_backup (pathlib.Path | None): Path to pre-restore backup
            - error (str | None): Error message if failed
    """
    backup_path = Path(backup_path)

    # Validate language names
    language_to_learn = utils.validate_language_name(language_to_learn)
    mother_tongue = utils.validate_language_name(mother_tongue)

    # Check backup exists
    if not backup_path.exists():
        return {
            "success": False,
            "restored_path": None,
            "pre_restore_backup": None,
            "error": "Backup file does not exist",
        }

    # Validate the backup is parseable
    validation = utils.validate_backup_parseable(backup_path)
    needs_header_migration = False
    if not validation["valid"]:
        # Check if it's a headerless legacy backup (3 or 4 tab-separated columns)
        # Headerless files fail with "No header row found" or "Missing required columns"
        # because CSV parser uses first data row as header
        if _is_valid_headerless_backup(backup_path):
            needs_header_migration = True
        else:
            return {
                "success": False,
                "restored_path": None,
                "pre_restore_backup": None,
                "error": f"Backup validation failed: {validation['error']}",
            }

    # Get target path
    translations_path, _ = utils.get_pair_file_paths(language_to_learn, mother_tongue)

    # Create pre-restore backup of current file if it exists
    pre_restore_backup = None
    if translations_path.exists():
        backup_dir = utils.get_backup_dir(language_to_learn, mother_tongue)
        timestamp = utils.generate_iso_timestamp()
        pre_restore_backup = backup_dir / f"pre_restore_{timestamp}.bak"
        try:
            shutil.copy(translations_path, pre_restore_backup)
        except OSError as e:
            return {
                "success": False,
                "restored_path": None,
                "pre_restore_backup": None,
                "error": f"Failed to create pre-restore backup: {e}",
            }

    # Restore from backup
    try:
        if needs_header_migration:
            # Migrate headerless backup to proper CSV format
            if not _migrate_headerless_to_csv(backup_path, translations_path):
                return {
                    "success": False,
                    "restored_path": None,
                    "pre_restore_backup": pre_restore_backup,
                    "error": "Failed to migrate headerless backup",
                }
        else:
            shutil.copy(backup_path, translations_path)
    except OSError as e:
        return {
            "success": False,
            "restored_path": None,
            "pre_restore_backup": pre_restore_backup,
            "error": f"Failed to restore from backup: {e}",
        }

    return {
        "success": True,
        "restored_path": translations_path,
        "pre_restore_backup": pre_restore_backup,
        "error": None,
    }


def validate_all_backups(language_to_learn, mother_tongue):
    """
    Validate all backup files for a language pair.

    Args:
        language_to_learn (str): Target language.
        mother_tongue (str): User's mother tongue.

    Returns:
        dict: Validation summary with keys:
            - total (int): Total number of backups
            - valid (int): Number of valid backups
            - invalid (int): Number of invalid backups
            - results (list): Per-backup validation results
    """
    backups = utils.list_backups(language_to_learn, mother_tongue)

    results = []
    valid_count = 0
    invalid_count = 0

    for backup in backups:
        backup_path = backup["path"]

        # Only validate vocabulary backups (not GPT responses)
        if backup["type"] == "vocabulary":
            validation = utils.validate_backup_parseable(backup_path)
            format_info = utils.get_backup_format_version(backup_path)

            result = {
                "path": backup_path,
                "filename": backup["filename"],
                "type": backup["type"],
                "valid": validation["valid"],
                "rows": validation["rows"],
                "format_version": format_info["version"],
                "error": validation["error"],
            }

            if validation["valid"]:
                valid_count += 1
            else:
                invalid_count += 1

            results.append(result)
        elif backup["type"] == "gpt-response":
            # GPT response backups are not validated the same way
            format_info = utils.get_backup_format_version(backup_path)
            # Mark "unknown" format as invalid since we can't verify integrity
            is_valid = format_info["error"] is None and format_info["version"] != "unknown"
            results.append(
                {
                    "path": backup_path,
                    "filename": backup["filename"],
                    "type": backup["type"],
                    "valid": is_valid,
                    "rows": None,
                    "format_version": format_info["version"],
                    "error": format_info["error"]
                    if format_info["error"]
                    else ("Unknown format" if not is_valid else None),
                }
            )
            if is_valid:
                valid_count += 1
            else:
                invalid_count += 1
        elif backup["type"] == "anki-deck":
            results.append(
                {
                    "path": backup_path,
                    "filename": backup["filename"],
                    "type": backup["type"],
                    "valid": True,
                    "rows": None,
                    "format_version": "anki-deck",
                    "error": None,
                }
            )
            valid_count += 1
        else:
            results.append(
                {
                    "path": backup_path,
                    "filename": backup["filename"],
                    "type": backup["type"],
                    "valid": False,
                    "rows": None,
                    "format_version": "unknown",
                    "error": "Unsupported backup type",
                }
            )
            invalid_count += 1

    return {
        "total": len(backups),
        "valid": valid_count,
        "invalid": invalid_count,
        "results": results,
    }


def get_latest_backup(language_to_learn, mother_tongue, backup_type="vocabulary"):
    """
    Get the most recent backup for a language pair.

    Args:
        language_to_learn (str): Target language.
        mother_tongue (str): User's mother tongue.
        backup_type (str): Type of backup ("vocabulary", "gpt-response", "anki-deck")

    Returns:
        dict | None: Backup info dict, or None if no backups exist.
    """
    backups = utils.list_backups(language_to_learn, mother_tongue)

    # Filter by type and sort by modification time (most recent first)
    typed_backups = [b for b in backups if b["type"] == backup_type]

    if not typed_backups:
        return None

    # Already sorted by mtime ascending, so last is most recent
    return typed_backups[-1]


def format_backup_timestamp(timestamp_str):
    """
    Format a backup timestamp string for human-readable display.

    Args:
        timestamp_str (str): ISO timestamp with underscores replacing colons.

    Returns:
        str: Human-readable date/time string.
    """
    try:
        # Convert back to ISO format
        iso_str = timestamp_str.replace("_", ":")
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return timestamp_str


# --- Format Migration Functions ---


def migrate_gpt_response_backup(backup_path, output_path=None):
    """
    Migrate a GPT response backup from 3-column to 4-column format.

    The old format: word\\ttranslation\\texample
    The new format: original_word\\trecognized_word\\ttranslation\\texample

    For migration, recognized_word is set equal to original_word (no correction).

    Args:
        backup_path (pathlib.Path | str): Path to the backup file to migrate.
        output_path (pathlib.Path | str | None): Output path. If None, creates
            a new file with '_migrated' suffix.

    Returns:
        dict: Migration result with keys:
            - success (bool): True if migration succeeded
            - output_path (pathlib.Path): Path to migrated file
            - original_format (str): Detected original format
            - rows_migrated (int): Number of rows migrated
            - error (str | None): Error message if failed
    """
    backup_path = Path(backup_path)

    if not backup_path.exists():
        return {
            "success": False,
            "output_path": None,
            "original_format": "unknown",
            "rows_migrated": 0,
            "error": "Backup file does not exist",
        }

    # Detect format
    format_info = utils.get_backup_format_version(backup_path)

    if format_info["error"]:
        return {
            "success": False,
            "output_path": None,
            "original_format": format_info["version"],
            "rows_migrated": 0,
            "error": format_info["error"],
        }

    if format_info["version"] == "4-col":
        return {
            "success": True,
            "output_path": backup_path,
            "original_format": "4-col",
            "rows_migrated": 0,
            "error": None,
        }

    if format_info["version"] != "3-col":
        return {
            "success": False,
            "output_path": None,
            "original_format": format_info["version"],
            "rows_migrated": 0,
            "error": f"Cannot migrate format: {format_info['version']}",
        }

    # Create output path
    if output_path is None:
        output_path = backup_path.with_suffix(".migrated.bak")
    else:
        output_path = Path(output_path)

    try:
        content = backup_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")

        migrated_lines = []
        rows_migrated = 0
        skipped_rows = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) == 3:
                # 3-col format: word, translation, example
                word, translation, example = parts
                # Convert to 4-col: original_word, recognized_word, translation, example
                migrated_line = f"{word}\t{word}\t{translation}\t{example}"
                migrated_lines.append(migrated_line)
                rows_migrated += 1
            elif len(parts) == 4:
                # Already 4-col, keep as-is
                migrated_lines.append(line)
            else:
                # Unexpected column count - skip and track
                skipped_rows += 1

        if skipped_rows > 0:
            return {
                "success": False,
                "output_path": None,
                "original_format": format_info["version"],
                "rows_migrated": 0,
                "error": f"Skipped {skipped_rows} rows with unexpected column counts",
            }

        output_path.write_text("\n".join(migrated_lines) + "\n", encoding="utf-8")

        return {
            "success": True,
            "output_path": output_path,
            "original_format": "3-col",
            "rows_migrated": rows_migrated,
            "error": None,
        }

    except OSError as e:
        return {
            "success": False,
            "output_path": None,
            "original_format": "3-col",
            "rows_migrated": 0,
            "error": f"File operation failed: {e}",
        }


def migrate_vocabulary_backup(backup_path, output_path=None):
    """
    Migrate a vocabulary CSV backup, ensuring proper format.

    Vocabulary files already use the standard CSV format with headers.
    This function validates and optionally repairs the format.

    Args:
        backup_path (pathlib.Path | str): Path to the backup file.
        output_path (pathlib.Path | str | None): Output path. If None, creates
            a new file with '_migrated' suffix.

    Returns:
        dict: Migration result with keys:
            - success (bool): True if migration succeeded
            - output_path (pathlib.Path): Path to migrated file
            - original_format (str): Detected original format
            - rows_migrated (int): Number of rows in output
            - error (str | None): Error message if failed
    """
    backup_path = Path(backup_path)

    if not backup_path.exists():
        return {
            "success": False,
            "output_path": None,
            "original_format": "unknown",
            "rows_migrated": 0,
            "error": "Backup file does not exist",
        }

    # Validate the backup
    validation = utils.validate_backup_parseable(backup_path)

    if not validation["valid"]:
        return {
            "success": False,
            "output_path": None,
            "original_format": "unknown",
            "rows_migrated": 0,
            "error": validation["error"],
        }

    # Create output path
    if output_path is None:
        output_path = backup_path.with_suffix(".migrated.bak")
    else:
        output_path = Path(output_path)

    try:
        # Read and rewrite with proper format
        with open(backup_path, "r", encoding="utf-8") as infile:
            reader = csv.DictReader(infile)
            rows = list(reader)

        with open(output_path, "w", encoding="utf-8", newline="") as outfile:
            fieldnames = ["word", "translation", "example"]
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()

            for row in rows:
                # Ensure all required fields exist
                clean_row = {
                    "word": row.get("word", ""),
                    "translation": row.get("translation", ""),
                    "example": row.get("example", ""),
                }
                writer.writerow(clean_row)

        return {
            "success": True,
            "output_path": output_path,
            "original_format": "3-col",
            "rows_migrated": len(rows),
            "error": None,
        }

    except (OSError, csv.Error) as e:
        return {
            "success": False,
            "output_path": None,
            "original_format": "unknown",
            "rows_migrated": 0,
            "error": f"Migration failed: {e}",
        }
