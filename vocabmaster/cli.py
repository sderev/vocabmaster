import platform
import sys
from pathlib import Path

import click
import openai

from vocabmaster import config_handler, csv_handler, gpt_integration

from . import utils
from .utils import openai_api_key_exists, setup_backup_dir, setup_dir, setup_files

# CLI message prefixes (styled, user-facing)
ERROR_PREFIX = click.style("Error:", fg="red")
WARNING_PREFIX = click.style("Warning:", fg="yellow")


def validate_data_directory(path_str: str) -> Path:
    """
    Validate user-specified data directory for security.

    Args:
        path_str: User-provided directory path

    Returns:
        Validated and resolved Path object

    Raises:
        ValueError: If path is unsafe
    """
    path = Path(path_str).expanduser().resolve()

    # Disallow system directories on Unix-like systems
    if platform.system() != "Windows":
        forbidden_prefixes = [
            "/etc",
            "/bin",
            "/sbin",
            "/usr",
            "/var",
            "/sys",
            "/proc",
            "/dev",
            "/boot",
            "/root",
        ]
        for prefix in forbidden_prefixes:
            if str(path).startswith(prefix):
                raise ValueError(f"Cannot use system directory: {path}")

    # On all systems, require path to be under home directory or explicit /opt location
    home = Path.home()
    allowed_prefixes = [str(home), "/opt"]

    if not any(str(path).startswith(prefix) for prefix in allowed_prefixes):
        raise ValueError(f"Directory must be under home directory or /opt. Got: {path}")

    return path


def validate_word(word: str) -> str:
    """
    Validate word input for safety and sanity.

    Args:
        word: User-provided word or phrase

    Returns:
        Validated word

    Raises:
        ValueError: If word is invalid
    """
    word = word.strip()

    # Reject empty words
    if not word:
        raise ValueError("Word cannot be empty")

    # Limit length (prevent disk exhaustion)
    if len(word) > 500:
        raise ValueError("Word too long (maximum 500 characters)")

    # Check for null bytes (can corrupt files)
    if "\0" in word:
        raise ValueError("Word contains invalid null byte")

    # Check for dangerous newlines/carriage returns (break CSV format)
    if "\n" in word or "\r" in word:
        raise ValueError("Word cannot contain newlines")

    # Warn about CSV injection risks (formulas)
    if word.startswith(("=", "+", "-", "@")):
        click.secho(
            f"Warning: Word starts with '{word[0]}' which may be interpreted as a formula in spreadsheets.",
            fg="yellow",
            err=True,
        )
        if not click.confirm("Continue anyway?", default=False):
            raise click.Abort()

    return word


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
    Build vocabulary flashcards with AI-generated translations and examples.

    \b
    Quick start:
      vocabmaster pairs add          # Create a language pair
      vocabmaster add "to have"      # Add a word
      vocabmaster translate          # Generate Anki deck

    \b
    More info:
      https://github.com/sderev/vocabmaster
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@vocabmaster.command()
@click.option(
    "--pair",
    type=str,
    help="Language pair (e.g., english:french). Overrides default.",
    required=False,
)
@click.argument("word", type=str, nargs=-1)
def add(pair, word):
    """
    Add a word to the vocabulary list.

    \b
    Examples:
      vocabmaster add good
      vocabmaster add "to be"
      vocabmaster add --pair spanish:english hola
    """
    try:
        language_to_learn, mother_tongue = config_handler.get_language_pair(pair)
    except Exception as error:
        click.echo(f"{ERROR_PREFIX} {error}", err=True)
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

    word_str = " ".join(word)

    # Validate word for security
    try:
        validated_word = validate_word(word_str)
    except ValueError as e:
        click.echo(f"{ERROR_PREFIX} {e}", err=True)
        sys.exit(1)
    except click.Abort:
        click.echo("Word not added.")
        sys.exit(0)

    if csv_handler.word_exists(validated_word, translations_filepath):
        click.echo("That word is already in your list 📒")
    else:
        csv_handler.append_word(validated_word, translations_filepath)
        click.echo("Added to your list! 📝✅")


