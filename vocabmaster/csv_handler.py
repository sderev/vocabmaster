import csv
from csv import DictReader, DictWriter

import click

from vocabmaster import gpt_integration, utils

CSV_FIELDNAMES = ["word", "translation", "example"]


def detect_word_mismatches(original_words, gpt_response):
    """
    Detect words that don't match between original words and LM response.

    Args:
        original_words (list): List of original words sent to the LM
        gpt_response (dict): Dictionary of LM responses with word as key

    Returns:
        list: List of tuples (original_word, [possible_corrections])
    """
    mismatches = []

    # Find words in LM response that aren't in original words (potential corrections)
    original_words_set = set(original_words)
    gpt_words_set = set(gpt_response.keys())
    potential_corrections = gpt_words_set - original_words_set

    for original_word in original_words:
        if original_word not in gpt_response:
            # Only report as mismatch if there are potential corrections available
            if potential_corrections:
                mismatches.append((original_word, list(potential_corrections)))

    return mismatches


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


def word_exists(word, translations_filepath):
    """
    Checks if the word is already present in the `translations_filepath`.

    Args:
        word (str): The word to check for its presence in the file.
        translations_filepath (str): The path to the file containing the list of words.

    Returns:
        bool: True if the word is found in the file, False otherwise.
    """
    with open(translations_filepath, encoding="UTF-8") as file:
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
    with open(translations_filepath, "a", encoding="UTF-8") as file:
        dict_writer = DictWriter(file, fieldnames=CSV_FIELDNAMES)
        dict_writer.writerow({"word": word, "translation": "", "example": ""})


def get_words_to_translate(translations_filepath):
    """
    Reads a CSV file containing words, translations, and examples, and returns a list of words that need translations.

    The input CSV file should have the following columns: 'word', 'translation', and 'example'.
    If a row is missing either the 'translation' or 'example' column, the 'word' from that row will be added to the list.

    Args:
        translations_filepath (str): The path to the input CSV file containing words, translations, and examples.

    Returns:
        list: A list of words that need translations.
    """
    words_to_translate = []

    with open(translations_filepath, encoding="UTF-8") as translations_file:
        dict_reader = DictReader(translations_file)
        # fieldnames = ["word", "translation", "example"]

        for row in dict_reader:
            # If a row is missing a translation or example, add the word to the list of words to translate
            if not row["translation"] or not row["example"]:
                words_to_translate.append(row["word"])

    if not words_to_translate:
        raise Exception(
            "All the words in the vocabulary list already have translations and examples"
        )
    else:
        return words_to_translate


def generate_translations_and_examples(language_to_learn, mother_tongue, translations_filepath):
    """
    Generates translations and examples for a list of words using the LM.

    This function calls `get_words_to_translate` to obtain a list of words that need translations,
    using the provided `translations_filepath`. It then formats the prompt using
    `gpt_integration.format_prompt` and sends a request to the LM. The generated text from
    the LM is returned.

    Args:
        language_to_learn (str): The language to learn.
        mother_tongue (str): The user's mother tongue.
        translations_filepath (str): The path to the input CSV file containing words,
                                       translations, and examples.

    Returns:
        str: The generated text containing translations and examples.
    """
    # Get the list of words that need translations and generate the LM prompt
    words_to_translate = get_words_to_translate(translations_filepath)
    prompt = gpt_integration.format_prompt(language_to_learn, mother_tongue, words_to_translate)

    # Send a request to the LM and extract the generated text
    gpt_response = gpt_integration.chatgpt_request(prompt=prompt, stream=True, temperature=0.6)
    generated_text = gpt_response[0]

    # Create a backup of the LM response
    backup_dir = utils.get_backup_dir(language_to_learn, mother_tongue)
    utils.backup_content(backup_dir, gpt_response)

    return generated_text


