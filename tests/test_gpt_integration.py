from vocabmaster import gpt_integration


def test_format_prompt_translation_mode():
    """Test prompt generation for translation mode (different languages)."""
    words = ["hello", "world"]
    prompt = gpt_integration.format_prompt("french", "english", words, mode="translation")

    # Verify structure
    assert len(prompt) == 2
    assert prompt[0]["role"] == "system"
    assert prompt[1]["role"] == "user"

    # Verify content mentions translations
    user_content = prompt[1]["content"]
    assert "Translate the following french words into english" in user_content
    assert "provide a TSV file where each row contains exactly four columns" in user_content
    assert "translations — list at least two or three" in user_content
    assert "original_word\trecognized_word" in user_content

    # Verify words are included
    assert "hello" in user_content
    assert "world" in user_content

    # Verify format specification (check for the pattern without escaping)
    assert (
        "original_word\trecognized_word\ttranslation1, translation2, ...\texample sentence in french"
        in user_content
    )


def test_format_prompt_definition_mode():
    """Test prompt generation for definition mode (same language)."""
    words = ["bonjour", "monde"]
    prompt = gpt_integration.format_prompt("french", "french", words, mode="definition")

    # Verify structure
    assert len(prompt) == 2
    assert prompt[0]["role"] == "system"
    assert prompt[1]["role"] == "user"

    # Verify content mentions definitions
    user_content = prompt[1]["content"]
    assert "Provide concise definitions for the following french words" in user_content
    assert "original_word\trecognized_word\tdefinition" in user_content
    assert "example sentence in french" in user_content

    # Verify it does NOT mention translations
    assert "translate" not in user_content.lower()
    assert "translation" not in user_content.lower()

    # Verify words are included
    assert "bonjour" in user_content
    assert "monde" in user_content

    # Verify format specification (check for the pattern without escaping)
    assert "word\tdefinition\texample sentence in french" in user_content


def test_format_prompt_default_mode_is_translation():
    """Test that mode parameter defaults to translation."""
    words = ["hello"]
    prompt_default = gpt_integration.format_prompt("french", "english", words)
    prompt_explicit = gpt_integration.format_prompt("french", "english", words, mode="translation")

    # Both should be identical
    assert prompt_default == prompt_explicit
    assert "Translate" in prompt_default[1]["content"]


def test_format_prompt_multiple_words():
    """Test prompt generation with multiple words."""
    words = ["apple", "banana", "cherry", "date"]
    prompt = gpt_integration.format_prompt("spanish", "english", words, mode="translation")

    user_content = prompt[1]["content"]

    # Verify all words are included
    for word in words:
        assert word in user_content


def test_format_prompt_system_message_consistent():
    """Test that system message is consistent across modes."""
    words = ["test"]

    prompt_translation = gpt_integration.format_prompt(
        "french", "english", words, mode="translation"
    )
    prompt_definition = gpt_integration.format_prompt("french", "french", words, mode="definition")

    # System messages should be identical
    assert prompt_translation[0]["role"] == "system"
    assert prompt_definition[0]["role"] == "system"
    assert prompt_translation[0]["content"] == prompt_definition[0]["content"]

    # Verify system message content
    system_content = prompt_translation[0]["content"]
    assert "vocabulary lists" in system_content
    assert "Tab-Separated Values" in system_content or "TSV" in system_content
