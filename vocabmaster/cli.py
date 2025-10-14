import platform
import sys

import click
import openai

from vocabmaster import config_handler, csv_handler, gpt_integration

from .utils import openai_api_key_exists, setup_backup_dir, setup_dir, setup_files


@click.group(invoke_without_command=True)
@click.version_option()
@click.pass_context
def vocabmaster(ctx):
    """
    VocabMaster is a command-line tool to help you learn vocabulary.

    It uses ChatGPT to generate translations and examples for your words,
    and creates an Anki deck for you to import.

    Start by setting up a new language pair:
    'vocabmaster setup'

    Add words to your vocabulary list:
    'vocabmaster add to have'

    Generate an Anki deck from your vocabulary list:
    'vocabmaster translate'

    You can find help for each command by running:
    'vocabmaster <command> --help'

    For more information, please visit https://github.com/sderev/vocabmaster.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@vocabmaster.command()
@click.option(
    "--pair",
    type=str,
    help=(
        "This overrides the default language pair. Specify in the format"
        " 'language_to_learn:mother_tongue'. For example: 'english:french'."
    ),
    required=False,
)
@click.argument("word", type=str, nargs=-1)
def add(pair, word):
    """
    Add a word to the vocabulary list, if not already present.

    WORD: The word or phrase to be added to the vocabulary list.

    Examples: 'good', 'to be', 'a cat'
    """
    try:
        language_to_learn, mother_tongue = config_handler.get_language_pair(pair)
    except Exception as error:
        click.secho("Error: ", fg="red", nl=False)
        click.echo(error)
        sys.exit(1)

    translations_filepath, anki_filepath = setup_files(
        setup_dir(), language_to_learn, mother_tongue
    )

    if not word:
        click.echo()
        click.echo("Please provide a word to add.")
        click.echo(
            f"Run '{click.style('vocabmaster add --help', bold=True)}' for more information."
        )
        sys.exit(0)

    word = " ".join(word)
    if csv_handler.word_exists(word, translations_filepath):
        click.echo("That word is already in your list 📒")
    else:
        csv_handler.append_word(word, translations_filepath)
        click.echo("Added to your list! 📝✅")


@vocabmaster.command()
@click.option(
    "--pair",
    type=str,
    help=(
        "This overrides the default language pair. Specify in the format"
        " 'language_to_learn:mother_tongue'. For example: 'english:french'."
    ),
    required=False,
)
@click.option(
    "--count",
    is_flag=True,
    help="Show the number of words remaining to be translated in the vocabulary list.",
    required=False,
)
def translate(pair, count):
    """
    Translate, Add examples, and Generate an Anki deck.

    This command reads your vocabulary list, fetches translations and examples,
    and creates an Anki-ready file for import.

    The generated Anki deck will be saved in the same folder as your vocabulary list.
    """
    try:
        language_to_learn, mother_tongue = config_handler.get_language_pair(pair)
    except Exception as error:
        click.secho("Error: ", fg="red", nl=False)
        click.echo(error)
        sys.exit(1)

    translations_filepath, anki_filepath = setup_files(
        setup_dir(), language_to_learn, mother_tongue
    )

    # Add the fieldnames to the CSV file if it's missing
    csv_handler.add_fieldnames_to_csv_file(
        translations_filepath, ["word", "translation", "example"]
    )

    # Check if the vocabulary list is empty
    if csv_handler.vocabulary_list_is_empty(translations_filepath):
        click.secho("Your vocabulary list is empty.", fg="red", nl=False)
        click.echo(" Please add some words first.")
        click.echo(
            f"Run '{click.style('vocabmaster add --help', bold=True)}' for more information."
        )
        sys.exit(0)

    # Show untranslated words count if `--count` is used, then exit.
    if count:
        try:
            number_words = len(csv_handler.get_words_to_translate(translations_filepath))
        except Exception as error:
            click.secho("Status: ", fg="green", nl=False)
            click.echo(error)
        else:
            click.echo(f"Number of words to translate: {click.style(str(number_words), fg='blue')}")
        sys.exit(0)

    # Check for OpenAI API key
    if not openai_api_key_exists():
        openai_api_key_explain()
        sys.exit(0)

    # Add translations and examples to the CSV file
    click.echo("Adding translations and examples to the file... 🔎📝")
    click.secho("This may take a while...", fg="blue")
    click.echo()

    try:
        csv_handler.add_translations_and_examples_to_file(translations_filepath, pair)
        click.echo()
    except openai.error.RateLimitError as error:
        click.echo(click.style("Error: ", fg="red") + f"{error}")
        handle_rate_limit_error()
        sys.exit(1)
    except Exception as error:
        if (
            str(error) == "All the words in the vocabulary list already have translations and"
            " examples"
        ):
            click.secho("Actually...", fg="blue")
            click.secho("No action needed: ", fg="green", nl=False)
            click.echo(f"{error} 🤓")
            click.echo(
                f"If you only want to generate the Anki deck, you can run '{click.style('vocabmaster anki', bold=True)}'."
            )
        else:
            click.secho("Status: ", fg="red", nl=False)
            click.echo(error)
        sys.exit(0)
    click.secho(
        "The translations and examples have been added to the vocabulary list 💡✅", fg="blue"
    )

    # Generate the Anki deck
    generate_anki_deck(translations_filepath, anki_filepath, language_to_learn, mother_tongue)


def generate_anki_deck(translations_filepath, anki_filepath, language_to_learn, mother_tongue):
    """
    Generates an Anki deck file from a translations file and saves it to the specified path.

    This function takes the input translations file and processes it using the csv_handler's
    generate_anki_output_file function. It then provides feedback to the user about the
    process completion and the location of the generated Anki deck.

    Args:
        translations_filepath (pathlib.Path): Path to the input translations file (CSV format).
        anki_filepath (pathlib.Path): Path to save the generated Anki deck file.
        language_to_learn (str): The target language being learned.
        mother_tongue (str): The user's native language.

    Returns:
        None
    """
    click.echo()
    click.echo("Generating the Anki deck... 📜")
    click.echo()
    csv_handler.generate_anki_output_file(
        translations_filepath, anki_filepath, language_to_learn, mother_tongue
    )
    click.echo("The Anki deck has been generated 🤓✅")
    click.echo()
    click.secho("You can now import the deck into Anki 📚", fg="green")

    click.secho("The deck is located at:", bold=True)
    click.echo(f"{anki_filepath}")


@vocabmaster.command()
def anki():
    """
    Generate an Anki deck from your vocabulary list.

    The Anki deck will be saved in the same folder as your vocabulary list.
    """
    language_to_learn = config_handler.get_default_language_pair()["language_to_learn"]
    mother_tongue = config_handler.get_default_language_pair()["mother_tongue"]

    translations_filepath, anki_filepath = setup_files(
        setup_dir(), language_to_learn, mother_tongue
    )

    generate_anki_deck(translations_filepath, anki_filepath, language_to_learn, mother_tongue)


@vocabmaster.command()
def setup():
    """
    Set up a new language pair.

    This command creates the necessary folders and files
    for the specified mother tongue and language to learn.
    You can set up as many language pairs as you want.

    Example usage:
    vocabmaster setup
    """
    language_to_learn = click.prompt("Please enter the language you want to learn")
    mother_tongue = click.prompt("Please enter your mother tongue")

    click.echo()
    click.echo(
        f"Setting up VocabMaster for learning {click.style(language_to_learn.capitalize(), bold=True)}, "
        f"and {click.style(mother_tongue.capitalize(), bold=True)} is your mother tongue."
    )

    if click.confirm("Do you want to proceed?"):
        # Create the necessary folders and files
        app_data_dir = setup_dir()
        language_to_learn = language_to_learn.casefold()
        mother_tongue = mother_tongue.casefold()

        translations_filepath, anki_filepath = setup_files(
            app_data_dir, language_to_learn, mother_tongue
        )

        backup_lang = setup_backup_dir(app_data_dir, language_to_learn, mother_tongue)
        config_handler.set_language_pair(language_to_learn, mother_tongue)

        click.echo()
        click.echo(f"Translations file: {translations_filepath}")
        click.echo(f"Anki deck file: {anki_filepath}")
        click.echo(f"Backup directory: {backup_lang}")
        click.echo()
        click.echo(f"VocabMaster setup for {language_to_learn} to {mother_tongue} complete 🤓✅")
        click.echo()
    else:
        click.secho("Setup canceled", fg="red")

    # Set the default language pair
    if config_handler.get_default_language_pair() is None:
        config_handler.set_default_language_pair(language_to_learn, mother_tongue)
        click.echo(
            f"This language pair ({language_to_learn}:{mother_tongue}) has been set as"
            " the default ✅"
        )

    # Ask the user if they want to set the language pair as the new default
    else:
        print_default_language_pair()

        if click.confirm("Do you want to set this language pair as the default?"):
            if click.confirm(
                f"{click.style('Are you sure?', fg='red')} This will overwrite the current default 🚨"
            ):
                config_handler.set_default_language_pair(language_to_learn, mother_tongue)
            click.echo()
            click.echo("This language pair has been set as the default ✅")
            click.secho("The new default language pair is:", fg="blue")

            # Get the new default language pair by reinitalizing the variables to avoid confusion
            default_language_to_learn = config_handler.get_default_language_pair()[
                "language_to_learn"
            ]
            default_mother_tongue = config_handler.get_default_language_pair()["mother_tongue"]
            click.echo(
                f"{click.style('Language to learn:', bold=True)} {default_language_to_learn.capitalize()}"
            )
            click.echo(
                f"{click.style('Mother tongue:', bold=True)} {default_mother_tongue.capitalize()}"
            )
            click.echo()

        else:
            click.echo("This language pair has not been set as the default ❌")
            click.echo()
            click.echo("The current default language pair is:")
            default_language_to_learn = config_handler.get_default_language_pair()[
                "language_to_learn"
            ]
            default_mother_tongue = config_handler.get_default_language_pair()["mother_tongue"]
            click.secho(f"{default_language_to_learn}:{default_mother_tongue}", bold=True)


@vocabmaster.command()
def default():
    """
    Show the current default language pair.
    """
    print_default_language_pair()
    click.echo()
    click.secho("You can change the default language pair at any time by running:", fg="blue")
    click.secho("vocabmaster config default", bold=True)


@vocabmaster.group(invoke_without_command=True)
@click.pass_context
def config(ctx):
    """
    Manage the configuration of VocabMaster.

    This command allows you to set the default language pair,
    and the OpenAI API key.

    Example usage:
    'vocabmaster config default'

    Example usage:
    'vocabmaster config key'
    """
    # the directory where the translations and Anki decks are stored,
    # Example usage:
    #'vocabmaster config dir'
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@config.command("default")
def config_default_language_pair():
    """
    Set the default language pair.

    This language pair will be used by default
    when you run the 'vocabmaster' command
    without specifying a language pair with '--pair'.
    """
    print_default_language_pair()

    print_all_language_pairs()
    choice = click.prompt(
        "Type the language pair or its number to set it as the new default",
        type=str,
    )

    # Check if the user entered a correct number
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(config_handler.get_all_language_pairs()):
            # Set the language pair as the default
            language_to_learn = config_handler.get_all_language_pairs()[idx]["language_to_learn"]
            mother_tongue = config_handler.get_all_language_pairs()[idx]["mother_tongue"]
            config_handler.set_default_language_pair(language_to_learn, mother_tongue)
            click.echo(
                f"{click.style(f'{language_to_learn}:{mother_tongue}', bold=True)} "
                f"{click.style('has been set as the default language pair', fg='green')} ✅"
            )
        else:
            # The user entered a number that is out of range
            click.secho("Invalid choice", fg="red")
            click.echo(
                "Please enter a number between 1 and"
                f" {len(config_handler.get_all_language_pairs())}"
            )
    else:
        # Check if the language pair exists
        try:
            if config_handler.get_language_pair(choice) is not None:
                # Set the language pair as the default
                language_to_learn, mother_tongue = config_handler.get_language_pair(choice)
        # The user entered an invalid language pair
        except ValueError as error:
            click.secho(str(error), fg="red")
            click.echo(f"The format is {click.style('language_to_learn:mother_tongue', bold=True)}")
            sys.exit(1)

        # Set the language pair as the default
        config_handler.set_default_language_pair(language_to_learn, mother_tongue)
        click.echo(
            f"{click.style(f'{language_to_learn}:{mother_tongue}', bold=True)} "
            f"{click.style('has been set as the default language pair', fg='green')} ✅"
        )


# @config.command("dir")
# def config_dir():
#    """
#    Set the directory where the list and the Anki deck are stored.
#    """
#    custom_app_data_dir = click.prompt("Enter the path for the new directory", type=str)
#    setup_dir(custom_app_data_dir)


