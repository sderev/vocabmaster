import platform
import sys
from pathlib import Path

import click
import openai

from vocabmaster import config_handler, csv_handler, gpt_integration

from . import utils
from .utils import openai_api_key_exists, setup_backup_dir, setup_dir, setup_files


class AliasedGroup(click.Group):
    """
    Click group with support for hidden command aliases.
    """

    def __init__(self, *args, **kwargs):
        self._aliases = kwargs.pop("aliases", {})
        super().__init__(*args, **kwargs)

    def get_command(self, ctx, cmd_name):
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command

        target = self._aliases.get(cmd_name)
        if target is not None:
            return super().get_command(ctx, target)
        return None

    def list_commands(self, ctx):
        commands = super().list_commands(ctx)
        return [name for name in commands if name not in self._aliases]


@click.group(cls=AliasedGroup, invoke_without_command=True, aliases={"pair": "pairs"})
@click.version_option()
@click.pass_context
def vocabmaster(ctx):
    """
    VocabMaster is a command-line tool to help you learn vocabulary.

    It uses ChatGPT to generate translations and examples for your words,
    and creates an Anki deck for you to import.

    Start by setting up a new language pair:
    'vocabmaster pairs add'

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
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo(error, err=True)
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
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo(error, err=True)
        sys.exit(1)

    translations_filepath, anki_filepath = setup_files(
        setup_dir(), language_to_learn, mother_tongue
    )

    # Add the fieldnames to the CSV file if it's missing
    csv_handler.ensure_csv_has_fieldnames(translations_filepath)

    # Check if the vocabulary list is empty
    if csv_handler.vocabulary_list_is_empty(translations_filepath):
        click.secho("Your vocabulary list is empty.", fg="red", nl=False, err=True)
        click.echo(" Please add some words first.", err=True)
        click.echo(
            f"Run '{click.style('vocabmaster add --help', bold=True)}' for more information.",
            err=True,
        )
        sys.exit(0)

    # Show untranslated words count if `--count` is used, then exit.
    if count:
        try:
            number_words = len(csv_handler.get_words_to_translate(translations_filepath))
        except csv_handler.AllWordsTranslatedError as error:
            click.secho("Status: ", fg="green", nl=False)
            click.echo(error)
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
        click.echo(click.style("Error: ", fg="red") + f"{error}", err=True)
        handle_rate_limit_error()
        sys.exit(1)
    except csv_handler.AllWordsTranslatedError as error:
        click.secho("Actually...", fg="blue")
        click.secho("No action needed: ", fg="green", nl=False)
        click.echo(f"{error} 🤓")
        click.echo(
            f"If you only want to generate the Anki deck, you can run '{click.style('vocabmaster anki', bold=True)}'."
        )
        sys.exit(0)
    except Exception as error:
        click.secho("Status: ", fg="red", nl=False, err=True)
        click.echo(error, err=True)
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
@click.option(
    "--pair",
    type=str,
    help=(
        "Generate the deck for a specific language pair. Specify in the format "
        "'language_to_learn:mother_tongue'."
    ),
    required=False,
)
def anki(pair):
    """
    Generate an Anki deck from your vocabulary list.

    The Anki deck will be saved in the same folder as your vocabulary list.
    """
    try:
        language_to_learn, mother_tongue = config_handler.get_language_pair(pair)
    except Exception as error:
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo(error, err=True)
        if pair is None:
            click.echo(
                f"Run '{click.style('vocabmaster pairs add', bold=True)}' to create a language pair.",
                err=True,
            )
        sys.exit(1)

    translations_filepath, anki_filepath = setup_files(
        setup_dir(), language_to_learn, mother_tongue
    )

    generate_anki_deck(translations_filepath, anki_filepath, language_to_learn, mother_tongue)


def create_language_pair_interactively():
    """
    Interactive workflow used by the `pairs add` command.
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

        backup_lang = setup_backup_dir(language_to_learn, mother_tongue)
        config_handler.set_language_pair(language_to_learn, mother_tongue)

        click.echo()
        click.echo(f"Translations file: {translations_filepath}")
        click.echo(f"Anki deck file: {anki_filepath}")
        click.echo(f"Backup directory: {backup_lang}")
        click.echo()
        click.echo(f"Language pair {language_to_learn}:{mother_tongue} is ready 🤓✅")
        click.echo()

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

            prompt = f"Set this language pair ({language_to_learn}:{mother_tongue}) as the default?"
            if click.confirm(prompt, default=False):
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
                click.echo("Keeping the existing default language pair.")
                click.echo()
                click.echo("The current default language pair is:")
                default_language_to_learn = config_handler.get_default_language_pair()[
                    "language_to_learn"
                ]
                default_mother_tongue = config_handler.get_default_language_pair()["mother_tongue"]
                click.secho(f"{default_language_to_learn}:{default_mother_tongue}", bold=True)
    else:
        click.secho("Creation canceled", fg="red")


