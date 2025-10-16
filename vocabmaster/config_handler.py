import json
import os
import platform
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Optional

APP_NAME = "vocabmaster"
CONFIG_FILENAME = "config.json"
DEFAULT_DATA_DIR_NAME = ".vocabmaster"


def _get_config_base_dir() -> Path:
    """
    Determine the base directory for the application's configuration file.
    """
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / APP_NAME

    system = platform.system()
    if system == "Windows":
        windows_base = os.environ.get("APPDATA")
        if windows_base:
            return Path(windows_base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME

    return Path.home() / ".config" / APP_NAME


def _get_legacy_config_path() -> Optional[Path]:
    """
    Return the legacy configuration file path used in previous releases.
    """
    system = platform.system()
    if system == "Windows":
        windows_base = os.environ.get("APPDATA")
        if windows_base:
            return Path(windows_base) / APP_NAME / CONFIG_FILENAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME / CONFIG_FILENAME
    if system in ("Linux", "Darwin"):
        return Path.home() / ".local" / "share" / APP_NAME / CONFIG_FILENAME
    return None


def _ensure_parent_dir(path: Path) -> None:
    """
    Ensure the parent directory for the provided path exists.
    """
    path.parent.mkdir(parents=True, exist_ok=True)


def _migrate_legacy_config_if_needed(target_path: Path) -> None:
    """
    Copy the legacy configuration file to the new location if needed.
    """
    legacy_path = _get_legacy_config_path()
    if legacy_path and legacy_path.exists() and not target_path.exists():
        try:
            data = legacy_path.read_text(encoding="utf-8")
            json.loads(data)
        except (OSError, json.JSONDecodeError):
            return
        try:
            target_path.write_text(data, encoding="utf-8")
        except OSError:
            return


def get_config_filepath() -> Path:
    """
    Get the path to the configuration file, migrating from the legacy location if necessary.
    """
    config_dir = _get_config_base_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / CONFIG_FILENAME
    _migrate_legacy_config_if_needed(config_path)
    return config_path


def read_config():
    """
    Read the configuration file.
    """
    config_filepath = get_config_filepath()
    if not config_filepath.exists():
        return None
    with open(config_filepath, "r", encoding="utf-8") as file:
        config = json.load(file)
    return config


def write_config(config):
    """
    Write config with atomic rename to prevent corruption.

    Uses write-to-temp-then-rename pattern to ensure config file is never
    left in a corrupted state if the process is killed during write.
    """
    config_filepath = get_config_filepath()
    _ensure_parent_dir(config_filepath)

    serializable_config = deepcopy(config)
    if "data_dir" in serializable_config and isinstance(serializable_config["data_dir"], Path):
        serializable_config["data_dir"] = str(serializable_config["data_dir"])

    # Atomic write: write to temp file in same directory, then rename
    temp_fd, temp_path = tempfile.mkstemp(
        dir=config_filepath.parent,
        prefix='.config_',
        suffix='.tmp',
        text=True
    )

    try:
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as file:
            json.dump(serializable_config, file, indent=4)

        # Atomic rename (os.replace works on all platforms)
        os.replace(temp_path, str(config_filepath))
    except Exception:
        # Clean up temp file on error
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def set_default_language_pair(language_to_learn, mother_tongue):
    """
    Set the default language pair in the configuration file.
    """
    config = read_config() or {}
    config["default"] = {
        "language_to_learn": language_to_learn,
        "mother_tongue": mother_tongue,
    }
    write_config(config)


def set_language_pair(language_to_learn, mother_tongue):
    """
    Append a language pair to the configuration file.
    """
    # Import here to avoid circular dependency
    from vocabmaster.utils import validate_language_name

    # Validate language names to prevent path traversal
    language_to_learn = validate_language_name(language_to_learn)
    mother_tongue = validate_language_name(mother_tongue)

    config = read_config() or {}
    language_pairs = config.setdefault("language_pairs", [])
    language_pairs.append({"language_to_learn": language_to_learn, "mother_tongue": mother_tongue})
    write_config(config)


def remove_language_pair(language_to_learn, mother_tongue):
    """
    Removes a language pair from the configuration file.

    Args:
        language_to_learn (str): The language the user wants to learn.
        mother_tongue (str): The user's mother tongue.

    Returns:
        bool: True if the removed pair was the default language pair, False otherwise.

    Raises:
        ValueError: If no language pairs are configured or if the specified pair is not found.
    """
    config = read_config() or {}
    language_pairs = config.get("language_pairs", [])
    if not language_pairs:
        raise ValueError("No language pairs configured.")

    language_to_learn = language_to_learn.casefold()
    mother_tongue = mother_tongue.casefold()

    remaining_pairs = [
        pair
        for pair in language_pairs
        if not (
            pair["language_to_learn"] == language_to_learn
            and pair["mother_tongue"] == mother_tongue
        )
    ]

    if len(remaining_pairs) == len(language_pairs):
        raise ValueError("Language pair not found.")

    removed_default = False
    default_pair = config.get("default")
    if default_pair:
        default_language = default_pair.get("language_to_learn", "").casefold()
        default_mother = default_pair.get("mother_tongue", "").casefold()
        if default_language == language_to_learn and default_mother == mother_tongue:
            config.pop("default", None)
            removed_default = True

    if remaining_pairs:
        config["language_pairs"] = remaining_pairs
    else:
        config.pop("language_pairs", None)

    write_config(config)
    return removed_default


def rename_language_pair(old_language, old_mother_tongue, new_language, new_mother_tongue):
    """
    Rename an existing language pair.

    Args:
        old_language (str): Current language to learn.
        old_mother_tongue (str): Current mother tongue.
        new_language (str): New language to learn value.
        new_mother_tongue (str): New mother tongue value.

    Returns:
        bool: True if the renamed pair was the default, False otherwise.

    Raises:
        ValueError: If the source pair does not exist, the destination already exists,
            or if both pairs are identical.
    """
    # Import here to avoid circular dependency
    from vocabmaster.utils import validate_language_name

    # Validate new names to prevent path traversal
    new_language = validate_language_name(new_language)
    new_mother_tongue = validate_language_name(new_mother_tongue)

    config = read_config() or {}
    language_pairs = config.get("language_pairs", [])
    if not language_pairs:
        raise ValueError("No language pairs configured.")

    old_key = (old_language.casefold(), old_mother_tongue.casefold())
    new_key = (new_language.casefold(), new_mother_tongue.casefold())

    if old_key == new_key:
        raise ValueError("New language pair must be different from the current one.")

    def pair_key(pair):
        return (pair["language_to_learn"].casefold(), pair["mother_tongue"].casefold())

    if any(pair_key(pair) == new_key for pair in language_pairs):
        raise ValueError(
            f"The language pair {new_key[0]}:{new_key[1]} already exists. Choose another name."
        )

    for index, pair in enumerate(language_pairs):
        if pair_key(pair) == old_key:
            language_pairs[index] = {
                "language_to_learn": new_key[0],
                "mother_tongue": new_key[1],
            }
            break
    else:
        raise ValueError("Language pair not found.")

    config["language_pairs"] = language_pairs

    was_default = False
    default_pair = config.get("default")
    if default_pair:
        default_key = (
            default_pair.get("language_to_learn", "").casefold(),
            default_pair.get("mother_tongue", "").casefold(),
        )
        if default_key == old_key:
            config["default"] = {
                "language_to_learn": new_key[0],
                "mother_tongue": new_key[1],
            }
            was_default = True

    write_config(config)
    return was_default


def get_default_language_pair():
    """
    Get the default language pair from the configuration file.
    """
    config = read_config()
    if config is None or "default" not in config:
        return None
    return config["default"]


def get_language_pair(language_pair):
    """
    Get a language pair from the configuration file, falling back to the default.
    """
    # Import here to avoid circular dependency
    from vocabmaster.utils import validate_language_name

    if language_pair:
        try:
            language_to_learn, mother_tongue = language_pair.split(":")
            # Validate parsed names to prevent path traversal
            language_to_learn = validate_language_name(language_to_learn)
            mother_tongue = validate_language_name(mother_tongue)
        except ValueError as exc:
            # Re-raise ValueError with original message if it's from validation
            if "can only contain" in str(exc) or "too long" in str(exc) or "cannot be empty" in str(exc):
                raise
            raise ValueError("Invalid language pair.") from exc
    else:
        default_pair = get_default_language_pair()
        if default_pair is None:
            raise ValueError(
                "No default language pair found. Please set a default language pair"
                " using 'vocabmaster config default'.\nSee `vocabmaster --help` for"
                " more information."
            )
        language_to_learn = default_pair["language_to_learn"]
        mother_tongue = default_pair["mother_tongue"]

    return language_to_learn, mother_tongue


def get_all_language_pairs():
    """
    Get all language pairs from the configuration file.
    """
    config = read_config()
    if config is None:
        return []
    return config.get("language_pairs", [])


def get_default_data_directory() -> Path:
    """
    Return the default directory used to store CSV and Anki files.
    """
    return Path.home() / DEFAULT_DATA_DIR_NAME


def get_data_directory() -> Path:
    """
    Resolve the directory where CSV and Anki files should be created.
    """
    config = read_config()
    configured = None
    if config and config.get("data_dir"):
        configured = Path(config["data_dir"]).expanduser()
    return configured or get_default_data_directory()


def set_data_directory(path: Path) -> None:
    """
    Persist the directory where CSV and Anki files should be stored.
    """
    config = read_config() or {}
    config["data_dir"] = str(Path(path).expanduser())
    write_config(config)
