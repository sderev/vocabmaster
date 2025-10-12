import json
import os
import platform
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
    Write the configuration data to the configuration file.
    """
    config_filepath = get_config_filepath()
    _ensure_parent_dir(config_filepath)

    serializable_config = deepcopy(config)
    if "data_dir" in serializable_config and isinstance(serializable_config["data_dir"], Path):
        serializable_config["data_dir"] = str(serializable_config["data_dir"])

    with open(config_filepath, "w", encoding="utf-8") as file:
        json.dump(serializable_config, file, indent=4)


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
    if language_pair:
        try:
            language_to_learn, mother_tongue = language_pair.split(":")
        except ValueError as exc:
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