@vocabmaster.group(invoke_without_command=True)
@click.pass_context
def config(ctx):
    """
    Manage VocabMaster configuration such as language pairs, storage location, and API keys.

    Run 'vocabmaster config dir' to choose where CSV and Anki files are stored. The configuration
    file itself always lives under ~/.config/vocabmaster/config.json.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@config.command("dir")
@click.option(
    "--show",
    "show_only",
    is_flag=True,
    help="Display the current storage directory and exit without making changes.",
)
@click.argument("directory", required=False)
def config_dir(show_only, directory):
    """
    Set the dir where the vocab list and Anki deck are stored.
    """
    current_dir = config_handler.get_data_directory()
    if show_only and directory is not None:
        raise click.BadParameter(
            "Cannot use '--show' together with a directory path.",
            param_hint="'--show'",
        )

    print_current_storage_directory(current_dir)

    if show_only:
        return

    if directory is None:
        directory_input = click.prompt(
            "Enter the directory to store your CSV and Anki files",
            default=str(current_dir),
        )
    else:
        directory_input = directory

    target_path = Path(directory_input).expanduser()
    if target_path.exists() and not target_path.is_dir():
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo(f"{target_path} exists and is not a directory.", err=True)
        sys.exit(1)

    try:
        target_path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo(f"Unable to use '{target_path}': {error}", err=True)
        sys.exit(1)

    config_handler.set_data_directory(target_path)
    click.secho("Storage updated!", fg="green")
    click.echo(f"Vocabulary CSV and Anki decks will now be stored in {target_path}")
    click.echo(f"You can also edit {config_handler.get_config_filepath()} directly.")


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


@vocabmaster.group("pairs", invoke_without_command=True)
@click.pass_context
def pairs(ctx):
    """
    Manage language pairs (list, add, remove, rename, inspect).
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@pairs.command("list")
def pairs_list():
    """
    List all configured language pairs.
    """
    print_all_language_pairs(
        f"Use {click.style('vocabmaster pairs add', bold=True)} to add a new language pair."
    )


@pairs.command("add")
def pairs_add():
    """
    Create a new language pair.
    """
    create_language_pair_interactively()


@pairs.command("default")
def pairs_default_command():
    """
    Show the current default language pair.
    """
    print_default_language_pair()
    click.secho("You can change the default language pair at any time by running:", fg="blue")
    click.secho("vocabmaster pairs set-default", bold=True)


@pairs.command("set-default")
def pairs_set_default_command():
    """
    Set the default language pair.
    """
    language_pairs = get_language_pairs_or_abort(
        f"Use {click.style('vocabmaster pairs add', bold=True)} to add a new language pair.",
        "No language pairs found. Run 'vocabmaster pairs add' to add one before setting a default.",
    )
    select_default_language_pair(language_pairs)


@pairs.command("remove")
def pairs_remove_command():
    """
    Remove one or multiple language pairs.
    """

    language_pairs = get_language_pairs_or_abort(
        f"Use {click.style('vocabmaster pairs add', bold=True)} to add a new language pair.",
        "No language pairs found. Run 'vocabmaster pairs add' to add one before removing.",
    )

    remove_language_pairs(
        language_pairs,
        default_hint="Run 'vocabmaster pairs set-default' to choose a new default.",
        add_hint="Use 'vocabmaster pairs add' to add a new language pair.",
    )


