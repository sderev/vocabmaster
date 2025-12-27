import csv
import os
import stat
import tempfile
from csv import DictReader, DictWriter
from pathlib import Path

import click

from vocabmaster import gpt_integration, utils

CSV_FIELDNAMES = ["word", "translation", "example"]

# CLI message prefixes (styled, user-facing)
ERROR_PREFIX = click.style("Error:", fg="red")
WARNING_PREFIX = click.style("Warning:", fg="yellow")
ALL_WORDS_TRANSLATED_MESSAGE = (
    "All the words in the vocabulary list already have translations and examples"
)


class ValidationError(RuntimeError):
    """Raised when vocabulary entries fail validation before write."""


def atomic_write_csv(filepath, write_function):
    """
    Write CSV atomically using temp-then-rename pattern.

    Creates a temporary file in the same directory as the target, writes content
    via the provided callback, then atomically replaces the target file. This
    ensures the file is never left in a corrupted state if the process is killed
    during write.

    Args:
        filepath: Path to the target CSV file (str or Path)
        write_function: Callable that receives the open file handle and writes content
    """
    filepath = Path(filepath)
    existing_mode = None
    if filepath.exists():
        existing_mode = stat.S_IMODE(filepath.stat().st_mode)
    temp_fd, temp_path = tempfile.mkstemp(
        dir=filepath.parent, prefix=".csv_", suffix=".tmp", text=True
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8", newline="") as file:
            write_function(file)
        # Apply permissions after writing (not before) to avoid write failure
        # when the original file is read-only
        if existing_mode is not None:
            os.chmod(temp_path, existing_mode)
        os.replace(temp_path, str(filepath))
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def validate_entries_before_write(entries):
    """
    Validate that entries are safe to write to the vocabulary file.

    Checks that the data structure is valid and contains at least one entry
    to prevent writing empty or corrupted data.

    Args:
        entries (dict): Dictionary of word entries to validate.

    Returns:
        dict: Validation result with keys:
            - valid (bool): True if safe to write
            - entry_count (int): Number of entries
            - error (str | None): Error message if invalid
    """
    if entries is None:
        return {"valid": False, "entry_count": 0, "error": "Entries dictionary is None"}

    if not isinstance(entries, dict):
        return {"valid": False, "entry_count": 0, "error": "Entries must be a dictionary"}

    entry_count = len(entries)

    if entry_count == 0:
        return {"valid": False, "entry_count": 0, "error": "No entries to write"}

    # Validate each entry has required structure
    for word, entry in entries.items():
        if not isinstance(entry, dict):
            return {
                "valid": False,
                "entry_count": entry_count,
                "error": f"Entry for '{word}' is not a dictionary",
            }

        # Check for required keys
        required_keys = {"word", "translation", "example"}
        missing_keys = required_keys - set(entry.keys())
        if missing_keys:
            return {
                "valid": False,
                "entry_count": entry_count,
                "error": f"Entry for '{word}' missing keys: {', '.join(sorted(missing_keys))}",
            }

    return {"valid": True, "entry_count": entry_count, "error": None}


def sanitize_csv_value(value: str) -> str:
    """
    Sanitize value for safe CSV storage.

    Prevents CSV injection by prefixing dangerous characters with single quote.
    Only sanitizes hyphen when it appears formula-like (e.g., "-123", "-=SUM")
    or contains DDE injection patterns.

    Args:
        value: Value to sanitize

    Returns:
        Sanitized value safe for CSV
    """
    if not value:
        return value

    first_char = value[0]

    # Always sanitize these formula starters
    if first_char in ("=", "+", "@", "\t", "\r", "\n"):
        return "'" + value

    # For hyphen, sanitize if:
    # 1. Followed by digit or formula char (e.g., "-123", "-=SUM"), OR
    # 2. Contains any digit (potential cell reference like "-A1", "-A1+1"), OR
    # 3. Contains DDE injection patterns (pipe or exclamation mark), OR
    # 4. Contains function call pattern (parenthesis indicates formula like -SUM())
    # This preserves legitimate vocabulary like "-ism" while blocking formulas
    if first_char == "-":
        if len(value) > 1:
            second_char = value[1]
            if second_char.isdigit() or second_char in ("=", "+", "-", "@"):
                return "'" + value
        # Block potential cell references (contain digits like -A1, -AB123)
        if any(c.isdigit() for c in value[1:]):
            return "'" + value
        # Block DDE injection and function-like patterns
        if "|" in value or "!" in value or "(" in value:
            return "'" + value

    return value


def _is_missing_or_blank(value):
    """
    Check if a value is None, empty string, or contains only whitespace.

    Args:
        value: The value to check (typically a string or None)

    Returns:
        bool: True if value is None, empty, or whitespace-only; False otherwise
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


class AllWordsTranslatedError(Exception):
    """Raised when the vocabulary file has no pending translations."""

    def __init__(self, message=ALL_WORDS_TRANSLATED_MESSAGE):
        super().__init__(message)


def detect_word_mismatches(original_words, gpt_response):
    """
    Detect words that don't match between original words and LM response.

    A mismatch occurs when the LM reports a different "recognized" spelling for a given
    original word, or when a response is entirely missing for one of the requested words.

    Args:
        original_words (list): List of original words sent to the LM.
        gpt_response (dict): Dictionary keyed by original words with LM metadata.

    Returns:
        tuple: (mismatches, missing_words) where:
            - mismatches: List of tuples (original_word, [possible_corrections])
            - missing_words: List of words that LM failed to return
    """
    mismatches = []
    missing_words = []

    # Convert to set for O(1) lookup performance (optimization for large vocabularies)
    original_words_set = set(original_words)

    for original_word in original_words:
        entry = gpt_response.get(original_word)

        if not entry:
            # Word might be missing, or might be a typo correction in legacy format
            # Check if any other entries could be corrections for this word
            possible_corrections = []
            for key, data in gpt_response.items():
                if isinstance(data, dict) and data.get("recognized_word"):
                    # In legacy 3-column format, key == recognized_word
                    # If key != original_word, this could be a typo correction
                    if key != original_word and key not in original_words_set:
                        possible_corrections.append(key)

            if possible_corrections:
                # Offer these as potential corrections (legacy format compatibility)
                mismatches.append((original_word, sorted(possible_corrections)))
            else:
                # Word is completely missing from LM response
                missing_words.append(original_word)
            continue

        recognized_word = entry.get("recognized_word")
        if _is_missing_or_blank(recognized_word):
            # LM didn't provide a valid recognized_word (empty, whitespace, or None)
            # Treat as missing rather than offering unrelated corrections
            missing_words.append(original_word)
        elif recognized_word != original_word:
            # LM corrected the spelling
            mismatches.append((original_word, [recognized_word]))

    return mismatches, missing_words


def ask_user_about_correction(original_word, corrected_word):
    """
    Ask user if they want to replace the original word with the LM's correction.

    Args:
        original_word (str): The original word with potential typo
        corrected_word (str): The LM's suggested correction

    Returns:
        bool: True if user wants to replace, False otherwise
    """
    message = f"The LM returned '{corrected_word}' instead of '{original_word}'. Replace the original word?"
    return click.confirm(message)


def update_word_in_entries(current_entries, old_word, new_word):
    """
    Update a word key in the entries dictionary.

    Args:
        current_entries (dict): Dictionary of CSV entries with word as key
        old_word (str): The old word key to replace
        new_word (str): The new word key

    Returns:
        dict: Updated entries dictionary
    """
    if old_word in current_entries:
        # Move the entry to the new key
        current_entries[new_word] = current_entries[old_word]
        # Update the internal "word" field to match the new key
        current_entries[new_word]["word"] = new_word
        del current_entries[old_word]

    return current_entries


def word_exists(word, translations_path):
    """
    Checks if the word is already present in the `translations_path`.

    Args:
        word (str): The word to check for its presence in the file.
        translations_filepath (str): The path to the file containing the list of words.

    Returns:
        bool: True if the word is found in the file, False otherwise.
    """
    with open(translations_path, encoding="UTF-8") as file:
        dict_reader = DictReader(file, fieldnames=CSV_FIELDNAMES)
        for row in dict_reader:
            if word == row["word"]:
                return True
        return False


def append_word(word, translations_filepath):
    """
    Appends the word to the translations file with empty translation and example fields.

    Args:
        word (str): The word to be appended to the file.
        translations_filepath (str): The path to the file containing the list of words.
    """
    # Sanitize word before appending to prevent CSV injection
    safe_word = sanitize_csv_value(word)

    with open(translations_filepath, "a", encoding="UTF-8") as file:
        dict_writer = DictWriter(file, fieldnames=CSV_FIELDNAMES)
        dict_writer.writerow({"word": safe_word, "translation": "", "example": ""})


def get_words_to_translate(translations_path):
    """
    Reads a CSV file containing words, translations, and examples, and returns a list of words that need translations.

    The input CSV file should have the following columns: 'word', 'translation', and 'example'.
    If a row is missing either the 'translation' or 'example' column, the 'word' from that row will be added to the list.

    Args:
        translations_path (pathlib.Path | str): The path to the input CSV file containing words, translations, and examples.

    Returns:
        list: A list of words that need translations.
    """
    # Ensure the file has the correct fieldnames before reading
    ensure_csv_has_fieldnames(translations_path)

    words_to_translate = []

    with open(translations_path, encoding="UTF-8") as translations_file:
        dict_reader = DictReader(translations_file)
        # fieldnames = ["word", "translation", "example"]

        for row in dict_reader:
            # If a row is missing a translation or example, add the word to the list of words to translate
            if not row["translation"] or not row["example"]:
                words_to_translate.append(row["word"])

    if not words_to_translate:
        raise AllWordsTranslatedError()
    else:
        return words_to_translate


def generate_translations_and_examples(language_to_learn, mother_tongue, translations_path):
    """
    Generates translations and examples for a list of words using the LM.

    This function calls `get_words_to_translate` to obtain a list of words that need translations,
    using the provided `translations_path`. It then formats the prompt using
    `gpt_integration.format_prompt` and sends a request to the LM. The generated text from
    the LM is returned.

    Args:
        language_to_learn (str): The language to learn.
        mother_tongue (str): The user's mother tongue.
        translations_path (str): The path to the input CSV file containing words,
                                       translations, and examples.

    Returns:
        str: The generated text containing translations and examples.
    """
    # Get the list of words that need translations and generate the LM prompt
    words_to_translate = get_words_to_translate(translations_path)

    # Determine the mode based on whether languages match
    mode = utils.get_pair_mode(language_to_learn, mother_tongue)
    prompt = gpt_integration.format_prompt(
        language_to_learn, mother_tongue, words_to_translate, mode
    )

    # Send a request to the LM and extract the generated text
    gpt_response = gpt_integration.chatgpt_request(prompt=prompt, stream=True, temperature=0.6)
    generated_text = gpt_response[0]

    # Create a backup of the LM response
    backup_dir = utils.get_backup_dir(language_to_learn, mother_tongue)
    utils.backup_content(backup_dir, generated_text)

    return generated_text


def convert_text_to_dict(generated_text):
    """
    Clean and convert the given TSV text into a dictionary.

    Expected format per line:
        original_word\trecognized_word\ttranslation_or_definition\texample

    The "recognized_word" column allows the LM to report spelling corrections. The function
    returns a dictionary keyed by the original words supplied by the user, preserving both the
    LM's recognized spelling and the generated content.

    Args:
        generated_text (str): The text to be cleaned and converted.

    Returns:
        dict: A dictionary keyed by original words with translation data.
    """
    # Clean input text and split it into lines
    cleaned_text = generated_text.replace("\\n\\n", "\\n").replace("```csv", "").replace("```", "")
    lines = cleaned_text.strip().splitlines()

    def _strip_wrapping(value: str, quote_char: str) -> str:
        """Remove matching wrapping quote characters while preserving inner content."""
        if value.startswith(quote_char) and value.endswith(quote_char) and len(value) >= 2:
            return value[1:-1]
        return value

    result = {}
    failed_entries = []

    def _record_failure(line_number: int, columns: list[str]) -> str:
        word_candidate = columns[0].strip() if columns and columns[0].strip() else "unknown"
        failed_entries.append((line_number, word_candidate))
        return word_candidate

    for line_number, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue

        # Split and detect potential tab corruption
        columns = line.split("\t")
        if len(columns) > 4:
            word_candidate = _record_failure(line_number, columns)
            # Likely has tabs within content - warn and skip to prevent data corruption
            click.echo(
                (
                    f"{WARNING_PREFIX} Line {line_number}: Line appears corrupted "
                    f"(tabs in content?) for word '{word_candidate}'"
                ),
                err=True,
            )
            click.echo(line, err=True)
            click.echo(
                "Skipping line to prevent data corruption. Consider removing tabs from content.",
                err=True,
            )
            continue

        # Handle both 3-column (legacy) and 4-column (new) formats
        if len(columns) == 3:
            # Legacy format: word\ttranslation\texample
            word, translation_quoted, example_quoted = columns
            original_word = word
            recognized_word = word  # Default to same spelling for legacy format
        elif len(columns) >= 4:
            # New format: original_word\trecognized_word\ttranslation\texample
            original_word, recognized_word, translation_quoted, example_quoted = columns[:4]
        else:
            # Neither 3 nor 4+ columns - cannot parse
            word_candidate = _record_failure(line_number, columns)
            click.echo(
                (
                    f"{WARNING_PREFIX} Line {line_number}: Could not parse word "
                    f"'{word_candidate}' (expected 3-4 columns, got {len(columns)})"
                ),
                err=True,
            )
            click.echo(line, err=True)
            continue

        translation = _strip_wrapping(translation_quoted, "'")
        example = _strip_wrapping(example_quoted, '"')

        result[original_word] = {
            "recognized_word": recognized_word,
            "translation": translation,
            "example": example,
        }

    if failed_entries:
        click.echo(
            (
                f"{WARNING_PREFIX} Failed to parse {len(failed_entries)} line(s). "
                "The following words may need review:"
            ),
            err=True,
        )
        for line_number, word_candidate in failed_entries:
            click.echo(f"  Line {line_number}: '{word_candidate}'", err=True)

    return result


def add_translations_and_examples_to_file(translations_path, pair):
    """
    Updates the translations file with new translations and examples.

    This function reads a CSV file with words that need translation and their existing translations and examples.
    It generates new translations and examples using the `generate_translations_and_examples` function and updates
    the CSV file with the new translations and examples.

    Args:
        translations_path (str): The path to the CSV file containing the translations and examples.
    Returns:
        pair (str): The language pair in the format: 'language_to_learn:mother_tongue'.

        None
    """
    # Generate new translations and examples, then convert the results to a dictionary
    language_to_learn, mother_tongue = utils.get_language_pair_from_option(pair)
    translations_path = Path(translations_path)
    backup_dir = utils.get_backup_dir(language_to_learn, mother_tongue)

    # Preserve the current vocabulary file before making external requests.
    utils.backup_file(backup_dir, translations_path)

    # Get the original words that were sent to the LM for mismatch detection
    original_words = get_words_to_translate(translations_path)

    new_entries = convert_text_to_dict(
        generate_translations_and_examples(language_to_learn, mother_tongue, translations_path)
    )

    # Read the current entries from the input file and store them in a dictionary
    with open(translations_path, "r", encoding="UTF-8") as input_file:
        translations_reader = DictReader(input_file)
        current_entries = {row["word"]: row for row in translations_reader}

    skip_translation_for = set()

    def _entry_for_correction(original_word, corrected_word):
        """Return LM data for a correction suggestion."""
        entry = new_entries.get(original_word)
        if entry and entry.get("recognized_word") == corrected_word:
            return entry

        for data in new_entries.values():
            if data.get("recognized_word") == corrected_word:
                return data

        return entry

    # Detect and handle word mismatches (e.g., typo corrections by the LM)
    mismatches, missing_words = detect_word_mismatches(original_words, new_entries)

    # Report missing words
    if missing_words:
        click.echo(
            f"\n{ERROR_PREFIX} LM failed to return translations for {len(missing_words)} word(s):",
            err=True,
        )
        for word in missing_words:
            click.echo(f"  - {word}", err=True)
        click.echo("Please retry or add them manually.\n", err=True)

    if mismatches:
        click.echo(f"\n{WARNING_PREFIX} Word corrections detected:", err=True)

        for original_word, potential_corrections in mismatches:
            if len(potential_corrections) == 1:
                corrected_word = potential_corrections[0]
                if ask_user_about_correction(original_word, corrected_word):
                    current_entries = update_word_in_entries(
                        current_entries, original_word, corrected_word
                    )
                    # Apply the translation and example immediately
                    entry_data = _entry_for_correction(original_word, corrected_word)
                    if entry_data:
                        current_entries[corrected_word]["translation"] = sanitize_csv_value(
                            entry_data["translation"]
                        )
                        current_entries[corrected_word]["example"] = sanitize_csv_value(
                            entry_data["example"]
                        )
                    click.echo(f"Updated '{original_word}' → '{corrected_word}' ✓")
                else:
                    click.echo(f"Kept original word '{original_word}'")
                    skip_translation_for.add(original_word)
            else:
                # Multiple possible corrections (rare case)
                click.echo(f"\nMultiple corrections found for '{original_word}':")
                click.echo(f"Suggestions: {', '.join(potential_corrections)}")

                corrected_word = click.prompt(
                    f"Choose the correct word for '{original_word}' (or press Enter to skip)",
                    type=str,
                    default="",
                    show_default=False,
                )

                if corrected_word and corrected_word in potential_corrections:
                    current_entries = update_word_in_entries(
                        current_entries, original_word, corrected_word
                    )
                    # Apply the translation and example immediately
                    entry_data = _entry_for_correction(original_word, corrected_word)
                    if entry_data:
                        current_entries[corrected_word]["translation"] = sanitize_csv_value(
                            entry_data["translation"]
                        )
                        current_entries[corrected_word]["example"] = sanitize_csv_value(
                            entry_data["example"]
                        )
                    click.echo(f"Updated '{original_word}' → '{corrected_word}' ✓")
                else:
                    click.echo(f"Skipped '{original_word}'")
                    skip_translation_for.add(original_word)

        click.echo()

    # Validate entries before writing to prevent data loss
    validation = validate_entries_before_write(current_entries)
    if not validation["valid"]:
        raise ValidationError(
            f"Cannot write: {validation['error']}. Original file preserved. Check backup for recovery."
        )

    # Write the updated translations and examples to the output file atomically
    def write_translations(output_file):
        writer = DictWriter(output_file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()

        # Iterate through the current entries and update them with the new translations and examples
        for word, current_entry in current_entries.items():
            if word in skip_translation_for:
                writer.writerow(current_entry)
                continue

            entry_data = new_entries.get(word)
            recognized_word = entry_data.get("recognized_word") if entry_data else None

            if (
                entry_data
                and not current_entry["translation"]
                and not _is_missing_or_blank(recognized_word)
                and recognized_word == word
            ):
                current_entry["translation"] = sanitize_csv_value(entry_data["translation"])
                current_entry["example"] = sanitize_csv_value(entry_data["example"])

            # Write the updated entry to the output file
            writer.writerow(current_entry)

    atomic_write_csv(translations_path, write_translations)

    # Create a backup of the translations file
    utils.backup_file(backup_dir, translations_path)


def generate_anki_headers(language_to_learn, mother_tongue, custom_deck_name=None):
    """
    Generate Anki file headers for proper import configuration.

    Args:
        language_to_learn (str): The target language being learned
        mother_tongue (str): The user's native language
        custom_deck_name (str, optional): Custom deck name. If None, auto-generates based on language pair mode.

    Returns:
        str: Formatted header lines for Anki import
    """
    # Use custom deck name if provided, otherwise auto-generate based on mode
    if custom_deck_name:
        deck_name = custom_deck_name
    else:
        mode = utils.get_pair_mode(language_to_learn, mother_tongue)
        if mode == "definition":
            deck_name = f"{language_to_learn.capitalize()} definitions"
        else:
            deck_name = f"{language_to_learn.capitalize()} vocabulary"

    headers = [
        "#separator:tab",
        "#html:true",
        "#notetype:Basic (and reversed card)",
        "#tags:vocabmaster",
        f"#deck:{deck_name}",
    ]
    return "\n".join(headers)


def generate_anki_output_file(
    translations_path, anki_output_file, language_to_learn, mother_tongue, custom_deck_name=None
):
    """
    Converts a translations file to a CSV file formatted for Anki import.

    This function reads a translations file with words, their translations, and examples, and creates a new TSV file
    formatted as an Anki deck with proper headers. The resulting file can be imported into Anki to create flashcards
    with the word on the front and the translation and example on the back.

    Uses atomic write to prevent corruption if interrupted.

    Args:
        translations_path (str): The path to the CSV file containing the translations and examples.
        anki_output_file (str): The path to the output TSV file formatted for Anki import.
        language_to_learn (str): The target language being learned.
        mother_tongue (str): The user's native language.
        custom_deck_name (str, optional): Custom deck name. If None, auto-generates based on language pair mode.

    Returns:
        None
    """
    # Ensure the source file contains the expected header so the DictReader can parse rows safely.
    ensure_csv_has_fieldnames(translations_path)

    # Read all translations first
    with open(translations_path, encoding="UTF-8") as translations_file:
        translations_dict_reader = DictReader(translations_file)
        all_translations = list(translations_dict_reader)

    def write_anki_deck(anki_file):
        # Write Anki headers first
        headers = generate_anki_headers(language_to_learn, mother_tongue, custom_deck_name)
        anki_file.write(headers + "\n")

        anki_dict_writer = DictWriter(
            anki_file,
            fieldnames=["Front", "Back"],
            quoting=csv.QUOTE_MINIMAL,
            delimiter="\t",
        )

        for translations in all_translations:
            if not translations["translation"] or not translations["example"]:
                continue
            else:
                translation_text = translations["translation"].strip('"')

                # Create a card with the word on the front, and the translations and example on the back
                card = {
                    "Front": translations["word"],
                    "Back": f"{translation_text}<br><br><details><summary>example</summary><i>&quot;{translations['example']}&quot;</i></details>",
                }

                # Write the card to the Anki output file
                anki_dict_writer.writerow(card)

    atomic_write_csv(anki_output_file, write_anki_deck)


def ensure_csv_has_fieldnames(translations_path, fieldnames=None):
    """
    Ensure the CSV file starts with the expected fieldnames.

    The header row is inserted only when it is missing. Uses atomic write to
    prevent corruption if interrupted during the insert.

    Args:
        translations_path (str): The path to the CSV file.
        fieldnames (list): A list of strings containing the column names.
    """
    if fieldnames is None:
        fieldnames = CSV_FIELDNAMES

    translations_path = Path(translations_path)

    with open(translations_path, "r", encoding="UTF-8") as file:
        # Check if the fieldnames is already present in the first row of the content
        for line in file:
            if line.startswith(",".join(fieldnames)):
                return
            else:
                break

        file.seek(0, 0)  # Move the file pointer to the beginning of the file
        content = file.read()

    # Need to insert header row - use atomic write
    def write_with_header(output_file):
        writer = csv.writer(output_file)
        writer.writerow(fieldnames)  # Write the fieldnames to the first row
        output_file.write(content)  # Write the original content after the fieldnames

    atomic_write_csv(translations_path, write_with_header)


def vocabulary_list_is_empty(translations_path):
    """
    Checks if the vocabulary list is empty.

    Args:
        translations_path (str): The path to the CSV file containing the translations and examples.

    Returns:
        bool: True if the vocabulary list is empty, False otherwise.
    """
    ensure_csv_has_fieldnames(translations_path, ["word", "translation", "example"])

    with open(translations_path, encoding="UTF-8") as file:
        dict_reader = DictReader(file)

        for row in dict_reader:
            if any((value or "").strip() for value in row.values()):
                return False
    return True


def calculate_vocabulary_stats(translations_path):
    """
    Compute statistics about a translations file.

    Args:
        translations_path (pathlib.Path | str): Path to the vocabulary CSV file.

    Returns:
        dict[str, int]: Dictionary with total, translated, and pending counts.
    """
    translations_path = Path(translations_path)
    if not translations_path.exists():
        return {"total": 0, "translated": 0, "pending": 0}

    total = 0
    translated = 0

    with open(translations_path, encoding="UTF-8") as translations_file:
        dict_reader = DictReader(translations_file)

        for row in dict_reader:
            word = (row.get("word") or "").strip()
            if not word:
                continue
            total += 1
            has_translation = bool((row.get("translation") or "").strip())
            has_example = bool((row.get("example") or "").strip())
            if has_translation and has_example:
                translated += 1

    pending = total - translated
    return {"total": total, "translated": translated, "pending": pending}