@vocabmaster.command()
@click.option(
    "--pair",
    type=str,
    help="Language pair (e.g., english:french). Overrides default.",
    required=False,
)
@click.option(
    "--count",
    is_flag=True,
    help="Show count of untranslated words and exit.",
    required=False,
)
@click.option(
    "--deck-name",
    type=str,
    help="Custom Anki deck name (overrides config).",
    required=False,
)
def translate(pair, count, deck_name):
    """
    Translate words and generate an Anki deck.

    Reads your vocabulary list, fetches AI-generated translations and examples,
    then creates an Anki-ready file for import.

    \b
    Examples:
      vocabmaster translate
      vocabmaster translate --count
      vocabmaster translate --pair spanish:english
    """
    try:
        language_to_learn, mother_tongue = config_handler.get_language_pair(pair)
    except Exception as error:
        click.echo(f"{ERROR_PREFIX} {error}", err=True)
        sys.exit(1)

    # Validate deck name early to avoid mutating files on validation failure
    if deck_name is not None:
        try:
            deck_name = utils.validate_deck_name(deck_name)
        except ValueError as error:
            click.echo(f"{ERROR_PREFIX} {error}", err=True)
            sys.exit(1)

    custom_deck_name = deck_name
    if custom_deck_name is None:
        try:
            custom_deck_name = config_handler.get_deck_name(language_to_learn, mother_tongue)
        except ValueError as error:
            click.echo(f"{ERROR_PREFIX} {error}", err=True)
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
    click.echo("Adding translations and examples...")
    click.secho("This may take a while...", fg="blue")
    click.echo()

    try:
        csv_handler.add_translations_and_examples_to_file(translations_filepath, pair)
        click.echo()
    except openai.error.RateLimitError as error:
        click.echo(f"{ERROR_PREFIX} {error}", err=True)
        handle_rate_limit_error()
        sys.exit(1)
    except csv_handler.AllWordsTranslatedError as error:
        click.secho("Actually...", fg="blue")
        click.secho("No action needed: ", fg="green", nl=False)
        click.echo(f"{error}")
        click.echo(
            f"If you only want to generate the Anki deck, you can run '{click.style('vocabmaster anki', bold=True)}'."
        )
        sys.exit(0)
    except Exception as error:
        click.secho("Status: ", fg="red", nl=False, err=True)
        click.echo(error, err=True)
        sys.exit(0)

    click.secho("Translations and examples added. ✅", fg="blue")

    # Generate the Anki deck
    generate_anki_deck(
        translations_filepath, anki_filepath, language_to_learn, mother_tongue, custom_deck_name
    )


