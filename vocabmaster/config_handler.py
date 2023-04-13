from pathlib import Path
import json
from vocabmaster import utils
from vocabmaster import config_handler


def get_config_filepath():
    """
    Gets the configuration file path.

    Returns:
        Path: The path to the application's configuration file.
    """
    app_data_dir = utils.setup_dir()
    config_filepath = app_data_dir / "config.json"
    return config_filepath


def read_config():
    """
    Reads the configuration file.

    Returns:
        dict: The configuration data as a dictionary, or None if the file doesn't exist.
    """
    config_filepath = get_config_filepath()
    if not config_filepath.exists():
        return None
    with open(config_filepath, "r") as file:
        config = json.load(file)
    return config


def write_config(config):
    """
    Writes the configuration data to the configuration file.

    Args:
        config (dict): The configuration data as a dictionary.
    """
    config_filepath = get_config_filepath()
    with open(config_filepath, "w") as file:
        json.dump(config, file, indent=4)


def set_default_language_pair(language_to_learn, mother_tongue):
    """
    Sets the default language pair in the configuration file.

    Args:
        language_to_learn (str): The language the user wants to learn.
        mother_tongue (str): The user's mother tongue.
    """
    config = read_config()
    if config is None:
        config = {}
    config["default"] = {
        "language_to_learn": language_to_learn,
        "mother_tongue": mother_tongue,
    }
    write_config(config)


def get_default_language_pair():
    """
    Gets the default language pair from the configuration file.

    Returns:
        dict: The default language pair as a dictionary, or None if not found.
    """
    config = read_config()
    if config is None or "default" not in config:
        return None
    return config["default"]


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
        if default_pair is None:
            raise Exception(
                "No default language pair found. Please specify a language pair using the `--pair` option. The language pair must be formatted like the following: 'language_to_learn:mother_tongue'. For example: 'english:french'.\nSee `vocabmaster --help` for more information."
            )
        language_to_learn = default_pair["language_to_learn"]
        mother_tongue = default_pair["mother_tongue"]

    return language_to_learn, mother_tongue