@config.command("key")
def config_key():
    """
    Set the OpenAI API key.
    """
    if openai_api_key_exists():
        click.secho("OpenAI API key found!", fg="green")
        click.echo()
        click.echo(
            f"You can use '{click.style('vocabmaster translate', bold=True)}' to generate translations."
        )
        click.echo()
        click.echo(
            f"If you only want to generate your Anki deck, you can use '{click.style('vocabmaster anki', bold=True)}'."
        )
    if not openai_api_key_exists():
        openai_api_key_explain()


def openai_api_key_explain():
    """
    Explain how to set up the OpenAI API key.
    """
    click.secho("You need to set up an OpenAI API key.", fg="red")
    click.echo()
    click.echo(
        "You can generate API keys in the OpenAI web interface. See"
        " https://platform.openai.com/account/api-keys for details."
    )
    click.echo()
    if platform.system() == "Windows":
        click.echo("Then, you can set it up by running `setx OPENAI_API_KEY your_key`")
    else:
        click.echo("Then, you can set it up by running `export OPENAI_API_KEY=YOUR_KEY`")
    return


@vocabmaster.command()
def show():
    """
    Show all the language pairs that have been set up.
    """
    print_all_language_pairs()
    click.secho("You can change the default at any time by running:", fg="blue")
    click.secho("vocabmaster config default", bold=True)