def generate_anki_deck(
    translations_filepath, anki_filepath, language_to_learn, mother_tongue, custom_deck_name=None
):
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
        custom_deck_name (str, optional): Custom deck name. If None, auto-generates or uses config value.

    Returns:
        None
    """
    click.echo()
    click.echo("Generating Anki deck...")
    click.echo()
    csv_handler.generate_anki_output_file(
        translations_filepath, anki_filepath, language_to_learn, mother_tongue, custom_deck_name
    )
    click.echo("Anki deck generated. ✅")
    click.echo()
    click.secho("You can now import the deck into Anki.", fg="green")

    click.secho("The deck is located at:", bold=True)
    click.echo(f"{anki_filepath}")


@vocabmaster.command()
@click.option(
    "--pair",
    type=str,
    help="Language pair (e.g., english:french). Overrides default.",
    required=False,
)
@click.option(
    "--deck-name",
    type=str,
    help="Custom Anki deck name (overrides config).",
    required=False,
)
def anki(pair, deck_name):
    """
    Generate an Anki deck from existing translations.

    Unlike `translate`, this does not fetch new translations. Use this to
    regenerate the Anki file after editing the vocabulary CSV manually.

    \b
    Examples:
      vocabmaster anki
      vocabmaster anki --deck-name "My Vocabulary"
    """
    try:
        language_to_learn, mother_tongue = config_handler.get_language_pair(pair)
    except Exception as error:
        click.echo(f"{ERROR_PREFIX} {error}", err=True)
        if pair is None:
            click.echo(
                f"Hint: Run '{click.style('vocabmaster pairs add', bold=True)}' to create a language pair.",
                err=True,
            )
        sys.exit(1)

    # Determine custom deck name: CLI option > config > None (auto-generate)
    custom_deck_name = deck_name
    if custom_deck_name is not None:
        try:
            custom_deck_name = utils.validate_deck_name(custom_deck_name)
        except ValueError as error:
            click.echo(f"{ERROR_PREFIX} {error}", err=True)
            sys.exit(1)

    if custom_deck_name is None:
        try:
            custom_deck_name = config_handler.get_deck_name(language_to_learn, mother_tongue)
        except ValueError as error:
            click.echo(f"{ERROR_PREFIX} {error}", err=True)
            sys.exit(1)

    translations_filepath, anki_filepath = setup_files(
        setup_dir(), language_to_learn, mother_tongue
    )

    generate_anki_deck(
        translations_filepath, anki_filepath, language_to_learn, mother_tongue, custom_deck_name
    )


def create_language_pair_interactively():
    """
    Interactive workflow used by the `pairs add` command.
    """
    language_to_learn = click.prompt("Please enter the language you want to learn")
    mother_tongue = click.prompt("Please enter your mother tongue")

    # Validate language names early to prevent path traversal
    try:
        language_to_learn = utils.validate_language_name(language_to_learn)
        mother_tongue = utils.validate_language_name(mother_tongue)
    except ValueError as error:
        click.echo(f"{ERROR_PREFIX} {error}", err=True)
        sys.exit(1)

    click.echo()
    click.echo(
        f"Setting up VocabMaster for learning {click.style(language_to_learn.capitalize(), bold=True)}, "
        f"and {click.style(mother_tongue.capitalize(), bold=True)} is your mother tongue."
    )

    if click.confirm("Do you want to proceed?"):
        # Create the necessary folders and files
        app_data_dir = setup_dir()

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
        click.echo(f"Language pair {language_to_learn}:{mother_tongue} ready. ✅")
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
        click.secho("Creation canceled.", fg="red", err=True)


@vocabmaster.group(invoke_without_command=True)
@click.pass_context
def config(ctx):
    """
    Manage storage location and API key settings.

    \b
    Subcommands:
      dir    Set data directory for vocabulary and Anki files
      key    Check OpenAI API key status
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@config.command("dir")
@click.option(
    "--show",
    "show_only",
    is_flag=True,
    help="Display current directory and exit.",
)
@click.argument("directory", required=False)
def config_dir(show_only, directory):
    """
    Set the data directory for vocabulary and Anki files.

    \b
    Examples:
      vocabmaster config dir --show
      vocabmaster config dir ~/vocabmaster-data
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

    # Validate directory for security
    try:
        target_path = validate_data_directory(directory_input)
    except ValueError as e:
        click.echo(f"{ERROR_PREFIX} {e}", err=True)
        sys.exit(1)

    if target_path.exists() and not target_path.is_dir():
        click.echo(f"{ERROR_PREFIX} {target_path} exists and is not a directory.", err=True)
        sys.exit(1)

    try:
        target_path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        click.echo(f"{ERROR_PREFIX} Unable to use '{target_path}': {error}", err=True)
        sys.exit(1)

    config_handler.set_data_directory(target_path)
    click.secho("Storage updated!", fg="green")
    click.echo(f"Vocabulary CSV and Anki decks will now be stored in {target_path}")
    click.echo(f"You can also edit {config_handler.get_config_filepath()} directly.")


@config.command("key")
def config_key():
    """
    Check if the OpenAI API key is configured.

    The key must be set via the OPENAI_API_KEY environment variable.
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
    click.echo(f"{ERROR_PREFIX} OpenAI API key not found.", err=True)
    click.echo(err=True)
    click.echo(
        "You can generate API keys in the OpenAI web interface. See"
        " https://platform.openai.com/account/api-keys for details.",
        err=True,
    )
    click.echo(err=True)
    if platform.system() == "Windows":
        click.echo(
            "Hint: Set the key by running `setx OPENAI_API_KEY your_key`.",
            err=True,
        )
    else:
        click.echo(
            "Hint: Set the key by running `export OPENAI_API_KEY=YOUR_KEY`.",
            err=True,
        )
    return


