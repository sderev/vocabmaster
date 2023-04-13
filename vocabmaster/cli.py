import click
from vocabmaster import csv_handler
from vocabmaster import config_handler
from .utils import *


@click.group()
def main():
    """
    VocabMaster is a command-line tool for learning vocabulary.
    """
    pass


@click.option(
    "-p",
    "--pair",
    type=str,
    help="Specify the language pair to use in the format 'language_to_learn:mother_tongue'. For example: 'english:french'.",
    #required=False,
)
@main.command()
@click.argument("word", type=str, nargs=-1)
def add(pair, word):
    """
    Add a word to the vocabulary list, if not already present.
    Examples: 'run', 'to run', 'a cat'

    WORD: The word or phrase to be added to the vocabulary list.
    """
    language_to_learn, mother_tongue = config_handler.get_language_pair_from_option(
        pair
    )
    translations_filepath, anki_filepath = setup_files(
        setup_dir(), language_to_learn, mother_tongue
    )

    if not word:
        click.echo("Please provide a word to add.")
        return

    word = " ".join(word)
    if csv_handler.word_exists(word, translations_filepath):
        click.echo("The word is already in the list 📒")
    else:
        csv_handler.append_word(word, translations_filepath)
        click.echo("The word has been appended to the list 📝✅")


@main.command()
@click.option(
    "--pair",
    type=str,
    help="Specify the language pair to use in the format 'language_to_learn:mother_tongue'. For example: 'english:french'.",
    required=False,
)
def translate(pair):
    """
    Generate an Anki deck from your vocabulary list.

    This command reads your vocabulary list, fetches translations and examples, and creates an Anki-ready file for import.
    The generated Anki deck will be saved in the same folder as your vocabulary list.

    Example usage:
    vocabmaster translate
    """
    language_to_learn, mother_tongue = config_handler.get_language_pair_from_option(
        pair
    )
    print(f"language_to_learn: {language_to_learn}, mother_tongue: {mother_tongue}")

    translations_filepath, anki_filepath = setup_files(
        setup_dir(), language_to_learn, mother_tongue
    )

    # Add the header to the CSV file if it's missing
    csv_handler.add_header_to_csv_file(
        translations_filepath, ["word", "translation", "example"]
    )
    try:
        click.echo("Adding translations and examples to the file... 🔎📝")
        click.echo("This may take a while...")
        click.echo()
        csv_handler.add_translations_and_examples_to_file(translations_filepath, pair)
        click.echo()
    except Exception as error:
        click.echo(f"Status: {error}")
    else:
        click.echo(
            "The translations and examples have been added to the vocabulary list 💡✅"
        )
    finally:
        click.echo()
        click.echo("Generating the Anki deck... 📜")
        click.echo()
        csv_handler.generate_anki_output_file(translations_filepath, anki_filepath)
        click.echo("The Anki deck has been generated 🤓✅")
        click.echo()
        click.echo("You can now import the deck into Anki 📚")

        BOLD = "\x1b[1m"
        RESET = "\x1b[0m"
        click.echo(f"{BOLD}The deck is located at:{RESET}")
        click.echo(f"{anki_filepath}")
        click.echo()
        # click.echo("You can also import the deck directly into Anki by running:")
        # click.echo("vocabmaster import")
        # click.echo()


@main.command()
def setup():
    """
    Set up a new language pair for VocabMaster.

    This command creates the necessary folders and files for the specified mother tongue and language to learn.
    You can set up as many language pairs as you want.

    Example usage:
    vocabmaster setup
    """
    language_to_learn = click.prompt("Please enter the language you want to learn")
    mother_tongue = click.prompt("Please enter your mother tongue")
    click.echo(
        f"Setting up VocabMaster for learning {language_to_learn.capitalize()}, and {mother_tongue.capitalize()} is your mother tongue."
    )

    if click.confirm("Do you want to proceed?"):
        app_data_dir = setup_dir()
        language_to_learn = language_to_learn.casefold()
        mother_tongue = mother_tongue.casefold()
        translations_filepath, anki_filepath = setup_files(
            app_data_dir, language_to_learn, mother_tongue
        )
        backup_lang = setup_backup_dir(app_data_dir, language_to_learn, mother_tongue)

        click.echo()
        click.echo(
            f"VocabMaster setup for {language_to_learn} to {mother_tongue} complete 🤓✅"
        )
        click.echo()
        click.echo(f"Translations file: {translations_filepath}")
        click.echo(f"Anki deck file: {anki_filepath}")
        click.echo(f"Backup directory: {backup_lang}")
        click.echo()
    else:
        RED = "\x1b[38;5;9m"
        RESET = "\x1b[0m"
        click.echo(f"{RED}Setup canceled{RESET}")

    if config_handler.get_default_language_pair() is None:
        config_handler.set_default_language_pair(language_to_learn, mother_tongue)
        click.echo(
            f"This language pair ({language_to_learn}:{mother_tongue}) has been set as the default ✅"
        )
    else:
        if click.confirm("Do you want to set this language pair as the default?"):
            if click.confirm("Are you sure? This will overwrite the current default 🚨"):
                config_handler.set_default_language_pair(language_to_learn, mother_tongue)
            click.echo("This language pair has been set as the default ✅")
        else:
            click.echo("This language pair has not been set as the default ❌")
            click.echo()
            click.echo("The default language pair is:")
            click.echo(config_handler.get_default_language_pair())