@pairs.command("rename")
def pairs_rename_command():
    """
    Rename an existing language pair.
    """
    language_pairs = get_language_pairs_or_abort(
        f"Use {click.style('vocabmaster pairs add', bold=True)} to add a new language pair.",
        "No language pairs found. Run 'vocabmaster pairs add' to add one before renaming.",
    )

    choice = click.prompt(
        "Type the language pair or its number to rename",
        type=str,
    )

    try:
        old_language, old_mother_tongue = resolve_language_pair_choice(choice, language_pairs)
    except ValueError as error:
        message = str(error)
        click.secho("Error: ", fg="red", nl=False, err=True)
        if message == "Invalid choice":
            click.echo(message, err=True)
            click.echo(
                f"Please enter a number between 1 and {len(language_pairs)}",
                err=True,
            )
        elif "Invalid language pair." in message:
            click.echo(message, err=True)
            click.echo(
                f"The format is {click.style('language_to_learn:mother_tongue', bold=True)}",
                err=True,
            )
        else:
            click.echo(message, err=True)
        sys.exit(1)

    new_pair_input = click.prompt(
        "Enter the new language pair (language_to_learn:mother_tongue)",
        type=str,
    ).strip()

    if not new_pair_input:
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo("New language pair cannot be empty.", err=True)
        sys.exit(1)

    try:
        new_language, new_mother_tongue = config_handler.get_language_pair(new_pair_input)
    except ValueError as error:
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo(str(error), err=True)
        click.echo(
            f"The format is {click.style('language_to_learn:mother_tongue', bold=True)}",
            err=True,
        )
        sys.exit(1)

    new_language = new_language.casefold()
    new_mother_tongue = new_mother_tongue.casefold()

    old_key = (old_language.casefold(), old_mother_tongue.casefold())
    new_key = (new_language, new_mother_tongue)

    if old_key == new_key:
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo("New language pair must be different from the current one.", err=True)
        sys.exit(1)

    existing_pairs = config_handler.get_all_language_pairs()
    if any(
        pair["language_to_learn"].casefold() == new_key[0]
        and pair["mother_tongue"].casefold() == new_key[1]
        for pair in existing_pairs
    ):
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo(
            f"The language pair {new_key[0]}:{new_key[1]} already exists. Choose another name.",
            err=True,
        )
        sys.exit(1)

    confirm_prompt = (
        f"Rename {old_language}:{old_mother_tongue} to {new_language}:{new_mother_tongue}?"
    )
    if not click.confirm(confirm_prompt, default=False):
        click.echo("No changes made.")
        return

    utils.backup_language_pair_files(old_language, old_mother_tongue)

    old_translations_path, old_anki_path = utils.get_pair_file_paths(
        old_language, old_mother_tongue
    )
    new_translations_path, new_anki_path = utils.get_pair_file_paths(
        new_language, new_mother_tongue
    )

    if old_translations_path.exists():
        old_translations_path.rename(new_translations_path)
    else:
        new_translations_path.touch(exist_ok=True)

    if old_anki_path.exists():
        old_anki_path.rename(new_anki_path)
    else:
        new_anki_path.touch(exist_ok=True)

    was_default = config_handler.rename_language_pair(
        old_language, old_mother_tongue, new_language, new_mother_tongue
    )

    click.echo(
        f"{old_language}:{old_mother_tongue} has been renamed to {new_language}:{new_mother_tongue}"
    )

    if was_default:
        click.secho(
            f"{new_language}:{new_mother_tongue} is now your default language pair.",
            fg="blue",
        )


