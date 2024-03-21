import csv
from csv import DictReader, DictWriter

from vocabmaster import gpt_integration, utils


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
        dict_reader = DictReader(file, fieldnames=["word", "translation", "example"])
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
        dict_writer = DictWriter(file, fieldnames=["word", "translation", "example"])
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
        fieldnames = ["word", "translation", "example"]

        for row in dict_reader:
            # If a row is missing a translation or example, add the word to the list of words to translate
            if not row["translation"] or not row["example"]:
                words_to_translate.append(row["word"])

    if not words_to_translate:
        raise Exception(
            "All the words in the vocabulary list already have translations and" " examples"
        )
    else:
        return words_to_translate


def generate_translations_and_examples(language_to_learn, mother_tongue, translations_filepath):
    """
    Generates translations and examples for a list of words using the GPT model.

    This function calls `get_words_to_translate` to obtain a list of words that need translations,
    using the provided `translations_filepath`. It then formats the prompt using
    `gpt_integration.format_prompt` and sends a request to the GPT model. The generated text from
    the GPT model is returned.

    Args:
        language_to_learn (str): The language to learn.
        mother_tongue (str): The user's mother tongue.
        translations_filepath (str): The path to the input CSV file containing words,
                                       translations, and examples.

    Returns:
        str: The generated text containing translations and examples.
    """
    # Get the list of words that need translations and generate the GPT model prompt
    words_to_translate = get_words_to_translate(translations_filepath)
    prompt = gpt_integration.format_prompt(language_to_learn, mother_tongue, words_to_translate)

    # Send a request to the GPT model and extract the generated text
    gpt_response = gpt_integration.chatgpt_request(prompt=prompt, stream=True, temperature=0.6)
    generated_text = gpt_response[0]

    # Create a backup of the GPT response
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
    cleaned_text = generated_text.replace("\n\n", "\n")
    lines = cleaned_text.strip().split("\n")

    # Create a dictionary of words with translations and examples
    result = {}
    for line in lines:
        word, translation_and_example = line.split(",", 1)
        translation, example = translation_and_example.rsplit(",", 1)
        result[word.replace("'", "")] = {
            "translation": translation.replace("'", ""),
            "example": example.replace("'", ""),
        }
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

    new_entries = convert_text_to_dict(
        generate_translations_and_examples(language_to_learn, mother_tongue, translations_filepath)
    )

    # Read the current entries from the input file and store them in a dictionary
    with open(translations_filepath, "r", encoding="UTF-8") as input_file:
        translations_reader = DictReader(input_file)
        current_entries = {row["word"]: row for row in translations_reader}

    # Write the updated translations and examples to the output file
    with open(translations_filepath, "w", encoding="UTF-8") as output_file:
        fieldnames = ["word", "translation", "example"]
        writer = DictWriter(output_file, fieldnames=fieldnames)
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


def generate_anki_output_file(translations_filepath, anki_output_file):
    """
    Converts a translations file to a CSV file formatted for Anki import.

    This function reads a translations file with words, their translations, and examples, and creates a new CSV file
    formatted as an Anki deck. The resulting file can be imported into Anki to create flashcards with the word on the
    front and the translation and example on the back.

    Args:
        translations_filepath (str): The path to the CSV file containing the translations and examples.
        anki_output_file (str): The path to the output CSV file formatted for Anki import.

    Returns:
        None
    """
    with open(translations_filepath, encoding="UTF-8") as translations_file, open(
        anki_output_file, "w", encoding="UTF-8"
    ) as anki_file:
        translations_dict_reader = DictReader(
            translations_file, fieldnames=["word", "translation", "example"]
        )
        next(translations_dict_reader)

        anki_dict_writer = DictWriter(
            anki_file,
            fieldnames=["front", "back"],
            quoting=csv.QUOTE_MINIMAL,
            delimiter=";",
        )

        for translations in translations_dict_reader:
            if not translations["translation"] or not translations["example"]:
                continue
            else:
                translations["translation"] = translations["translation"].strip('"')

                # Create a card with the word on the front, and the translations and example on the back
                card = {
                    "front": translations["word"],
                    "back": f"{translations['translation']}<br><br><details><summary>example</summary><i>&quot;{translations['example']}&quot;</i></details>",
                }

                # Write the card to the Anki output file
                anki_dict_writer.writerow(card)


def add_fieldnames_to_csv_file(translations_filepath, fieldnames):
    """
    Adds fieldnames to a CSV file if it's missing.

    Args:
        translations_filepath (str): The path to the CSV file.
        fieldnames (list): A list of strings containing the column names.
    """
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
    with open(translations_filepath, encoding="UTF-8") as file:
        csv_reader = csv.reader(file)
        next(csv_reader)  # Skip the fieldnames
        if len(list(csv_reader)) == 0:
            return True
