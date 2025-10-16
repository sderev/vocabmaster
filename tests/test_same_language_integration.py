"""Integration tests for same-language definition mode workflow."""
from pathlib import Path

from vocabmaster import config_handler, csv_handler


def test_same_language_workflow_generates_definitions(tmp_path, monkeypatch):
    """Test complete workflow with same-language pair generates definitions, not translations."""
    # Set up test environment
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Mock get_data_directory instead of calling set_data_directory
    monkeypatch.setattr(config_handler, "get_data_directory", lambda: data_dir)

    # Create a vocabulary file with French words
    vocab_file = data_dir / "vocab_list_french-french.csv"
    vocab_file.write_text("word,translation,example\nbonjour,,\nmonde,,\n", encoding="utf-8")

    # Mock the GPT response to return definitions
    def fake_generate(language_to_learn, mother_tongue, filepath):
        # Verify the languages are the same (definition mode)
        assert language_to_learn == "french"
        assert mother_tongue == "french"

        # Return definitions in the expected format
        return "bonjour\tsalutation, salut\t\"Bonjour, comment allez-vous ?\"\nmonde\tunivers, terre\t\"Le monde est vaste.\"\n"

    monkeypatch.setattr(
        csv_handler,
        "generate_translations_and_examples",
        fake_generate,
    )

    # Mock backup functions to avoid side effects
    monkeypatch.setattr(csv_handler.utils, "backup_file", lambda *args: None)

    # Execute the workflow
    csv_handler.add_translations_and_examples_to_file(
        str(vocab_file),
        "french:french",
    )

    # Verify the output contains definitions
    content = vocab_file.read_text(encoding="utf-8")
    assert "salutation, salut" in content
    assert "univers, terre" in content
    assert "Bonjour, comment allez-vous ?" in content
    assert "Le monde est vaste." in content


def test_same_language_anki_output_uses_definitions_deck_name(tmp_path):
    """Test that Anki output for same-language pairs uses 'definitions' deck name."""
    # Create a vocabulary file with definitions
    vocab_file = tmp_path / "vocab_french-french.csv"
    vocab_content = """word,translation,example
bonjour,salutation,Bonjour tout le monde
monde,univers,Le monde est grand
"""
    vocab_file.write_text(vocab_content)

    # Generate Anki output
    anki_file = tmp_path / "anki_french-french.tsv"
    csv_handler.generate_anki_output_file(
        str(vocab_file), str(anki_file), "french", "french"
    )

    # Verify the deck name is for definitions
    content = anki_file.read_text()
    assert "#deck:French definitions" in content
    assert "#deck:French vocabulary" not in content

    # Verify the data is present
    assert "bonjour" in content
    assert "salutation" in content


def test_same_language_case_variations_work(tmp_path, monkeypatch):
    """Test that case variations of same language are handled correctly."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Mock get_data_directory instead of calling set_data_directory
    monkeypatch.setattr(config_handler, "get_data_directory", lambda: data_dir)

    # Create vocabulary file with mixed case language pair
    vocab_file = data_dir / "vocab_list_english-english.csv"
    vocab_file.write_text("word,translation,example\nhello,,\n", encoding="utf-8")

    # Mock GPT response
    def fake_generate(language_to_learn, mother_tongue, filepath):
        # Verify both languages are treated as same despite case
        assert language_to_learn.casefold() == mother_tongue.casefold()
        return "hello\tgreeting\t\"Hello, how are you?\"\n"

    monkeypatch.setattr(
        csv_handler,
        "generate_translations_and_examples",
        fake_generate,
    )
    monkeypatch.setattr(csv_handler.utils, "backup_file", lambda *args: None)

    # Test with different case variations
    csv_handler.add_translations_and_examples_to_file(
        str(vocab_file),
        "English:ENGLISH",
    )

    content = vocab_file.read_text(encoding="utf-8")
    assert "greeting" in content


def test_different_language_still_generates_translations(tmp_path, monkeypatch):
    """Test that different-language pairs still work with translation mode."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Mock get_data_directory instead of calling set_data_directory
    monkeypatch.setattr(config_handler, "get_data_directory", lambda: data_dir)

    # Create vocabulary file with different language pair
    vocab_file = data_dir / "vocab_list_french-english.csv"
    vocab_file.write_text("word,translation,example\nbonjour,,\n", encoding="utf-8")

    # Mock GPT response for translation mode
    def fake_generate(language_to_learn, mother_tongue, filepath):
        # Verify languages are different (translation mode)
        assert language_to_learn != mother_tongue
        return "bonjour\thello, hi, good morning\t\"Bonjour, comment allez-vous ?\"\n"

    monkeypatch.setattr(
        csv_handler,
        "generate_translations_and_examples",
        fake_generate,
    )
    monkeypatch.setattr(csv_handler.utils, "backup_file", lambda *args: None)

    # Execute the workflow
    csv_handler.add_translations_and_examples_to_file(
        str(vocab_file),
        "french:english",
    )

    # Verify the output contains translations (multiple options)
    content = vocab_file.read_text(encoding="utf-8")
    assert "hello" in content


def test_different_language_anki_output_uses_vocabulary_deck_name(tmp_path):
    """Test that Anki output for different-language pairs uses 'vocabulary' deck name."""
    # Create a vocabulary file with translations
    vocab_file = tmp_path / "vocab_french-english.csv"
    vocab_content = """word,translation,example
bonjour,hello,Bonjour tout le monde
monde,world,Le monde est grand
"""
    vocab_file.write_text(vocab_content)

    # Generate Anki output
    anki_file = tmp_path / "anki_french-english.tsv"
    csv_handler.generate_anki_output_file(
        str(vocab_file), str(anki_file), "french", "english"
    )

    # Verify the deck name is for vocabulary
    content = anki_file.read_text()
    assert "#deck:French vocabulary" in content
    assert "#deck:French definitions" not in content


def test_prompt_generation_detects_mode_correctly(monkeypatch):
    """Test that the prompt generation system correctly detects and uses mode."""
    from vocabmaster import gpt_integration

    # Track which mode was used
    mode_used = {"value": None}
    original_format_prompt = gpt_integration.format_prompt

    def spy_format_prompt(language_to_learn, mother_tongue, words, mode="translation"):
        mode_used["value"] = mode
        return original_format_prompt(language_to_learn, mother_tongue, words, mode)

    monkeypatch.setattr(gpt_integration, "format_prompt", spy_format_prompt)

    # Mock the actual GPT request
    def fake_chatgpt_request(*args, **kwargs):
        return ("word\tdefinition\texample", 0.1, {})

    monkeypatch.setattr(gpt_integration, "chatgpt_request", fake_chatgpt_request)

    # Test same-language pair
    from vocabmaster import utils
    mode = utils.get_pair_mode("french", "french")
    prompt = gpt_integration.format_prompt("french", "french", ["test"], mode)

    assert mode == "definition"
    assert "definition" in prompt[1]["content"].lower()
    assert "translate" not in prompt[1]["content"].lower()

    # Test different-language pair
    mode = utils.get_pair_mode("french", "english")
    prompt = gpt_integration.format_prompt("french", "english", ["test"], mode)

    assert mode == "translation"
    assert "translate" in prompt[1]["content"].lower()
