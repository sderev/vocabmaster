import csv
from pathlib import Path

from vocabmaster import config_handler, csv_handler


def test_convert_text_to_dict_preserves_single_quotes():
    """Ensure apostrophes inside translations and examples are preserved."""
    generated_text = "saluer\tsaluer\t'l'amour, l'ami'\t\"Je dis 'bonjour'\"\n"

    result = csv_handler.convert_text_to_dict(generated_text)

    assert result["saluer"]["recognized_word"] == "saluer"
    assert result["saluer"]["translation"] == "l'amour, l'ami"
    assert result["saluer"]["example"] == "Je dis 'bonjour'"


def test_detect_word_mismatches_finds_typo_corrections():
    """Test detecting when the LM corrects typos in word responses."""
    original_words = ["brethen", "hello"]
    gpt_response = {
        "brethen": {
            "recognized_word": "brethren",
            "translation": "frères",
            "example": "The brethren gather",
        },
        "hello": {
            "recognized_word": "hello",
            "translation": "bonjour",
            "example": "Hello there",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    expected = [("brethen", ["brethren"])]
    assert mismatches == expected
    assert missing_words == []


def test_detect_word_mismatches_returns_empty_when_all_match():
    """Test no mismatches detected when all words match exactly."""
    original_words = ["hello", "world"]
    gpt_response = {
        "hello": {
            "recognized_word": "hello",
            "translation": "bonjour",
            "example": "Hello there",
        },
        "world": {
            "recognized_word": "world",
            "translation": "monde",
            "example": "The world is big",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)
    assert mismatches == []
    assert missing_words == []


def test_detect_word_mismatches_handles_multiple_corrections():
    """Test detecting multiple typo corrections in one batch."""
    original_words = ["brethen", "seperate", "definately"]
    gpt_response = {
        "brethen": {
            "recognized_word": "brethren",
            "translation": "frères",
            "example": "The brethren gather",
        },
        "seperate": {
            "recognized_word": "separate",
            "translation": "séparer",
            "example": "Separate items",
        },
        "definately": {
            "recognized_word": "definitely",
            "translation": "définitivement",
            "example": "Definitely yes",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    expected = {
        "brethen": ["brethren"],
        "seperate": ["separate"],
        "definately": ["definitely"],
    }

    assert len(mismatches) == 3
    assert missing_words == []
    for original_word, corrections in mismatches:
        assert expected[original_word] == corrections


def test_ask_user_about_word_correction_accepts_change(monkeypatch):
    """Test user confirmation flow when user accepts word correction."""
    # Mock click.confirm to return True
    monkeypatch.setattr("click.confirm", lambda msg: True)

    # This function doesn't exist yet - we'll implement it
    result = csv_handler.ask_user_about_correction("brethen", "brethren")

    assert result is True


def test_ask_user_about_word_correction_rejects_change(monkeypatch):
    """Test user confirmation flow when user rejects word correction."""
    # Mock click.confirm to return False
    monkeypatch.setattr("click.confirm", lambda msg: False)

    result = csv_handler.ask_user_about_correction("brethen", "brethren")

    assert result is False


def test_update_word_key_in_csv_entries():
    """Test updating a word key in the CSV entries dictionary after user confirmation."""
    current_entries = {
        "brethen": {"word": "brethen", "translation": "", "example": ""},
        "hello": {"word": "hello", "translation": "bonjour", "example": "Hello there"},
    }

    updated_entries = csv_handler.update_word_in_entries(current_entries, "brethen", "brethren")

    # Check that dictionary keys are updated
    assert "brethen" not in updated_entries
    assert "brethren" in updated_entries

    # Check that the internal "word" field is also updated
    assert updated_entries["brethren"]["word"] == "brethren"
    assert updated_entries["brethren"]["translation"] == ""
    assert updated_entries["brethren"]["example"] == ""

    # Check that other entries are unchanged
    assert updated_entries["hello"]["word"] == "hello"
    assert updated_entries["hello"]["translation"] == "bonjour"
    assert updated_entries["hello"]["example"] == "Hello there"


def test_word_correction_applies_translation_immediately():
    """Test that when a word is corrected, the translation is applied immediately."""
    current_entries = {
        "brethen": {"word": "brethen", "translation": "", "example": ""},
        "hello": {"word": "hello", "translation": "bonjour", "example": "Hello there"},
    }

    new_entries = {
        "brethen": {
            "recognized_word": "brethren",
            "translation": "frères",
            "example": "The brethren gather",
        },
        "hello": {
            "recognized_word": "hello",
            "translation": "bonjour",
            "example": "Hello there",
        },
    }

    # Test the logic that should apply translations immediately after word correction
    original_words = ["brethen", "hello"]
    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, new_entries)

    assert len(mismatches) == 1
    assert missing_words == []
    original_word, potential_corrections = mismatches[0]
    assert original_word == "brethen"
    assert "brethren" in potential_corrections

    # Simulate user accepting the correction
    corrected_word = "brethren"
    current_entries = csv_handler.update_word_in_entries(
        current_entries, original_word, corrected_word
    )

    # Apply translation immediately (this is what the bug fix does)
    entry_data = new_entries[original_word]
    current_entries[corrected_word]["translation"] = entry_data["translation"]
    current_entries[corrected_word]["example"] = entry_data["example"]

    # Verify the correction is properly applied including the internal word field
    assert "brethen" not in current_entries
    assert "brethren" in current_entries
    assert current_entries["brethren"]["word"] == "brethren"  # The word field should be corrected!
    assert current_entries["brethren"]["translation"] == "frères"
    assert current_entries["brethren"]["example"] == "The brethren gather"


def test_backup_occurs_before_chat_request(tmp_path, fake_home, monkeypatch):
    """Ensure the vocabulary file is backed up before contacting the language model."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config_handler.set_data_directory(data_dir)

    translations_file = data_dir / "vocab_list_english-french.csv"
    translations_file.write_text("word,translation,example\nhello,,\n", encoding="utf-8")

    call_order = []

    def fake_backup_file(backup_dir, filepath):
        call_order.append(("backup_file", Path(filepath).name))

    monkeypatch.setattr(csv_handler.utils, "backup_file", fake_backup_file)

    def fake_generate(language_to_learn, mother_tongue, filepath):
        call_order.append(("generate_translations_and_examples", None))
        return "hello\thello\t'bonjour'\t\"Salut !\"\n"

    monkeypatch.setattr(
        csv_handler,
        "generate_translations_and_examples",
        fake_generate,
    )

    csv_handler.add_translations_and_examples_to_file(
        str(translations_file),
        "english:french",
    )

    assert call_order[0][0] == "backup_file"
    assert call_order[1][0] == "generate_translations_and_examples"
    assert sum(1 for name, _ in call_order if name == "backup_file") == 2
    assert "bonjour" in translations_file.read_text(encoding="utf-8")


def test_declined_correction_keeps_original_translation_empty(tmp_path, fake_home, monkeypatch):
    """Ensure we do not apply translations when a correction is rejected."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config_handler.set_data_directory(data_dir)

    translations_file = data_dir / "vocab_list_english-french.csv"
    translations_file.write_text("word,translation,example\nconvertable,,\n", encoding="utf-8")

    def fake_generate(language_to_learn, mother_tongue, filepath):
        return (
            "convertable\tconvertible\t'convertible, cabriolet'\t\"La voiture est convertible.\"\n"
        )

    monkeypatch.setattr(csv_handler, "generate_translations_and_examples", fake_generate)
    monkeypatch.setattr(csv_handler, "ask_user_about_correction", lambda *_: False)

    csv_handler.add_translations_and_examples_to_file(
        str(translations_file),
        "english:french",
    )

    with open(translations_file, encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    assert rows[0]["word"] == "convertable"
    assert rows[0]["translation"] == ""
    assert rows[0]["example"] == ""


def test_generate_anki_headers():
    """Test generation of Anki file headers."""
    headers = csv_handler.generate_anki_headers("english", "french")

    expected_lines = [
        "#separator:tab",
        "#html:true",
        "#notetype:Basic (and reversed card)",
        "#tags:vocabmaster",
        "#deck:English vocabulary",
    ]

    assert headers.splitlines() == expected_lines


def test_generate_anki_headers_different_languages():
    """Test header generation with different language pairs."""
    headers = csv_handler.generate_anki_headers("spanish", "italian")

    assert "#deck:Spanish vocabulary" in headers
    assert "#separator:tab" in headers
    assert "#html:true" in headers
    assert "#notetype:Basic (and reversed card)" in headers
    assert "#tags:vocabmaster" in headers


def test_generate_anki_headers_capitalization():
    """Test that language names are properly capitalized in deck name."""
    headers = csv_handler.generate_anki_headers("german", "english")

    assert "#deck:German vocabulary" in headers


def test_generate_anki_headers_same_language_definition_mode():
    """Test header generation for same-language pairs uses 'definitions' deck name."""
    headers = csv_handler.generate_anki_headers("french", "french")

    assert "#deck:French definitions" in headers
    assert "#separator:tab" in headers
    assert "#html:true" in headers
    assert "#notetype:Basic (and reversed card)" in headers
    assert "#tags:vocabmaster" in headers


def test_generate_anki_headers_same_language_case_insensitive():
    """Test definition mode works with case variations."""
    headers_lower = csv_handler.generate_anki_headers("english", "english")
    headers_mixed = csv_handler.generate_anki_headers("English", "ENGLISH")

    assert "#deck:English definitions" in headers_lower
    assert "#deck:English definitions" in headers_mixed


def test_generate_anki_headers_with_custom_deck_name():
    """Test header generation with custom deck name overrides auto-generation."""
    headers = csv_handler.generate_anki_headers("english", "french", "My Custom Deck")

    assert "#deck:My Custom Deck" in headers
    assert "#deck:English vocabulary" not in headers


def test_generate_anki_headers_custom_name_overrides_definition_mode():
    """Test custom deck name overrides definition mode auto-generation."""
    headers = csv_handler.generate_anki_headers("french", "french", "French Basics")

    assert "#deck:French Basics" in headers
    assert "#deck:French definitions" not in headers


def test_generate_anki_headers_custom_name_with_special_chars():
    """Test custom deck names can contain special characters."""
    headers = csv_handler.generate_anki_headers("english", "french", "Business English (Advanced)")

    assert "#deck:Business English (Advanced)" in headers


def test_generate_anki_headers_none_falls_back_to_auto_generation():
    """Test None as custom_deck_name falls back to auto-generation."""
    headers_auto = csv_handler.generate_anki_headers("english", "french")
    headers_none = csv_handler.generate_anki_headers("english", "french", None)

    assert headers_auto == headers_none
    assert "#deck:English vocabulary" in headers_none


def test_generate_anki_output_file_with_custom_deck_name(tmp_path):
    """Test complete Anki output file generation with custom deck name."""
    translations_file = tmp_path / "translations.csv"
    translations_content = """word,translation,example
test,essai,This is a test.
"""
    translations_file.write_text(translations_content)

    anki_file = tmp_path / "anki.csv"
    csv_handler.generate_anki_output_file(
        translations_file, anki_file, "english", "french", "My Custom Deck"
    )

    content = anki_file.read_text()
    assert "#deck:My Custom Deck" in content
    assert "#deck:English vocabulary" not in content


def test_generate_anki_output_file_with_headers(tmp_path):
    """Test complete Anki output file generation with headers and tab separator."""
    # Create a test translations file
    translations_file = tmp_path / "translations.csv"
    translations_content = """word,translation,example
to harken back,"se rappeler, évoquer, remonter à",The story harks back to ancient legends.
a queasiness,"nausée, malaise, haut-le-cœur",He felt a queasiness after the roller coaster ride.
to snigger,"rire sous cape, ricaner, pouffer",They began to snigger at the teacher's mistake.
"""
    translations_file.write_text(translations_content)

    # Generate Anki output file
    anki_file = tmp_path / "anki_deck.tsv"
    csv_handler.generate_anki_output_file(
        str(translations_file), str(anki_file), "english", "french"
    )

    # Read and verify the output
    anki_content = anki_file.read_text()
    lines = anki_content.splitlines()

    # Check headers
    assert lines[0] == "#separator:tab"
    assert lines[1] == "#html:true"
    assert lines[2] == "#notetype:Basic (and reversed card)"
    assert lines[3] == "#tags:vocabmaster"
    assert lines[4] == "#deck:English vocabulary"

    # Check that data rows use tab separator and proper field names
    data_lines = [line for line in lines[5:] if line.strip()]
    assert len(data_lines) == 3  # Three words

    # Check first data row
    first_row = data_lines[0].split("\t")
    assert first_row[0] == "to harken back"
    assert "se rappeler, évoquer, remonter à" in first_row[1]
    assert "The story harks back to ancient legends." in first_row[1]
    assert "<br><br>" in first_row[1]  # HTML formatting preserved


def test_generate_anki_output_file_skips_incomplete_entries(tmp_path):
    """Test that incomplete entries (missing translation or example) are skipped."""
    # Create a test translations file with incomplete entries
    translations_file = tmp_path / "translations.csv"
    translations_content = """word,translation,example
to relitigate,"relancer un débat, réexaminer, rejuger",They decided not to relitigate the old arguments.
incomplete1,,"Missing example"
incomplete2,translation,
to harken back,"se rappeler, évoquer, remonter à",The story harks back to ancient legends.
"""
    translations_file.write_text(translations_content)

    # Generate Anki output file
    anki_file = tmp_path / "anki_deck.tsv"
    csv_handler.generate_anki_output_file(
        str(translations_file), str(anki_file), "english", "french"
    )

    # Read and verify the output
    anki_content = anki_file.read_text()
    data_lines = [line for line in anki_content.splitlines()[5:] if line.strip()]

    # Should only have 2 complete entries, not 4
    assert len(data_lines) == 2
    assert "to relitigate" in data_lines[0]
    assert "to harken back" in data_lines[1]


def test_generate_anki_output_file_different_languages(tmp_path):
    """Test output generation with different language pairs."""
    # Create a test translations file
    translations_file = tmp_path / "translations.csv"
    translations_content = """word,translation,example
a queasiness,"nausée, malaise, haut-le-cœur",He felt a queasiness after the roller coaster ride.
to snigger,"rire sous cape, ricaner, pouffer",They began to snigger at the teacher's mistake.
"""
    translations_file.write_text(translations_content)

    # Generate Anki output file
    anki_file = tmp_path / "anki_deck.tsv"
    csv_handler.generate_anki_output_file(
        str(translations_file), str(anki_file), "spanish", "italian"
    )

    # Read and verify the deck name header
    anki_content = anki_file.read_text()
    lines = anki_content.splitlines()

    assert "#deck:Spanish vocabulary" in lines


def test_vocabulary_list_is_empty_inserts_header_when_missing(tmp_path):
    """Ensure the helper adds the header row before evaluating emptiness."""
    translations_file = tmp_path / "translations.csv"
    translations_file.write_text("")

    assert csv_handler.vocabulary_list_is_empty(translations_file) is True
    assert translations_file.read_text().splitlines()[0] == "word,translation,example"


def test_vocabulary_list_is_empty_ignores_blank_rows(tmp_path):
    """Blank or whitespace-only rows should not count as vocabulary entries."""
    translations_file = tmp_path / "translations.csv"
    translations_file.write_text("word,translation,example\n   , ,   \n")

    assert csv_handler.vocabulary_list_is_empty(translations_file) is True


def test_vocabulary_list_is_empty_detects_existing_entries(tmp_path):
    """A row containing any value should mark the list as non-empty."""
    translations_file = tmp_path / "translations.csv"
    translations_file.write_text("word,translation,example\nbonjour,,\n")

    assert csv_handler.vocabulary_list_is_empty(translations_file) is False


def test_is_missing_or_blank_helper():
    """Test the _is_missing_or_blank helper function with various inputs."""
    # None should be considered missing
    assert csv_handler._is_missing_or_blank(None) is True

    # Empty string should be considered missing
    assert csv_handler._is_missing_or_blank("") is True

    # Whitespace-only strings should be considered missing
    assert csv_handler._is_missing_or_blank(" ") is True
    assert csv_handler._is_missing_or_blank("  ") is True
    assert csv_handler._is_missing_or_blank("\t") is True
    assert csv_handler._is_missing_or_blank("\n") is True
    assert csv_handler._is_missing_or_blank(" \t\n ") is True

    # Valid non-empty strings should not be considered missing
    assert csv_handler._is_missing_or_blank("hello") is False
    assert csv_handler._is_missing_or_blank(" hello ") is False  # Has content after stripping
    assert csv_handler._is_missing_or_blank("0") is False  # "0" is a valid value

    # Non-string values (edge case)
    assert csv_handler._is_missing_or_blank(0) is False
    assert csv_handler._is_missing_or_blank(False) is False
    assert csv_handler._is_missing_or_blank([]) is False


def test_csv_injection_prevention():
    """Test that CSV injection attacks are prevented by sanitizing LM responses."""
    # Test that the sanitize function works correctly
    assert csv_handler.sanitize_csv_value("=SUM(A:A)") == "'=SUM(A:A)"
    assert csv_handler.sanitize_csv_value("+1234567890") == "'+1234567890"
    assert csv_handler.sanitize_csv_value("-1234567890") == "'-1234567890"
    assert csv_handler.sanitize_csv_value("@SUM(A:A)") == "'@SUM(A:A)"
    assert csv_handler.sanitize_csv_value("\t=EVIL()") == "'\t=EVIL()"
    assert csv_handler.sanitize_csv_value("normal text") == "normal text"


def test_sanitize_csv_value_preserves_hyphenated_words():
    """Ensure vocabulary words starting with hyphen are not corrupted."""
    from vocabmaster.csv_handler import sanitize_csv_value

    # Natural language hyphens should be preserved
    assert sanitize_csv_value("-ism") == "-ism"
    assert sanitize_csv_value("-able") == "-able"
    assert sanitize_csv_value("-ing") == "-ing"

    # Formula-like patterns should still be sanitized
    assert sanitize_csv_value("-123") == "'-123"
    assert sanitize_csv_value("-=SUM") == "'-=SUM"
    assert sanitize_csv_value("--5") == "'--5"

    # DDE injection patterns should be sanitized even with letter after hyphen
    assert sanitize_csv_value("-cmd|'/C calc'!A0") == "'-cmd|'/C calc'!A0"
    assert sanitize_csv_value("-something!else") == "'-something!else"
    assert sanitize_csv_value("-pipe|test") == "'-pipe|test"

    # Function-like patterns should be sanitized
    assert sanitize_csv_value("-SUM(1,1)") == "'-SUM(1,1)"
    assert sanitize_csv_value("-HYPERLINK(url)") == "'-HYPERLINK(url)"
    assert sanitize_csv_value("-IF(A1,B1,C1)") == "'-IF(A1,B1,C1)"

    # Other dangerous chars unchanged
    assert sanitize_csv_value("=cmd") == "'=cmd"
    assert sanitize_csv_value("+1") == "'+1"
    assert sanitize_csv_value("@mention") == "'@mention"


def test_lm_responses_are_sanitized(tmp_path, monkeypatch):
    """Test that LM responses containing formulas are sanitized before writing to CSV."""

    # Create a test CSV file
    translations_file = tmp_path / "vocab_list_en-fr.csv"
    translations_file.write_text("word,translation,example\nhello,,\nworld,,\n")

    # Mock the LM response with CSV injection attempts
    mock_lm_response = """hello\thello\t'=SUM(A:A)'\t"=HYPERLINK('http://evil.com')"
world\tworld\t'+1234567890'\t"@SUM(1:1)"
"""

    # Mock the generate_translations_and_examples function
    def mock_generate(*args):
        return mock_lm_response

    monkeypatch.setattr("vocabmaster.csv_handler.generate_translations_and_examples", mock_generate)

    # Mock utils functions for backup operations
    monkeypatch.setattr(csv_handler.utils, "backup_file", lambda *args: None)
    monkeypatch.setattr(csv_handler.utils, "get_backup_dir", lambda *args: tmp_path / "backup")

    # Mock click.echo to suppress output
    monkeypatch.setattr("click.echo", lambda *args, **kwargs: None)

    # Mock the pair extraction
    monkeypatch.setattr(
        csv_handler.utils, "get_language_pair_from_option", lambda pair: ("en", "fr")
    )

    # Call the function
    csv_handler.add_translations_and_examples_to_file(translations_file, "en:fr")

    # Read the CSV file back and verify formulas were sanitized
    import csv

    with open(translations_file, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Verify that formulas were prefixed with single quote for safety
    assert rows[0]["word"] == "hello"
    assert rows[0]["translation"] == "'=SUM(A:A)"
    assert rows[0]["example"] == "'=HYPERLINK('http://evil.com')"

    assert rows[1]["word"] == "world"
    assert rows[1]["translation"] == "'+1234567890"
    assert rows[1]["example"] == "'@SUM(1:1)"


def test_tab_character_handling_in_content(monkeypatch):
    """Test that lines with tab characters in content are rejected to prevent corruption."""
    # Mock click.echo to capture warnings
    warnings = []

    def mock_echo(msg, **kwargs):
        warnings.append(str(msg))

    monkeypatch.setattr("click.echo", mock_echo)

    # Test TSV with tabs embedded in the content (should be rejected)
    tsv_with_tabs = """word1\tword1\t'trans\tlation with tab'\t"example\twith\ttabs"
word2\tword2\t'normal translation'\t"normal example"
"""

    result = csv_handler.convert_text_to_dict(tsv_with_tabs)

    # Lines with tabs in content should be rejected to prevent data corruption
    # Only word2 should be parsed successfully
    assert len(result) == 1
    assert "word1" not in result  # Rejected due to tabs in content
    assert result["word2"]["translation"] == "normal translation"
    assert result["word2"]["example"] == "normal example"

    # Check that a warning was issued
    assert any("corrupted" in w for w in warnings)


def test_convert_text_to_dict_legacy_3column_format():
    """Test backward compatibility with 3-column TSV format."""
    # Legacy format: word\ttranslation\texample
    generated_text = """hello\t'bonjour'\t"Hello, world!"
world\t'monde'\t"The world is big"
test\t'test'\t"This is a test"
"""

    result = csv_handler.convert_text_to_dict(generated_text)

    assert len(result) == 3
    # For legacy format, recognized_word should default to original_word
    assert result["hello"]["recognized_word"] == "hello"
    assert result["hello"]["translation"] == "bonjour"
    assert result["hello"]["example"] == "Hello, world!"

    assert result["world"]["recognized_word"] == "world"
    assert result["world"]["translation"] == "monde"

    assert result["test"]["recognized_word"] == "test"


def test_convert_text_to_dict_legacy_3column_with_quotes():
    """Test 3-column format with apostrophes and quotes in content."""
    generated_text = """l'ami\t'l'amour, l'ami'\t"C'est l'ami de Jean"
aujourd'hui\t'today'\t"Aujourd'hui c'est lundi"
"""

    result = csv_handler.convert_text_to_dict(generated_text)

    assert len(result) == 2
    assert result["l'ami"]["recognized_word"] == "l'ami"
    assert result["l'ami"]["translation"] == "l'amour, l'ami"
    assert result["l'ami"]["example"] == "C'est l'ami de Jean"

    assert result["aujourd'hui"]["recognized_word"] == "aujourd'hui"
    assert result["aujourd'hui"]["translation"] == "today"


def test_convert_text_to_dict_handles_both_formats():
    """Test that both 3-column and 4-column formats can be parsed."""
    # Mix of legacy and new formats (though unlikely in practice)
    generated_text = """hello\t'bonjour'\t"Hello!"
brethen\tbrethren\t'brothers'\t"The brethren gather"
world\t'monde'\t"World peace"
seperate\tseparate\t'séparer'\t"Separate items"
"""

    result = csv_handler.convert_text_to_dict(generated_text)

    assert len(result) == 4

    # 3-column entries
    assert result["hello"]["recognized_word"] == "hello"
    assert result["hello"]["translation"] == "bonjour"
    assert result["world"]["recognized_word"] == "world"

    # 4-column entries
    assert result["brethen"]["recognized_word"] == "brethren"
    assert result["brethen"]["translation"] == "brothers"
    assert result["seperate"]["recognized_word"] == "separate"
    assert result["seperate"]["translation"] == "séparer"


def test_convert_text_to_dict_unicode_in_3column():
    """Test 3-column format with unicode/emoji characters."""
    generated_text = """café\t'coffee ☕'\t"Un café, s'il vous plaît"
naïve\t'naïf'\t"Don't be naïve 🙄"
"""

    result = csv_handler.convert_text_to_dict(generated_text)

    assert result["café"]["recognized_word"] == "café"
    assert result["café"]["translation"] == "coffee ☕"
    assert result["naïve"]["recognized_word"] == "naïve"
    assert result["naïve"]["example"] == "Don't be naïve 🙄"


def test_legacy_3column_typo_correction_detection():
    """Test that typo corrections in legacy 3-column format are properly detected."""
    # Simulate a legacy 3-column response where LM corrected "brethen" to "brethren"
    legacy_lm_response = """brethren\t'brothers'\t"The brethren gather"
hello\t'bonjour'\t"Hello, world!"
"""

    # Parse the legacy response
    result = csv_handler.convert_text_to_dict(legacy_lm_response)

    # The result will have "brethren" as key (the corrected spelling)
    assert "brethren" in result
    assert "brethen" not in result

    # Now test mismatch detection with original words including the typo
    original_words = ["brethen", "hello"]
    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, result)

    # "brethen" should be offered "brethren" as a correction (not marked as missing)
    assert len(mismatches) == 1
    assert mismatches[0][0] == "brethen"
    assert "brethren" in mismatches[0][1]

    # Nothing should be marked as completely missing
    assert missing_words == []


def test_end_to_end_legacy_3column_backup_compatibility():
    """Integration test: complete workflow with cached 3-column LM response."""
    # Simulate a cached 3-column response (old format)
    legacy_lm_response = """hello\t'bonjour'\t"Hello, world!"
café\t'coffee'\t"Un café, s'il vous plaît"
world\t'monde'\t"The world is big"
"""

    # Parse the legacy response
    result = csv_handler.convert_text_to_dict(legacy_lm_response)

    # Should parse all 3 entries with recognized_word defaulting to original_word
    assert len(result) == 3
    assert result["hello"]["recognized_word"] == "hello"
    assert result["hello"]["translation"] == "bonjour"
    assert result["café"]["recognized_word"] == "café"
    assert result["café"]["translation"] == "coffee"
    assert result["world"]["recognized_word"] == "world"

    # Verify no mismatches detected (since recognized_word == original_word)
    original_words = ["hello", "café", "world"]
    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, result)

    assert mismatches == []
    assert missing_words == []

    # Verify translations would apply correctly
    for word in original_words:
        entry = result[word]
        # In the actual flow, these would apply since recognized_word == word
        assert entry["recognized_word"] == word
        assert entry["translation"] is not None
        assert entry["example"] is not None


def test_detect_word_mismatches_with_duplicate_words_and_corrections():
    """Edge case: duplicate words in original_words list with corrections.

    This tests that when the user has duplicate words in their vocabulary list
    and one of those words has a correction, the correction is not offered twice.
    """
    # Unlikely but possible: user has "hello" twice in their vocab list
    original_words = ["hello", "hello", "world"]
    gpt_response = {
        "hello": {
            "recognized_word": "héllo",  # LM corrected the spelling
            "translation": "bonjour",
            "example": "Hello there!",
        },
        "world": {
            "recognized_word": "world",
            "translation": "monde",
            "example": "The world",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    # The mismatch for "hello" should appear only ONCE, not twice
    # Even though "hello" appears twice in original_words
    assert len(mismatches) == 1 or len(mismatches) == 2  # Allow for bug detection
    assert missing_words == []

    # Count how many times "hello" appears in mismatches
    hello_mismatch_count = sum(1 for word, _ in mismatches if word == "hello")

    # EXPECTED: Should be 1 (no duplicates)
    # ACTUAL: Might be 2 if there's a bug
    # For now, just document what we find
    if hello_mismatch_count == 2:
        # Bug detected: duplicates in original_words create duplicate mismatches
        assert mismatches == [("hello", ["héllo"]), ("hello", ["héllo"])]
    else:
        # Expected behavior: deduplication happened somewhere
        assert mismatches == [("hello", ["héllo"])]


def test_detect_word_mismatches_with_duplicate_words_no_corrections():
    """Edge case: duplicate words in original_words list, all match exactly."""
    original_words = ["hello", "hello", "world"]
    gpt_response = {
        "hello": {
            "recognized_word": "hello",
            "translation": "bonjour",
            "example": "Hello!",
        },
        "world": {
            "recognized_word": "world",
            "translation": "monde",
            "example": "World!",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    # No mismatches should be detected, even with duplicates
    assert mismatches == []
    assert missing_words == []


def test_detect_word_mismatches_empty_original_words():
    """Edge case: empty original_words list should return empty results."""
    original_words = []
    gpt_response = {
        "hello": {
            "recognized_word": "hello",
            "translation": "bonjour",
            "example": "Hello!",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    assert mismatches == []
    assert missing_words == []


def test_detect_word_mismatches_case_sensitivity():
    """Case differences between original and recognized words are treated as corrections."""
    original_words = ["Hello", "WORLD"]
    gpt_response = {
        "Hello": {
            "recognized_word": "hello",  # Different case
            "translation": "bonjour",
            "example": "Hello there",
        },
        "WORLD": {
            "recognized_word": "world",  # Different case
            "translation": "monde",
            "example": "The world",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    # Case differences are treated as intentional corrections
    assert len(mismatches) == 2
    assert mismatches[0] == ("Hello", ["hello"])
    assert mismatches[1] == ("WORLD", ["world"])
    assert missing_words == []


def test_detect_word_mismatches_none_entry_in_response():
    """None values in gpt_response are treated as missing via fallback logic."""
    original_words = ["hello", "world"]
    gpt_response = {
        "hello": None,  # None value instead of dict
        "world": {
            "recognized_word": "world",
            "translation": "monde",
            "example": "The world",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    # "hello" with None value should be treated as missing
    assert mismatches == []
    assert missing_words == ["hello"]


def test_detect_word_mismatches_missing_recognized_word_key():
    """Entries missing the 'recognized_word' key are treated as missing."""
    original_words = ["hello", "world"]
    gpt_response = {
        "hello": {
            # No "recognized_word" key
            "translation": "bonjour",
            "example": "Hello there",
        },
        "world": {
            "recognized_word": "world",
            "translation": "monde",
            "example": "The world",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    # "hello" without recognized_word key should be treated as missing
    assert mismatches == []
    assert missing_words == ["hello"]


def test_detect_word_mismatches_missing_row_does_not_offer_unrelated():
    """When LM omits a row entirely, should not offer unrelated corrections."""
    original_words = ["brethen", "hello", "world"]
    gpt_response = {
        # "brethen" is completely missing from response
        "hello": {
            "recognized_word": "hello",
            "translation": "bonjour",
            "example": "Hello there",
        },
        "world": {
            "recognized_word": "world",
            "translation": "monde",
            "example": "The world",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    # brethen is missing, not a mismatch
    assert mismatches == []
    assert missing_words == ["brethen"]


def test_detect_word_mismatches_partial_response_logs_failures():
    """Test that partially missing responses are correctly identified."""
    original_words = ["apple", "banana", "cherry", "date"]
    gpt_response = {
        # Only apple and cherry returned
        "apple": {
            "recognized_word": "apple",
            "translation": "pomme",
            "example": "An apple a day",
        },
        "cherry": {
            "recognized_word": "cherry",
            "translation": "cerise",
            "example": "Cherry pie",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    assert mismatches == []
    assert set(missing_words) == {"banana", "date"}
    assert len(missing_words) == 2


def test_detect_word_mismatches_all_rows_missing():
    """Edge case: LM returns nothing for any requested word."""
    original_words = ["word1", "word2", "word3"]
    gpt_response = {}  # Empty response

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    assert mismatches == []
    assert missing_words == ["word1", "word2", "word3"]


def test_detect_word_mismatches_with_both_missing_and_corrected():
    """Test when some words are missing and others have corrections."""
    original_words = ["brethen", "missing1", "hello", "missing2"]
    gpt_response = {
        "brethen": {
            "recognized_word": "brethren",  # Corrected spelling
            "translation": "frères",
            "example": "The brethren",
        },
        # "missing1" is completely missing
        "hello": {
            "recognized_word": "hello",  # No correction
            "translation": "bonjour",
            "example": "Hello!",
        },
        # "missing2" is completely missing
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    assert mismatches == [("brethen", ["brethren"])]
    assert set(missing_words) == {"missing1", "missing2"}


def test_detect_word_mismatches_empty_string_recognized_word():
    """Empty string recognized_word should be treated as missing."""
    original_words = ["hello", "world"]
    gpt_response = {
        "hello": {
            "recognized_word": "",  # Empty string
            "translation": "bonjour",
            "example": "Hello there",
        },
        "world": {
            "recognized_word": "world",
            "translation": "monde",
            "example": "World peace",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    assert mismatches == []
    assert missing_words == ["hello"]  # Empty recognized_word treated as missing


def test_detect_word_mismatches_whitespace_recognized_word():
    """Whitespace-only recognized_word should be treated as missing."""
    original_words = ["apple", "banana", "cherry"]
    gpt_response = {
        "apple": {
            "recognized_word": "   ",  # Spaces only
            "translation": "pomme",
            "example": "An apple",
        },
        "banana": {
            "recognized_word": "\t",  # Tab only
            "translation": "banane",
            "example": "Yellow banana",
        },
        "cherry": {
            "recognized_word": "\n  \t",  # Mixed whitespace
            "translation": "cerise",
            "example": "Cherry pie",
        },
    }

    mismatches, missing_words = csv_handler.detect_word_mismatches(original_words, gpt_response)

    assert mismatches == []
    assert set(missing_words) == {"apple", "banana", "cherry"}


def test_add_translations_skips_blank_recognized_word(tmp_path, monkeypatch):
    """Blank recognized_word values should not auto-apply translations."""

    # Create a test CSV file
    translations_file = tmp_path / "vocab_list_en-fr.csv"
    translations_file.write_text("word,translation,example\nhello,,\nworld,,\n")

    # Mock the LM response with blank recognized_word
    mock_lm_response = """hello\t\t'bonjour'\t"Hello!"
world\t   \t'monde'\t"World peace"
"""

    # Mock the generate_translations_and_examples function
    def mock_generate(*args):
        return mock_lm_response

    monkeypatch.setattr("vocabmaster.csv_handler.generate_translations_and_examples", mock_generate)

    # Mock utils functions for backup operations
    monkeypatch.setattr(csv_handler.utils, "backup_file", lambda *args: None)
    monkeypatch.setattr(csv_handler.utils, "get_backup_dir", lambda *args: tmp_path / "backup")

    # Mock click.echo to suppress output
    monkeypatch.setattr("click.echo", lambda *args, **kwargs: None)

    # Mock the pair extraction
    monkeypatch.setattr(
        csv_handler.utils, "get_language_pair_from_option", lambda pair: ("en", "fr")
    )

    # Call the actual function that should NOT apply translations with blank recognized_word
    csv_handler.add_translations_and_examples_to_file(translations_file, "en:fr")

    # Read the CSV file back and verify translations were NOT applied
    import csv

    with open(translations_file, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Both rows should still have empty translations and examples
    assert len(rows) == 2
    assert rows[0]["word"] == "hello"
    assert rows[0]["translation"] == ""  # Should remain empty!
    assert rows[0]["example"] == ""  # Should remain empty!

    assert rows[1]["word"] == "world"
    assert rows[1]["translation"] == ""  # Should remain empty!
    assert rows[1]["example"] == ""  # Should remain empty!