def convert_text_to_dict(generated_text):
    """
    Clean and convert the given text into a dictionary.

    The text should be in the format:
    "'word1',"translation1","example1"\n'word2',"translation2","example2"'

    Args:
        generated_text (str): The text to be cleaned and converted.

    Returns:
        dict: A dictionary with words as keys and a dictionary of translations and examples as values.
    """
    # Clean input text and split it into lines
    cleaned_text = generated_text.replace("\n\n", "\n").replace("```csv", "").replace("```", "")
    lines = cleaned_text.strip().splitlines()

    # Create a dictionary of words with translations and examples
    result = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            word, translation_quoted, example_quoted = line.split("\t")

            translation = translation_quoted.strip("'")
            example = example_quoted.strip('"')

            result[word] = {
                "translation": translation,
                "example": example,
            }
        except ValueError:
            click.echo(f"{click.style('Warning: ', fg='yellow')} Could not parse line:\n{line}")
            continue
    return result


def add_translations_and_examples_to_file(translations_filepath, pair):
    """
    Updates the translations file with new translations and examples.

    This function reads a CSV file with words that need translation and their existing translations and examples.
    It generates new translations and examples using the `generate_translations_and_examples` function and updates
    the CSV file with the new translations and examples.

    Args:
        translations_filepath (str): The path to the CSV file containing the translations and examples.
    Returns:
        pair (str): The language pair in the format: 'language_to_learn:mother_tongue'.

        None
    """
    # Generate new translations and examples, then convert the results to a dictionary
    language_to_learn, mother_tongue = utils.get_language_pair_from_option(pair)

    # Get the original words that were sent to the LM for mismatch detection
    original_words = get_words_to_translate(translations_filepath)

    new_entries = convert_text_to_dict(
        generate_translations_and_examples(language_to_learn, mother_tongue, translations_filepath)
    )

    # Read the current entries from the input file and store them in a dictionary
    with open(translations_filepath, "r", encoding="UTF-8") as input_file:
        translations_reader = DictReader(input_file)
        current_entries = {row["word"]: row for row in translations_reader}

    # Detect and handle word mismatches (e.g., typo corrections by the LM)
    mismatches = detect_word_mismatches(original_words, new_entries)

    if mismatches:
        click.echo(f"\n{click.style('Word corrections detected:', fg='yellow')}")

        for original_word, potential_corrections in mismatches:
            if len(potential_corrections) == 1:
                corrected_word = potential_corrections[0]
                if ask_user_about_correction(original_word, corrected_word):
                    current_entries = update_word_in_entries(
                        current_entries, original_word, corrected_word
                    )
                    # Apply the translation and example immediately
                    current_entries[corrected_word]["translation"] = new_entries[corrected_word][
                        "translation"
                    ]
                    current_entries[corrected_word]["example"] = new_entries[corrected_word][
                        "example"
                    ]
                    click.echo(f"Updated '{original_word}' → '{corrected_word}' ✓")
                else:
                    click.echo(f"Kept original word '{original_word}'")
            else:
                click.echo(f"\nThe LM didn't return a translation for '{original_word}'.")
                click.echo(f"Available translations: {', '.join(potential_corrections)}")

                corrected_word = click.prompt(
                    f"Enter the correct word for '{original_word}' (or press Enter to skip)",
                    type=str,
                    default="",
                    show_default=False,
                )

                if corrected_word and corrected_word in potential_corrections:
                    current_entries = update_word_in_entries(
                        current_entries, original_word, corrected_word
                    )
                    # Apply the translation and example immediately
                    current_entries[corrected_word]["translation"] = new_entries[corrected_word][
                        "translation"
                    ]
                    current_entries[corrected_word]["example"] = new_entries[corrected_word][
                        "example"
                    ]
                    click.echo(f"Updated '{original_word}' → '{corrected_word}' ✓")
                else:
                    click.echo(f"Skipped '{original_word}'")

        click.echo()

    # Write the updated translations and examples to the output file
    with open(translations_filepath, "w", encoding="UTF-8") as output_file:
        writer = DictWriter(output_file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()

        # Iterate through the current entries and update them with the new translations and examples
        for word, current_entry in current_entries.items():
            if word in new_entries and not current_entry["translation"]:
                current_entry["translation"] = new_entries[word]["translation"]
                current_entry["example"] = new_entries[word]["example"]

            # Write the updated entry to the output file
            writer.writerow(current_entry)

    # Create a backup of the translations file
    backup_dir = utils.get_backup_dir(language_to_learn, mother_tongue)
    utils.backup_file(backup_dir, translations_filepath)


def generate_anki_headers(language_to_learn, mother_tongue):
    """
    Generate Anki file headers for proper import configuration.

    Args:
        language_to_learn (str): The target language being learned
        mother_tongue (str): The user's native language

    Returns:
        str: Formatted header lines for Anki import
    """
    headers = [
        "#separator:tab",
        "#html:true",
        "#notetype:Basic (and reversed card)",
        "#tags:vocabmaster",
        f"#deck:{language_to_learn.capitalize()} vocabulary",
    ]
    return "\n".join(headers)


def generate_anki_output_file(
    translations_filepath, anki_output_file, language_to_learn, mother_tongue
):
    """
    Converts a translations file to a CSV file formatted for Anki import.

    This function reads a translations file with words, their translations, and examples, and creates a new TSV file
    formatted as an Anki deck with proper headers. The resulting file can be imported into Anki to create flashcards
    with the word on the front and the translation and example on the back.

    Args:
        translations_filepath (str): The path to the CSV file containing the translations and examples.
        anki_output_file (str): The path to the output TSV file formatted for Anki import.
        language_to_learn (str): The target language being learned.
        mother_tongue (str): The user's native language.

    Returns:
        None
    """
    # Ensure the source file contains the expected header so the DictReader can parse rows safely.
    ensure_csv_has_fieldnames(translations_filepath)

    with (
        open(translations_filepath, encoding="UTF-8") as translations_file,
        open(anki_output_file, "w", encoding="UTF-8") as anki_file,
    ):
        # Write Anki headers first
        headers = generate_anki_headers(language_to_learn, mother_tongue)
        anki_file.write(headers + "\n")

        translations_dict_reader = DictReader(translations_file)

        anki_dict_writer = DictWriter(
            anki_file,
            fieldnames=["Front", "Back"],
            quoting=csv.QUOTE_MINIMAL,
            delimiter="\t",
        )

        for translations in translations_dict_reader:
            if not translations["translation"] or not translations["example"]:
                continue
            else:
                translations["translation"] = translations["translation"].strip('"')

                # Create a card with the word on the front, and the translations and example on the back
                card = {
                    "Front": translations["word"],
                    "Back": f"{translations['translation']}<br><br><details><summary>example</summary><i>&quot;{translations['example']}&quot;</i></details>",
                }

                # Write the card to the Anki output file
                anki_dict_writer.writerow(card)


def ensure_csv_has_fieldnames(translations_filepath, fieldnames=None):
    """
    Ensure the CSV file starts with the expected fieldnames.

    The header row is inserted only when it is missing.

    Args:
        translations_filepath (str): The path to the CSV file.
        fieldnames (list): A list of strings containing the column names.
    """
    if fieldnames is None:
        fieldnames = CSV_FIELDNAMES

    with open(translations_filepath, "r+", encoding="UTF-8") as file:
        # Check if the fieldnames is already present in the first row of the content
        for line in file:
            if line.startswith(",".join(fieldnames)):
                return
            else:
                break

        file.seek(0, 0)  # Move the file pointer to the beginning of the file
        content = file.read()
        file.seek(0, 0)

        writer = csv.writer(file)
        writer.writerow(fieldnames)  # Write the fieldnames to the first row
        file.write(content)  # Write the original content after the fieldnames


def vocabulary_list_is_empty(translations_filepath):
    """
    Checks if the vocabulary list is empty.

    Args:
        translations_filepath (str): The path to the CSV file containing the translations and examples.

    Returns:
        bool: True if the vocabulary list is empty, False otherwise.
    """
    ensure_csv_has_fieldnames(translations_filepath, ["word", "translation", "example"])

    with open(translations_filepath, encoding="UTF-8") as file:
        dict_reader = DictReader(file)

        for row in dict_reader:
            if any((value or "").strip() for value in row.values()):
                return False
    return True