@pairs.command("inspect")
@click.option(
    "--pair",
    type=str,
    help=(
        "Inspect a specific language pair. Specify in the format 'language_to_learn:mother_tongue'."
    ),
    required=False,
)
def pairs_inspect_command(pair):
    """
    Inspect a language pair and display storage information.
    """
    if pair is None:
        default_pair = config_handler.get_default_language_pair()
        if default_pair is None:
            click.secho("Error: ", fg="red", nl=False, err=True)
            click.echo(
                "No default language pair found. Run 'vocabmaster pairs add' to create one.",
                err=True,
            )
            sys.exit(1)
        language_to_learn = default_pair["language_to_learn"]
        mother_tongue = default_pair["mother_tongue"]
    else:
        try:
            language_to_learn, mother_tongue = config_handler.get_language_pair(pair)
        except ValueError:
            click.secho("Error: ", fg="red", nl=False, err=True)
            click.echo(
                f"The format is {click.style('language_to_learn:mother_tongue', bold=True)}",
                err=True,
            )
            sys.exit(1)

    normalized_pair = (language_to_learn.casefold(), mother_tongue.casefold())

    language_pairs = config_handler.get_all_language_pairs()
    pair_exists = any(
        pair["language_to_learn"].casefold() == normalized_pair[0]
        and pair["mother_tongue"].casefold() == normalized_pair[1]
        for pair in language_pairs
    )
    if not pair_exists:
        provided = pair.strip().casefold() if pair else f"{normalized_pair[0]}:{normalized_pair[1]}"
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo(
            f"The language pair {provided} was not found.",
            err=True,
        )
        sys.exit(1)

    translations_path, anki_path = utils.get_pair_file_paths(normalized_pair[0], normalized_pair[1])
    stats = csv_handler.calculate_vocabulary_stats(translations_path)

    default_pair = config_handler.get_default_language_pair()
    is_default = False
    if default_pair:
        is_default = (
            default_pair.get("language_to_learn", "").casefold() == normalized_pair[0]
            and default_pair.get("mother_tongue", "").casefold() == normalized_pair[1]
        )

    click.secho(
        f"Language pair: {normalized_pair[0]}:{normalized_pair[1]}",
        fg="blue",
    )
    click.echo(f"Default: {'Yes' if is_default else 'No'}")
    click.echo(f"Vocabulary file: {translations_path}")
    click.echo(f"Anki deck: {anki_path}")
    click.echo(f"Total words: {stats['total']}")
    click.echo(f"Translated: {stats['translated']}")
    click.echo(f"Pending: {stats['pending']}")

    estimate = compute_prompt_estimate(language_to_learn, mother_tongue, translations_path)
    status = estimate["status"]
    translation_model = estimate["model"]

    if status == "error":
        click.echo("Prompt tokens (input only): N/A (unable to evaluate next prompt).")
        click.echo(f"Reason: {estimate['error']}")
    elif status == "missing_file":
        click.echo("Prompt tokens (input only): N/A (vocabulary file not found)")
        click.echo(
            f"Pricing data unavailable for {translation_model}; unable to estimate monetary cost."
        )
    elif status == "no_words":
        click.echo("Prompt tokens (input only): 0")
        click.echo(
            f"Pricing data unavailable for {translation_model}; no words pending translation."
        )
    else:
        tokens_count = estimate["tokens"]
        cost_value = estimate["cost"]
        click.echo(f"Prompt tokens (input only): {tokens_count}")
        if cost_value is not None and estimate.get("price_available", False):
            click.echo(
                f"Estimated prompt cost (input tokens only, {translation_model}): ${cost_value}"
            )
        else:
            click.echo(
                f"Pricing data unavailable for {translation_model}; unable to estimate monetary cost."
            )


@vocabmaster.command()
@click.option(
    "--pair",
    type=str,
    help=(
        "Estimate tokens for a specific language pair. Specify in the format "
        "'language_to_learn:mother_tongue'."
    ),
    required=False,
)
def tokens(pair):
    """
    Estimate input-token usage for the next translation run (output tokens are not included).
    """
    try:
        language_to_learn, mother_tongue = config_handler.get_language_pair(pair)
    except Exception as error:
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo(error, err=True)
        if pair is None:
            click.echo(
                f"Run '{click.style('vocabmaster pairs add', bold=True)}' to create a language pair.",
                err=True,
            )
        sys.exit(1)
    translations_filepath, anki_file = setup_files(setup_dir(), language_to_learn, mother_tongue)

    if csv_handler.vocabulary_list_is_empty(translations_filepath):
        click.secho("The list is empty!", fg="red", err=True)
        click.echo("Please add words to the list before running this command.", err=True)
        sys.exit(0)

    estimate = compute_prompt_estimate(language_to_learn, mother_tongue, translations_filepath)

    status = estimate["status"]
    translation_model = estimate["model"]

    if status == "error":
        click.secho("Status: ", fg="blue", nl=False, err=True)
        click.echo(estimate["error"], err=True)
        click.echo("Therefore, the next prompt cannot be evaluated.", err=True)
        return

    if status == "missing_file":
        click.echo("Prompt tokens (input only): N/A (vocabulary file not found)")
        click.echo(
            f"Pricing data unavailable for {translation_model}; unable to estimate monetary cost."
        )
        return

    if status == "no_words":
        click.echo("Prompt tokens (input only): 0")
        click.echo(
            f"Pricing data unavailable for {translation_model}; no words pending translation."
        )
        return

    tokens_count = estimate["tokens"]
    cost_value = estimate["cost"]
    price_available = estimate.get("price_available", False)

    click.echo(f"Prompt tokens (input only): {click.style(str(tokens_count), fg='blue')}")
    if cost_value is not None and price_available:
        click.echo(
            "Estimated prompt cost (input tokens only, "
            f"{translation_model}): {click.style(f'${cost_value}', fg='blue')}"
        )
    else:
        click.echo(
            f"Pricing data unavailable for {translation_model}; unable to estimate monetary cost."
        )


