from vocabmaster import csv_handler


def test_detect_word_mismatches_finds_typo_corrections():
    """Test detecting when the LM corrects typos in word responses."""
    original_words = ["brethen", "hello"]
    gpt_response = {
        "brethren": {"translation": "frères", "example": "The brethren gather"},
        "hello": {"translation": "bonjour", "example": "Hello there"},
    }

    # This function doesn't exist yet - we'll implement it
    mismatches = csv_handler.detect_word_mismatches(original_words, gpt_response)

    expected = [("brethen", ["brethren"])]
    assert mismatches == expected


def test_detect_word_mismatches_returns_empty_when_all_match():
    """Test no mismatches detected when all words match exactly."""
    original_words = ["hello", "world"]
    gpt_response = {
        "hello": {"translation": "bonjour", "example": "Hello there"},
        "world": {"translation": "monde", "example": "The world is big"},
    }

    mismatches = csv_handler.detect_word_mismatches(original_words, gpt_response)
    assert mismatches == []


def test_detect_word_mismatches_handles_multiple_corrections():
    """Test detecting multiple typo corrections in one batch."""
    original_words = ["brethen", "seperate", "definately"]
    gpt_response = {
        "brethren": {"translation": "frères", "example": "The brethren gather"},
        "separate": {"translation": "séparer", "example": "Separate items"},
        "definitely": {"translation": "définitivement", "example": "Definitely yes"},
    }

    mismatches = csv_handler.detect_word_mismatches(original_words, gpt_response)

    # Current simple logic: all missing words get all potential corrections
    # We can improve this later with similarity matching
    expected_corrections = ["brethren", "separate", "definitely"]

    assert len(mismatches) == 3
    # Check that all original words are detected as mismatches
    original_words_in_mismatches = [mismatch[0] for mismatch in mismatches]
    assert set(original_words_in_mismatches) == set(original_words)
    # Check that all corrections are provided (order doesn't matter)
    for _, corrections in mismatches:
        assert set(corrections) == set(expected_corrections)


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
        "brethren": {"translation": "frères", "example": "The brethren gather"},
        "hello": {"translation": "bonjour", "example": "Hello there"},
    }

    # Test the logic that should apply translations immediately after word correction
    original_words = ["brethen", "hello"]
    mismatches = csv_handler.detect_word_mismatches(original_words, new_entries)

    assert len(mismatches) == 1
    original_word, potential_corrections = mismatches[0]
    assert original_word == "brethen"
    assert "brethren" in potential_corrections

    # Simulate user accepting the correction
    corrected_word = "brethren"
    current_entries = csv_handler.update_word_in_entries(
        current_entries, original_word, corrected_word
    )

    # Apply translation immediately (this is what the bug fix does)
    current_entries[corrected_word]["translation"] = new_entries[corrected_word]["translation"]
    current_entries[corrected_word]["example"] = new_entries[corrected_word]["example"]

    # Verify the correction is properly applied including the internal word field
    assert "brethen" not in current_entries
    assert "brethren" in current_entries
    assert current_entries["brethren"]["word"] == "brethren"  # The word field should be corrected!
    assert current_entries["brethren"]["translation"] == "frères"
    assert current_entries["brethren"]["example"] == "The brethren gather"


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