@vocabmaster.group("pairs", invoke_without_command=True)
@click.pass_context
def pairs(ctx):
    """
    Manage language pairs.

    \b
    Subcommands:
      list           List all language pairs
      add            Create a new language pair
      remove         Remove language pairs
      rename         Rename a language pair
      default        Show current default pair
      set-default    Change default pair
      set-deck-name  Set custom Anki deck name
      inspect        Show pair details and stats
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@pairs.command("list")
def pairs_list():
    """List all configured language pairs."""
    print_all_language_pairs(
        f"Use {click.style('vocabmaster pairs add', bold=True)} to add a new language pair."
    )


@pairs.command("add")
def pairs_add():
    """Create a new language pair interactively."""
    create_language_pair_interactively()


@pairs.command("default")
def pairs_default_command():
    """Show the current default language pair."""
    print_default_language_pair()
    click.secho("You can change the default language pair at any time by running:", fg="blue")
    click.secho("vocabmaster pairs set-default", bold=True)


@pairs.command("set-default")
def pairs_set_default_command():
    """Set the default language pair interactively."""
    language_pairs = get_language_pairs_or_abort(
        f"Use {click.style('vocabmaster pairs add', bold=True)} to add a new language pair.",
        "No language pairs found. Run 'vocabmaster pairs add' to add one before setting a default.",
    )
    select_default_language_pair(language_pairs)


@pairs.command("remove")
def pairs_remove_command():
    """Remove one or more language pairs interactively."""
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
    """Rename an existing language pair interactively."""
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
        click.echo(f"{ERROR_PREFIX} {message}", err=True)
        if message == "Invalid choice":
            click.echo(
                f"Hint: Enter a number between 1 and {len(language_pairs)}.",
                err=True,
            )
        elif "Invalid language pair." in message:
            click.echo(
                f"Hint: Format is {click.style('language_to_learn:mother_tongue', bold=True)}.",
                err=True,
            )
        sys.exit(1)

    new_pair_input = click.prompt(
        "Enter the new language pair (language_to_learn:mother_tongue)",
        type=str,
    ).strip()

    if not new_pair_input:
        click.echo(f"{ERROR_PREFIX} New language pair cannot be empty.", err=True)
        sys.exit(1)

    try:
        new_language, new_mother_tongue = config_handler.get_language_pair(new_pair_input)
        # Validate the new names to prevent path traversal
        new_language = utils.validate_language_name(new_language)
        new_mother_tongue = utils.validate_language_name(new_mother_tongue)
    except ValueError as error:
        click.echo(f"{ERROR_PREFIX} {error}", err=True)
        if "Invalid language pair" in str(error):
            click.echo(
                f"Hint: Format is {click.style('language_to_learn:mother_tongue', bold=True)}.",
                err=True,
            )
        sys.exit(1)

    old_key = (old_language.casefold(), old_mother_tongue.casefold())
    new_key = (new_language, new_mother_tongue)

    if old_key == new_key:
        click.echo(
            f"{ERROR_PREFIX} New language pair must be different from the current one.", err=True
        )
        sys.exit(1)

    existing_pairs = config_handler.get_all_language_pairs()
    if any(
        pair["language_to_learn"].casefold() == new_key[0]
        and pair["mother_tongue"].casefold() == new_key[1]
        for pair in existing_pairs
    ):
        click.echo(
            f"{ERROR_PREFIX} The language pair {new_key[0]}:{new_key[1]} already exists. Choose another name.",
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


@pairs.command("set-deck-name")
@click.option(
    "--pair",
    type=str,
    help="Language pair (e.g., english:french). Omit to select interactively.",
    required=False,
)
@click.option(
    "--name",
    type=str,
    help="Deck name to set. Omit to be prompted.",
    required=False,
)
@click.option(
    "--remove",
    is_flag=True,
    help="Remove custom name (revert to auto-generated).",
)
def pairs_set_deck_name_command(pair, name, remove):
    """
    Set or remove a custom Anki deck name for a language pair.

    \b
    Examples:
      vocabmaster pairs set-deck-name
      vocabmaster pairs set-deck-name --pair english:french --name "My Vocab"
      vocabmaster pairs set-deck-name --remove
    """
    # Get language pair (either from option or by prompting)
    if pair:
        try:
            language_to_learn, mother_tongue = config_handler.get_language_pair(pair)
        except ValueError as error:
            click.echo(f"{ERROR_PREFIX} {error}", err=True)
            sys.exit(1)
    else:
        language_pairs = get_language_pairs_or_abort(
            f"Use {click.style('vocabmaster pairs add', bold=True)} to add a new language pair.",
            "No language pairs found. Run 'vocabmaster pairs add' to add one before setting a deck name.",
        )

        choice = click.prompt(
            "Type the language pair or its number to configure",
            type=str,
        )

        try:
            language_to_learn, mother_tongue = resolve_language_pair_choice(choice, language_pairs)
        except ValueError as error:
            message = str(error)
            click.echo(f"{ERROR_PREFIX} {message}", err=True)
            if message == "Invalid choice":
                click.echo(
                    f"Hint: Enter a number between 1 and {len(language_pairs)}.",
                    err=True,
                )
            elif "Invalid language pair." in message:
                click.echo(
                    f"Hint: Format is {click.style('language_to_learn:mother_tongue', bold=True)}.",
                    err=True,
                )
            sys.exit(1)

    # Validate that pair exists in config (especially important for --remove)
    all_pairs = config_handler.get_all_language_pairs()
    pair_exists = any(
        pair.get("language_to_learn", "").casefold() == language_to_learn
        and pair.get("mother_tongue", "").casefold() == mother_tongue
        for pair in all_pairs
    )
    if not pair_exists:
        click.echo(
            f"{ERROR_PREFIX} Language pair {language_to_learn}:{mother_tongue} not found.", err=True
        )
        click.echo(
            f"Hint: Run '{click.style('vocabmaster pairs list', bold=True)}' to see configured pairs.",
            err=True,
        )
        sys.exit(1)

    # Show current deck name if any (warn if stored value is invalid)
    current_name = None
    current_name_error = None
    try:
        current_name = config_handler.get_deck_name(language_to_learn, mother_tongue)
    except ValueError as error:
        current_name_error = str(error)

    if current_name_error:
        click.echo(f"{WARNING_PREFIX} {current_name_error}", err=True)
        click.echo("Stored deck name is invalid. You can remove it or set a new name.", err=True)
    elif current_name:
        click.echo(f"Current custom deck name: {click.style(current_name, bold=True)}")
    else:
        mode = utils.get_pair_mode(language_to_learn, mother_tongue)
        auto_name = (
            f"{language_to_learn.capitalize()} definitions"
            if mode == "definition"
            else f"{language_to_learn.capitalize()} vocabulary"
        )
        click.echo(f"Currently using auto-generated name: {click.style(auto_name, dim=True)}")

    # Handle removal
    if remove:
        if not current_name and not current_name_error:
            click.echo("No custom deck name set. Nothing to remove.")
            return

        if click.confirm(
            f"Remove custom deck name for {language_to_learn}:{mother_tongue}?", default=False
        ):
            config_handler.remove_deck_name(language_to_learn, mother_tongue)
            click.secho(
                f"✓ Custom deck name removed for {language_to_learn}:{mother_tongue}", fg="green"
            )
            click.echo("Deck names will now be auto-generated.")
        else:
            click.echo("No changes made.")
        return

    # Get deck name (either from option or by prompting)
    if name is None:
        name = click.prompt(
            "Enter custom deck name (leave blank to cancel)",
            type=str,
            default="",
        ).strip()

        if not name:
            click.echo("No changes made.")
            return

    # Validate and set deck name
    try:
        # Validate to get normalized name (stripped, etc.) for accurate confirmation
        normalized_name = utils.validate_deck_name(name)
        config_handler.set_deck_name(language_to_learn, mother_tongue, normalized_name)
        click.secho(
            f"✓ Custom deck name set for {language_to_learn}:{mother_tongue}: {normalized_name}",
            fg="green",
        )
        click.echo(f"Future Anki decks will use: {click.style(normalized_name, bold=True)}")
    except ValueError as error:
        click.echo(f"{ERROR_PREFIX} {error}", err=True)
        sys.exit(1)


@pairs.command("inspect")
@click.option(
    "--pair",
    type=str,
    help="Language pair (e.g., english:french). Defaults to current default.",
    required=False,
)
def pairs_inspect_command(pair):
    """
    Show details and stats for a language pair.

    Displays vocabulary file location, word counts, and cost estimates.
    """
    if pair is None:
        default_pair = config_handler.get_default_language_pair()
        if default_pair is None:
            click.echo(
                f"{ERROR_PREFIX} No default language pair found. Run 'vocabmaster pairs add' to create one.",
                err=True,
            )
            sys.exit(1)
        language_to_learn = default_pair["language_to_learn"]
        mother_tongue = default_pair["mother_tongue"]
    else:
        try:
            language_to_learn, mother_tongue = config_handler.get_language_pair(pair)
        except ValueError:
            click.echo(f"{ERROR_PREFIX} Invalid language pair format.", err=True)
            click.echo(
                f"Hint: Format is {click.style('language_to_learn:mother_tongue', bold=True)}.",
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
        click.echo(f"{ERROR_PREFIX} The language pair {provided} was not found.", err=True)
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
        click.echo("Number of tokens in the prompt: N/A (unable to evaluate next prompt).")
        click.echo(f"Reason: {estimate['error']}")
    elif status == "missing_file":
        click.echo("Number of tokens in the prompt: N/A (vocabulary file not found)")
        click.echo(
            f"Pricing data unavailable for {translation_model}; unable to estimate monetary cost."
        )
    elif status == "no_words":
        click.echo("Number of tokens in the prompt: 0")
        click.echo(
            f"Pricing data unavailable for {translation_model}; no words pending translation."
        )
    else:
        tokens_count = estimate["tokens"]
        cost_value = estimate["cost"]
        click.echo(
            f"Number of tokens in the prompt: {click.style(str(tokens_count), fg='yellow')}."
        )
        if cost_value is not None and estimate.get("price_available", False):
            click.echo(
                f"Cost estimate for {click.style(translation_model, fg='blue')} model:"
                f" {click.style(f'${cost_value}', fg='yellow')} (input tokens only)."
            )
        else:
            click.echo(
                f"Pricing data unavailable for {translation_model}; unable to estimate monetary cost."
            )


@vocabmaster.command()
@click.option(
    "--pair",
    type=str,
    help="Language pair (e.g., english:french). Overrides default.",
    required=False,
)
def tokens(pair):
    """
    Estimate input token usage and cost for the next translation.

    Calculates the prompt size for pending words. Output tokens are not included.

    \b
    Examples:
      vocabmaster tokens
      vocabmaster tokens --pair spanish:english
    """
    try:
        language_to_learn, mother_tongue = config_handler.get_language_pair(pair)
    except Exception as error:
        click.echo(f"{ERROR_PREFIX} {error}", err=True)
        if pair is None:
            click.echo(
                f"Hint: Run '{click.style('vocabmaster pairs add', bold=True)}' to create a language pair.",
                err=True,
            )
        sys.exit(1)
    translations_filepath, anki_file = setup_files(setup_dir(), language_to_learn, mother_tongue)

    if csv_handler.vocabulary_list_is_empty(translations_filepath):
        click.echo(f"{ERROR_PREFIX} The list is empty!", err=True)
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

    click.echo(f"Number of tokens in the prompt: {click.style(str(tokens_count), fg='yellow')}.")
    if cost_value is not None and price_available:
        click.echo(
            f"Cost estimate for {click.style(translation_model, fg='blue')} model:"
            f" {click.style(f'${cost_value}', fg='yellow')} (input tokens only)."
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
        click.secho("No default language pair configured yet.", fg="yellow", err=True)
        click.echo(err=True)
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
        click.secho("No language pairs found yet.", fg="yellow", err=True)
        hint = (
            empty_hint
            or f"Use {click.style('vocabmaster pairs add', bold=True)} to add a new language pair."
        )
        click.echo(hint, err=True)
        click.echo(err=True)
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
        click.echo(f"{ERROR_PREFIX} {no_pairs_message}", err=True)
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
        click.echo(f"{ERROR_PREFIX} {message}", err=True)
        if message == "Invalid choice":
            click.echo(
                f"Hint: Enter a number between 1 and {len(language_pairs)}.",
                err=True,
            )
        elif "Invalid language pair." in message:
            click.echo(
                f"Hint: Format is {click.style('language_to_learn:mother_tongue', bold=True)}.",
                err=True,
            )
        sys.exit(1)

    config_handler.set_default_language_pair(language_to_learn, mother_tongue)
    click.echo(
        f"{click.style(f'{language_to_learn}:{mother_tongue}', bold=True)} "
        f"{click.style('has been set as the default language pair', fg='green')} ✅"
    )


def compute_prompt_estimate(language_to_learn, mother_tongue, translations_path):
    """Evaluate the prompt tokens and cost for the next translation."""

    translation_model = "gpt-4.1"

    if not translations_path.exists():
        return {"status": "missing_file", "model": translation_model}

    try:
        words_to_translate = csv_handler.get_words_to_translate(translations_path)
    except Exception as error:
        message = str(error)
        if "All the words in the vocabulary list" in message:
            return {"status": "no_words", "model": translation_model}
        return {"status": "error", "model": translation_model, "error": message}

    if not words_to_translate:
        return {"status": "no_words", "model": translation_model}

    # Determine the mode based on whether languages match
    mode = utils.get_pair_mode(language_to_learn, mother_tongue)
    prompt = gpt_integration.format_prompt(
        language_to_learn, mother_tongue, words_to_translate, mode
    )

    tokens_count = gpt_integration.num_tokens_from_messages(prompt, translation_model)
    cost_value = gpt_integration.estimate_prompt_cost(prompt, translation_model)

    return {
        "status": "ok",
        "model": translation_model,
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
        click.echo(f"{ERROR_PREFIX} No language pairs selected for removal.", err=True)
        sys.exit(1)

    try:
        selections = parse_multiple_language_pair_choices(raw_choices, language_pairs)
    except ValueError as error:
        message = str(error)
        click.echo(f"{ERROR_PREFIX} {message}", err=True)
        if message == "Invalid choice":
            click.echo(
                f"Hint: Enter a number between 1 and {len(language_pairs)}.",
                err=True,
            )
        elif "Invalid language pair." in message:
            click.echo(
                f"Hint: Format is {click.style('language_to_learn:mother_tongue', bold=True)}.",
                err=True,
            )
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
            click.echo(f"{ERROR_PREFIX} {error}", err=True)
            sys.exit(1)

        click.echo(
            f"{click.style(f'{language_to_learn}:{mother_tongue}', bold=True)} "
            f"{click.style('has been removed', fg='green')} ✅"
        )

    remaining_pairs = config_handler.get_all_language_pairs()

    if removed_default:
        click.echo(f"{WARNING_PREFIX} The default language pair was removed.", err=True)
        if remaining_pairs:
            click.echo(f"Hint: {default_hint}", err=True)

    if not remaining_pairs:
        click.echo(f"{WARNING_PREFIX} There are no language pairs configured now.", err=True)
        click.echo(f"Hint: {add_hint}", err=True)


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
