"""
Recovery functions for VocabMaster backup restoration.

This module provides utilities to restore vocabulary files from backups,
validate backup integrity, and migrate between format versions.
"""

import shutil
from datetime import datetime
from pathlib import Path

from vocabmaster import utils


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
    if not validation["valid"]:
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
            results.append(
                {
                    "path": backup_path,
                    "filename": backup["filename"],
                    "type": backup["type"],
                    "valid": format_info["error"] is None,
                    "rows": None,
                    "format_version": format_info["version"],
                    "error": format_info["error"],
                }
            )
            if format_info["error"] is None:
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