@vocabmaster.command()
def tokens():
    """
    Estimate the cost of the next translation.

    This command estimates the cost of the next translation,
    based on the number of tokens in the prompt.

    Note that this is only the estimation of the cost of the next prompt,
    not the total cost of the translation.
    The total cost (prompt + translation) cannot exceed $0.008192 per request, though.
    """
    language_to_learn = config_handler.get_default_language_pair()["language_to_learn"]
    mother_tongue = config_handler.get_default_language_pair()["mother_tongue"]
    translations_filepath, anki_file = setup_files(setup_dir(), language_to_learn, mother_tongue)

    if csv_handler.vocabulary_list_is_empty(translations_filepath):
        click.secho("The list is empty!", fg="red")
        click.echo("Please add words to the list before running this command.")
        sys.exit(0)

    try:
        words_to_translate = csv_handler.get_words_to_translate(translations_filepath)
    except Exception as error:
        click.secho("Status: ", fg="blue", nl=False)
        click.echo(error)
        click.echo("Therefore, the cost of the next prompt cannot be estimated.")
    else:
        prompt = gpt_integration.format_prompt(language_to_learn, mother_tongue, words_to_translate)
        estimated_cost = gpt_integration.estimate_prompt_cost(prompt)["gpt-3.5-turbo"]
        click.echo(
            f"The estimated cost of the next prompt is {click.style(f'${estimated_cost}', fg='blue')}."
        )