def print_default_language_pair():
    """
    Print the current default language pair.
    """
    click.secho("The current default language pair is:", fg="blue")
    default_pair = config_handler.get_default_language_pair()
    if default_pair is None:
        click.secho("No default language pair configured yet.", fg="yellow")
        click.echo()
        return None

    click.secho(
        f"{default_pair['language_to_learn']}:{default_pair['mother_tongue']}",
        fg="yellow",
        bold=True,
    )
    click.echo()
    return default_pair


def print_all_language_pairs(empty_hint: str | None = None):
    """
    Print all the language pairs that have been set up.
    """
    click.secho("The following language pairs have been set up:", fg="blue")
    language_pairs = config_handler.get_all_language_pairs()
    if not language_pairs:
        click.secho("No language pairs found yet.", fg="yellow")
        hint = (
            empty_hint
            or f"Use {click.style('vocabmaster pairs add', bold=True)} to add a new language pair."
        )
        click.echo(hint)
        click.echo()
        return []

    for idx, language_pair in enumerate(language_pairs, start=1):
        click.echo(f"{idx}. {language_pair['language_to_learn']}:{language_pair['mother_tongue']}")
    click.echo()
    return language_pairs


def resolve_language_pair_choice(choice: str, language_pairs):
    """
    Resolve a user-provided selection (number or pair string) into a language pair tuple.

    Args:
        choice (str): Selection provided by the user.
        language_pairs (list[dict]): Available language pairs.

    Returns:
        tuple[str, str]: Normalized (language_to_learn, mother_tongue) tuple.

    Raises:
        ValueError: If the selection is invalid or the pair does not exist.
    """
    choice = choice.strip()
    if not choice:
        raise ValueError("No language pair selected.")

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(language_pairs):
            pair = language_pairs[idx]
            return pair["language_to_learn"], pair["mother_tongue"]
        raise ValueError("Invalid choice")

    try:
        language_to_learn, mother_tongue = config_handler.get_language_pair(choice)
    except ValueError as error:
        raise ValueError(str(error)) from error

    language_to_learn = language_to_learn.casefold()
    mother_tongue = mother_tongue.casefold()

    for pair in language_pairs:
        if (
            pair["language_to_learn"].casefold() == language_to_learn
            and pair["mother_tongue"].casefold() == mother_tongue
        ):
            return pair["language_to_learn"], pair["mother_tongue"]

    raise ValueError(f"The language pair {language_to_learn}:{mother_tongue} was not found.")


def get_language_pairs_or_abort(empty_hint: str, no_pairs_message: str):
    """
    Retrieve all configured language pairs or exit with an error message.
    """
    language_pairs = print_all_language_pairs(empty_hint=empty_hint)
    if not language_pairs:
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo(no_pairs_message, err=True)
        sys.exit(1)
    return language_pairs


def parse_multiple_language_pair_choices(raw_choices, language_pairs):
    """
    Parse a comma-separated list of language pair selections.

    Args:
        raw_choices (list[str]): Raw user selections.
        language_pairs (list[dict]): Available language pairs.

    Returns:
        list[tuple[str, str]]: Unique language pairs selected by the user.

    Raises:
        ValueError: When a selection is invalid or duplicates are found.
    """
    selections = []
    seen_pairs = set()

    for choice in raw_choices:
        if not choice:
            continue
        try:
            language_to_learn, mother_tongue = resolve_language_pair_choice(choice, language_pairs)
        except ValueError as error:
            raise ValueError(str(error)) from error

        pair_key = (language_to_learn.casefold(), mother_tongue.casefold())
        if pair_key not in seen_pairs:
            selections.append((language_to_learn, mother_tongue))
            seen_pairs.add(pair_key)

    return selections


def select_default_language_pair(language_pairs):
    """
    Prompt the user to select a default language pair from the provided list.
    """
    choice = click.prompt(
        "Type the language pair or its number to set it as the new default",
        type=str,
    )

    try:
        language_to_learn, mother_tongue = resolve_language_pair_choice(choice, language_pairs)
    except ValueError as error:
        message = str(error)
        click.secho("Error: ", fg="red", nl=False, err=True)
        if message == "Invalid choice":
            click.echo(message, err=True)
            click.echo(
                f"Please enter a number between 1 and {len(language_pairs)}",
                err=True,
            )
        elif "Invalid language pair." in message:
            click.echo(message, err=True)
            click.echo(
                f"The format is {click.style('language_to_learn:mother_tongue', bold=True)}",
                err=True,
            )
        else:
            click.echo(message, err=True)
        sys.exit(1)

    config_handler.set_default_language_pair(language_to_learn, mother_tongue)
    click.echo(
        f"{click.style(f'{language_to_learn}:{mother_tongue}', bold=True)} "
        f"{click.style('has been set as the default language pair', fg='green')} ✅"
    )


