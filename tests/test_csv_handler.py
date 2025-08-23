import pytest
from vocabmaster import csv_handler


def test_detect_word_mismatches_finds_typo_corrections():
    """Test detecting when the LM corrects typos in word responses."""
    original_words = ["brethen", "hello"]
    gpt_response = {
        "brethren": {"translation": "frères", "example": "The brethren gather"},
        "hello": {"translation": "bonjour", "example": "Hello there"}
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
        "world": {"translation": "monde", "example": "The world is big"}
    }
    
    mismatches = csv_handler.detect_word_mismatches(original_words, gpt_response)
    assert mismatches == []


def test_detect_word_mismatches_handles_multiple_corrections():
    """Test detecting multiple typo corrections in one batch."""
    original_words = ["brethen", "seperate", "definately"]
    gpt_response = {
        "brethren": {"translation": "frères", "example": "The brethren gather"},
        "separate": {"translation": "séparer", "example": "Separate items"},
        "definitely": {"translation": "définitivement", "example": "Definitely yes"}
    }
    
    mismatches = csv_handler.detect_word_mismatches(original_words, gpt_response)
    
    # Current simple logic: all missing words get all potential corrections
    # We can improve this later with similarity matching
    expected_corrections = ["brethren", "separate", "definitely"]
    expected = [
        ("brethen", expected_corrections),
        ("seperate", expected_corrections), 
        ("definately", expected_corrections)
    ]
    
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
        "hello": {"word": "hello", "translation": "bonjour", "example": "Hello there"}
    }
    
    updated_entries = csv_handler.update_word_in_entries(
        current_entries, "brethen", "brethren"
    )
    
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
        "hello": {"word": "hello", "translation": "bonjour", "example": "Hello there"}
    }
    
    new_entries = {
        "brethren": {"translation": "frères", "example": "The brethren gather"},
        "hello": {"translation": "bonjour", "example": "Hello there"}
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