def print_default_language_pair():
    """
    Print the current default language pair.
    """
    click.secho("The current default language pair is:", fg="blue")
    default_language_to_learn = config_handler.get_default_language_pair()["language_to_learn"]
    default_mother_tongue = config_handler.get_default_language_pair()["mother_tongue"]
    click.secho(f"{default_language_to_learn}:{default_mother_tongue}", fg="yellow", bold=True)
    click.echo()


def print_all_language_pairs():
    """
    Print all the language pairs that have been set up.
    """
    click.secho("The following language pairs have been set up:", fg="blue")
    language_pairs = config_handler.get_all_language_pairs()
    for idx, language_pair in enumerate(language_pairs, start=1):
        click.echo(f"{idx}. {language_pair['language_to_learn']}:{language_pair['mother_tongue']}")
    click.echo()


def handle_rate_limit_error():
    """
    Provides guidance on how to handle a rate limit error.
    """
    click.echo()
    click.echo(
        click.style(
            ("You might not have set a usage rate limit in your OpenAI account settings. "),
            fg="blue",
        )
    )
    click.echo(
        "If that's the case, you can set it"
        " here:\nhttps://platform.openai.com/account/billing/limits"
    )

    click.echo()
    click.echo(
        click.style(
            "If you have set a usage rate limit, please try the following steps:",
            fg="blue",
        )
    )
    click.echo("- Wait a few seconds before trying again.")
    click.echo()
    click.echo(
        "- Reduce your request rate or batch tokens. You can read the"
        " OpenAI rate limits"
        " here:\nhttps://platform.openai.com/account/rate-limits"
    )
    click.echo()
    click.echo(
        "- If you are using the free plan, you can upgrade to the paid"
        " plan"
        " here:\nhttps://platform.openai.com/account/billing/overview"
    )
    click.echo()
    click.echo(
        "- If you are using the paid plan, you can increase your usage"
        " rate limit"
        " here:\nhttps://platform.openai.com/account/billing/limits"
    )
    click.echo()