def compute_prompt_estimate(language_to_learn, mother_tongue, translations_path):
    """Evaluate the prompt tokens and cost for the next translation."""

    cost_model = "gpt-3.5-turbo"

    if not translations_path.exists():
        return {"status": "missing_file", "model": cost_model}

    try:
        words_to_translate = csv_handler.get_words_to_translate(translations_path)
    except Exception as error:
        message = str(error)
        if "All the words in the vocabulary list" in message:
            return {"status": "no_words", "model": cost_model}
        return {"status": "error", "model": cost_model, "error": message}

    if not words_to_translate:
        return {"status": "no_words", "model": cost_model}

    prompt = gpt_integration.format_prompt(language_to_learn, mother_tongue, words_to_translate)

    try:
        tokens_count = gpt_integration.num_tokens_from_messages(prompt)
    except NotImplementedError as error:
        return {"status": "error", "model": cost_model, "error": str(error)}

    cost_map = gpt_integration.estimate_prompt_cost(prompt)
    cost_value = None
    if isinstance(cost_map, dict):
        cost_value = cost_map.get(cost_model)

    return {
        "status": "ok",
        "model": cost_model,
        "tokens": tokens_count,
        "cost": cost_value,
        "price_available": cost_value is not None,
    }


def remove_language_pairs(language_pairs, default_hint, add_hint):
    """
    Interactive workflow to remove one or multiple language pairs.
    """
    choices_input = click.prompt(
        "Type the language pair(s) or number(s) to remove (comma-separated)",
        type=str,
    ).strip()

    raw_choices = [item.strip() for item in choices_input.split(",") if item.strip()]
    if not raw_choices:
        click.secho("Error: ", fg="red", nl=False, err=True)
        click.echo("No language pairs selected for removal.", err=True)
        sys.exit(1)

    try:
        selections = parse_multiple_language_pair_choices(raw_choices, language_pairs)
    except ValueError as error:
        message = str(error)
        click.secho("Error: ", fg="red", nl=False, err=True)
        if message == "Invalid choice":
            click.echo(message, err=True)
            click.echo(
                f"Please enter a number between 1 and {len(language_pairs)}",
                err=True,
            )
        elif "Invalid language pair." in message:
            click.echo(message, err=True)
            click.echo(
                f"The format is {click.style('language_to_learn:mother_tongue', bold=True)}",
                err=True,
            )
        else:
            click.echo(message, err=True)
        sys.exit(1)

    display_pairs = [f"{lang}:{mother}" for lang, mother in selections]
    if len(display_pairs) == 1:
        confirm_prompt = f"Remove {display_pairs[0]} from your configured language pairs?"
    else:
        confirm_prompt = (
            "Remove the following language pairs from your configuration?\n"
            + ", ".join(display_pairs)
        )

    if not click.confirm(confirm_prompt, default=False):
        click.echo("No changes made.")
        return

    removed_default = False
    for language_to_learn, mother_tongue in selections:
        try:
            removed_default = (
                config_handler.remove_language_pair(language_to_learn, mother_tongue)
                or removed_default
            )
        except ValueError as error:
            click.secho("Error: ", fg="red", nl=False, err=True)
            click.echo(error, err=True)
            sys.exit(1)

        click.echo(
            f"{click.style(f'{language_to_learn}:{mother_tongue}', bold=True)} "
            f"{click.style('has been removed', fg='green')} ✅"
        )

    remaining_pairs = config_handler.get_all_language_pairs()

    if removed_default:
        click.secho("Heads-up: the default language pair was removed.", fg="yellow")
        if remaining_pairs:
            click.secho(default_hint, fg="blue")

    if not remaining_pairs:
        click.secho("There are no language pairs configured now.", fg="yellow")
        click.secho(add_hint, fg="blue")


def print_current_storage_directory(current_dir: Path | None = None) -> Path:
    """
    Print and return the directory where CSV and Anki files are stored.

    Args:
        current_dir (pathlib.Path | None): Directory to display. If None, the configured
            storage directory is resolved before printing.

    Returns:
        pathlib.Path: The directory that was printed.
    """
    if current_dir is None:
        current_dir = config_handler.get_data_directory()
    click.secho("Current storage directory:", fg="blue")
    click.echo(current_dir)
    return current_dir


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
