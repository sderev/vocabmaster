import os
import platform
import shutil
from datetime import datetime
from pathlib import Path

import click

from vocabmaster import config_handler


def setup_dir():
    """
    Creates the application data directory if it doesn't exist and returns its path.
    The directory location is determined based on the global app_name variable and the user's operating system.

    Returns:
        pathlib.Path: The path to the application data directory.
    """
    system = platform.system()
    if system == "Windows":
        app_data_dir = Path.home() / "AppData" / "Roaming" / app_name
    elif system in ("Linux", "Darwin"):
        app_data_dir = Path.home() / ".local" / "share" / app_name
    else:
        click.echo("We couldn't identify your OS.", err=True)
        while True:
            try:
                app_data_dir = Path(
                    input("Please, tell us where you want your files to be installed: ")
                )
                app_data_dir.mkdir(exist_ok=True, parents=True)
            except Exception as err:
                click.echo(click.style("Error:", fg="red", bold=True) + f" {err}", err=True)
            else:
                break
    app_data_dir.mkdir(exist_ok=True, parents=True)
    return app_data_dir


def setup_files(app_data_dir, language_to_learn, mother_tongue):
    """
    Creates the necessary file paths in the data directory if they don't exist.

    Args:
    app_data_dir (pathlib.Path): The directory where the application data files should be created.
    language_to_learn (str): The language the user wants to learn.
    mother_tongue (str): The user's mother tongue.

    Returns:
    tuple: A tuple containing the paths of the created files (vocab_list.csv, anki_deck.csv).
    """
    file_paths = (
        app_data_dir / f"vocab_list_{language_to_learn}-{mother_tongue}.csv",
        app_data_dir / f"anki_deck_{language_to_learn}-{mother_tongue}.csv",
    )
    for file in file_paths:
        file.touch()
    return file_paths


def setup_backup_dir(app_data_dir, language_to_learn, mother_tongue):
    """
    Creates the backup directory if it doesn't exist and returns its path.
        The backup directory is created inside the global app_data_dir directory.
        If both mother_tongue and language_to_learn are provided, a subdirectory is created for the specific language pair.

    Args:
        app_data_dir (pathlib.Path): The global application data directory.
        language_to_learn (str): The language the user wants to learn.
        mother_tongue (str): The user's mother tongue.

    Returns:
        pathlib.Path: The path to the backup directory (or the language-specific subdirectory).
    """
    backup_dir = get_backup_dir(language_to_learn, mother_tongue)
    backup_lang = backup_dir / ".backup" / f"{language_to_learn}-{mother_tongue}"
    backup_lang.mkdir(exist_ok=True, parents=True)
    return backup_lang


def get_backup_dir(language_to_learn, mother_tongue):
    """
    Returns the path to the backup directory (or the language-specific subdirectory).

    Args:
        language_to_learn (str): The language the user wants to learn.
        mother_tongue (str): The user's mother tongue.

    Returns:
        pathlib.Path: The path to the backup directory (or the language-specific subdirectory).
    """
    backup_dir = app_data_dir / ".backup"
    if language_to_learn and mother_tongue:
        backup_dir = backup_dir / f"{language_to_learn}-{mother_tongue}"
    return backup_dir


def backup_content(backup_dir, content):
    """
    Creates a timestamped backup file for the provided content in the backup_dir directory.
    A maximum of 15 backup files will be saved, after which the oldest backup file will be overwritten.

    Args:
        backup_dir (pathlib.Path): The backup directory path.
        content (str): The content to be written to the backup file.

    Returns:
        None
    """
    iso_timestamp = generate_iso_timestamp()

    # Create a new backup file with the generated timestamp
    backup_file = backup_dir / f"gpt_request_{iso_timestamp}.bak"
    with backup_file.open("w", encoding="UTF-8") as file:
        file.write(str(content))

    # If there are more than 15 backup files in the directory, delete the oldest backup file
    backup_files = sorted(
        list(backup_dir.glob("gpt_request" + "_*.bak")),
        key=lambda p: p.stat().st_mtime,
    )
    if len(backup_files) > 15:
        oldest_backup_file = backup_files[0]
        oldest_backup_file.unlink(missing_ok=True)


def backup_file(backup_dir, filepath):
    """
    Creates a timestamped backup file for the provided filepath in the backup_dir directory.
    A maximum of 10 backup files will be saved, after which the oldest backup file will be overwritten.

    Args:
        backup_dir (pathlib.Path): The backup directory path.
        filepath (pathlib.Path): The path to the file to be backed up.

    Returns:
        None
    """
    iso_timestamp = generate_iso_timestamp()

    # Create a new backup file with the generated timestamp
    backup_voc_list = backup_dir / f"{filepath.stem}_{iso_timestamp}.bak"
    shutil.copy(filepath, backup_voc_list)

    # If there are more than 10 backup files in the directory, delete the oldest backup file
    backup_files = sorted(
        list(backup_dir.glob(f"{filepath.stem}_*.bak")), key=lambda p: p.stat().st_mtime
    )
    if len(backup_files) > 10:
        oldest_backup_file = backup_files[0]
        oldest_backup_file.unlink()


def generate_iso_timestamp():
    """
    Generates an ISO 8601 formatted timestamp with colons replaced by underscores.

    Returns:
        str: The generated ISO 8601 formatted timestamp with colons replaced by underscores.
    """
    now = datetime.now()
    return now.isoformat().replace(":", "_")


def get_language_pair_from_option(pair):
    """
    Gets the language pair based on the input option string or the default language pair.

    If the 'pair' argument is not empty, the function will extract the mother tongue and language
    to learn from the input string. If the 'pair' argument is empty, the default language pair
    from the configuration file will be used.

    Args:
        pair (str): A string containing the language pair separated by a colon, e.g. "english:french",
            where 'english' is the language to learn and 'french' is the mother tongue. If empty, the default
            language pair from the configuration file will be used.

    Returns:
        tuple: A tuple containing the language to learn and the mother tongue as strings.
    """
    if pair:
        language_to_learn, mother_tongue = pair.split(":")
    else:
        default_pair = config_handler.get_default_language_pair()
        language_to_learn = default_pair["language_to_learn"]
        mother_tongue = default_pair["mother_tongue"]

    return language_to_learn, mother_tongue


def openai_api_key_exists():
    """
    Checks if an OpenAI API key is set on the system.

    Returns:
        bool: True if the OpenAI API key is set, False otherwise.
    """
    return bool(os.environ.get("OPENAI_API_KEY"))


app_name = "vocabmaster"
app_data_dir = setup_dir()
BLUE = "\x1b[94m"
BOLD = "\x1b[1m"
GREEN = "\x1b[92m"
ORANGE = "\x1b[93m"
RED = "\x1b[91m"
RESET = "\x1b[0m"
