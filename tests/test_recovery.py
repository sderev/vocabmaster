"""Tests for recovery module and backup validation."""

import csv
import os

import pytest

from vocabmaster import recovery, utils


class TestAtomicWriteCSV:
    """Test atomic CSV write operations."""

    def test_atomic_write_creates_file(self, tmp_path):
        """Atomic write creates file successfully."""
        from vocabmaster.csv_handler import atomic_write_csv

        output_file = tmp_path / "test.csv"

        def write_content(f):
            f.write("word,translation,example\n")
            f.write("hello,bonjour,Hello world\n")

        atomic_write_csv(output_file, write_content)

        assert output_file.exists()
        content = output_file.read_text()
        assert "word,translation,example" in content
        assert "hello,bonjour" in content

    def test_atomic_write_replaces_existing_file(self, tmp_path):
        """Atomic write replaces existing file content."""
        from vocabmaster.csv_handler import atomic_write_csv

        output_file = tmp_path / "test.csv"
        output_file.write_text("old content")

        def write_content(f):
            f.write("new content")

        atomic_write_csv(output_file, write_content)

        assert output_file.read_text() == "new content"

    def test_atomic_write_cleans_up_on_error(self, tmp_path):
        """Temp file is cleaned up if write fails."""
        from vocabmaster.csv_handler import atomic_write_csv

        output_file = tmp_path / "test.csv"
        output_file.write_text("original content")

        def write_that_fails(f):
            f.write("partial content")
            raise RuntimeError("Simulated write failure")

        with pytest.raises(RuntimeError):
            atomic_write_csv(output_file, write_that_fails)

        # Original file should be preserved
        assert output_file.read_text() == "original content"

        # No temp files should remain
        temp_files = list(tmp_path.glob(".csv_*.tmp"))
        assert len(temp_files) == 0

    def test_atomic_write_no_partial_content_on_interrupt(self, tmp_path):
        """File never contains partial content even on failure."""
        from vocabmaster.csv_handler import atomic_write_csv

        output_file = tmp_path / "test.csv"
        output_file.write_text("word,translation,example\nhello,bonjour,Hello\n")

        def write_partial_then_fail(f):
            f.write("word,translation,example\n")
            f.write("new_word,")  # Partial write
            raise RuntimeError("Interrupted!")

        with pytest.raises(RuntimeError):
            atomic_write_csv(output_file, write_partial_then_fail)

        # Original should be unchanged
        content = output_file.read_text()
        assert "hello,bonjour" in content
        assert "new_word" not in content


class TestValidateEntriesBeforeWrite:
    """Test pre-write validation function."""

    def test_valid_entries_pass(self):
        """Valid entries dictionary passes validation."""
        from vocabmaster.csv_handler import validate_entries_before_write

        entries = {
            "hello": {"word": "hello", "translation": "bonjour", "example": "Hello!"},
            "world": {"word": "world", "translation": "monde", "example": "World!"},
        }

        result = validate_entries_before_write(entries)

        assert result["valid"] is True
        assert result["entry_count"] == 2
        assert result["error"] is None

    def test_none_entries_fail(self):
        """None entries dictionary fails validation."""
        from vocabmaster.csv_handler import validate_entries_before_write

        result = validate_entries_before_write(None)

        assert result["valid"] is False
        assert "None" in result["error"]

    def test_empty_entries_fail(self):
        """Empty entries dictionary fails validation."""
        from vocabmaster.csv_handler import validate_entries_before_write

        result = validate_entries_before_write({})

        assert result["valid"] is False
        assert "No entries" in result["error"]

    def test_missing_required_keys_fail(self):
        """Entry missing required keys fails validation."""
        from vocabmaster.csv_handler import validate_entries_before_write

        entries = {
            "hello": {"word": "hello"},  # Missing translation and example
        }

        result = validate_entries_before_write(entries)

        assert result["valid"] is False
        assert "missing keys" in result["error"]

    def test_non_dict_entry_fails(self):
        """Non-dict entry value fails validation."""
        from vocabmaster.csv_handler import validate_entries_before_write

        entries = {
            "hello": "not a dict",
        }

        result = validate_entries_before_write(entries)

        assert result["valid"] is False
        assert "not a dictionary" in result["error"]


class TestBackupValidation:
    """Test backup validation functions."""

    def test_validate_parseable_valid_csv(self, tmp_path):
        """Valid CSV file passes validation."""
        backup_file = tmp_path / "backup.bak"
        backup_file.write_text(
            "word,translation,example\nhello,bonjour,Hello world\n",
            encoding="utf-8",
        )

        result = utils.validate_backup_parseable(backup_file)

        assert result["valid"] is True
        assert result["rows"] == 1
        assert result["error"] is None

    def test_validate_parseable_missing_columns(self, tmp_path):
        """CSV missing required columns fails validation."""
        backup_file = tmp_path / "backup.bak"
        backup_file.write_text(
            "word,other_col\nhello,value\n",
            encoding="utf-8",
        )

        result = utils.validate_backup_parseable(backup_file)

        assert result["valid"] is False
        assert "Missing required columns" in result["error"]

    def test_validate_parseable_nonexistent_file(self, tmp_path):
        """Nonexistent file fails validation."""
        result = utils.validate_backup_parseable(tmp_path / "nonexistent.bak")

        assert result["valid"] is False
        assert "does not exist" in result["error"]

    def test_get_format_version_3col_gpt_response(self, tmp_path):
        """Detect 3-col GPT response format."""
        backup_file = tmp_path / "gpt_request_timestamp.bak"
        backup_file.write_text(
            "hello\t'bonjour'\t\"Hello world\"\n",
            encoding="utf-8",
        )

        result = utils.get_backup_format_version(backup_file)

        assert result["version"] == "3-col"
        assert result["error"] is None

    def test_get_format_version_4col_gpt_response(self, tmp_path):
        """Detect 4-col GPT response format."""
        backup_file = tmp_path / "gpt_request_timestamp.bak"
        backup_file.write_text(
            "brethen\tbrethren\t'brothers'\t\"The brethren gather\"\n",
            encoding="utf-8",
        )

        result = utils.get_backup_format_version(backup_file)

        assert result["version"] == "4-col"
        assert result["error"] is None

    def test_get_format_version_csv_vocabulary(self, tmp_path):
        """Detect vocabulary CSV format."""
        backup_file = tmp_path / "vocab_list_en-fr_timestamp.bak"
        backup_file.write_text(
            "word,translation,example\nhello,bonjour,Hello\n",
            encoding="utf-8",
        )

        result = utils.get_backup_format_version(backup_file)

        assert result["version"] == "3-col"
        assert "word" in result["columns"]


class TestListBackups:
    """Test backup listing function."""

    def test_list_backups_empty_dir(self, tmp_path, fake_home, monkeypatch):
        """Empty backup directory returns empty list."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        backups = utils.list_backups("english", "french")

        assert backups == []

    def test_list_backups_finds_vocabulary(self, tmp_path, fake_home, monkeypatch):
        """List finds vocabulary backups."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        backup_dir = data_dir / ".backup" / "english-french"
        backup_dir.mkdir(parents=True)

        backup_file = backup_dir / "vocab_list_english-french_2024-01-01T12_00_00.bak"
        backup_file.write_text("word,translation,example\n")

        backups = utils.list_backups("english", "french")

        assert len(backups) == 1
        assert backups[0]["type"] == "vocabulary"
        assert backups[0]["filename"] == backup_file.name

    def test_list_backups_finds_gpt_response(self, tmp_path, fake_home, monkeypatch):
        """List finds GPT response backups."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        backup_dir = data_dir / ".backup" / "english-french"
        backup_dir.mkdir(parents=True)

        backup_file = backup_dir / "gpt_request_2024-01-01T12_00_00.bak"
        backup_file.write_text("hello\t'bonjour'\t\"Hello\"\n")

        backups = utils.list_backups("english", "french")

        assert len(backups) == 1
        assert backups[0]["type"] == "gpt-response"


class TestRestoreVocabulary:
    """Test vocabulary restoration functions."""

    def test_restore_from_valid_backup(self, tmp_path, fake_home, monkeypatch):
        """Restore from valid backup succeeds."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        # Create backup
        backup_dir = data_dir / ".backup" / "english-french"
        backup_dir.mkdir(parents=True)
        backup_file = backup_dir / "vocab_list_english-french_2024-01-01T12_00_00.bak"
        backup_file.write_text("word,translation,example\nhello,bonjour,Hello\n")

        # Create current file
        vocab_file = data_dir / "vocab_list_english-french.csv"
        vocab_file.write_text("word,translation,example\nworld,monde,World\n")

        result = recovery.restore_vocabulary_from_backup(backup_file, "english", "french")

        assert result["success"] is True
        assert result["restored_path"] == vocab_file
        assert result["pre_restore_backup"] is not None

        # Check content was restored
        content = vocab_file.read_text()
        assert "hello,bonjour" in content
        assert "world,monde" not in content

    def test_restore_creates_pre_restore_backup(self, tmp_path, fake_home, monkeypatch):
        """Restore creates backup of current file before overwriting."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        # Create backup
        backup_dir = data_dir / ".backup" / "english-french"
        backup_dir.mkdir(parents=True)
        backup_file = backup_dir / "vocab_list_english-french_2024-01-01T12_00_00.bak"
        backup_file.write_text("word,translation,example\nhello,bonjour,Hello\n")

        # Create current file
        vocab_file = data_dir / "vocab_list_english-french.csv"
        vocab_file.write_text("word,translation,example\nworld,monde,World\n")

        result = recovery.restore_vocabulary_from_backup(backup_file, "english", "french")

        assert result["pre_restore_backup"] is not None
        assert result["pre_restore_backup"].exists()

        # Pre-restore backup should contain old content
        pre_restore_content = result["pre_restore_backup"].read_text()
        assert "world,monde" in pre_restore_content

    def test_restore_fails_for_invalid_backup(self, tmp_path, fake_home, monkeypatch):
        """Restore fails if backup is not parseable."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        # Create invalid backup (missing columns)
        backup_dir = data_dir / ".backup" / "english-french"
        backup_dir.mkdir(parents=True)
        backup_file = backup_dir / "invalid.bak"
        backup_file.write_text("invalid,columns\n")

        result = recovery.restore_vocabulary_from_backup(backup_file, "english", "french")

        assert result["success"] is False
        assert "validation failed" in result["error"]

    def test_restore_fails_for_nonexistent_backup(self, tmp_path, fake_home, monkeypatch):
        """Restore fails if backup file doesn't exist."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        result = recovery.restore_vocabulary_from_backup(
            tmp_path / "nonexistent.bak", "english", "french"
        )

        assert result["success"] is False
        assert "does not exist" in result["error"]

    def test_restore_headerless_backup_migrates_to_csv(self, tmp_path, fake_home, monkeypatch):
        """Restore headerless TSV backup and migrate to CSV format."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        # Create headerless TSV backup (3-column legacy format)
        backup_dir = data_dir / ".backup" / "english-french"
        backup_dir.mkdir(parents=True)
        backup_file = backup_dir / "vocab_list_english-french_2024-01-01T12_00_00.bak"
        backup_file.write_text("hello\tbonjour\tHello world\ncat\tchat\tThe cat\n")

        result = recovery.restore_vocabulary_from_backup(backup_file, "english", "french")

        assert result["success"] is True
        assert result["restored_path"] is not None

        # Check content was migrated to proper CSV with headers
        content = result["restored_path"].read_text()
        assert "word,translation,example" in content
        assert "hello,bonjour,Hello world" in content
        assert "cat,chat,The cat" in content

    def test_restore_headerless_4col_backup_migrates(self, tmp_path, fake_home, monkeypatch):
        """Restore 4-column headerless backup (original_word, recognized_word, etc.)."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        # Create headerless TSV backup (4-column format)
        backup_dir = data_dir / ".backup" / "english-french"
        backup_dir.mkdir(parents=True)
        backup_file = backup_dir / "vocab_list_english-french_2024-01-01T12_00_00.bak"
        # original_word, recognized_word, translation, example
        backup_file.write_text("helo\thello\tbonjour\tHello world\n")

        result = recovery.restore_vocabulary_from_backup(backup_file, "english", "french")

        assert result["success"] is True

        # Check recognized_word is used as the canonical word
        content = result["restored_path"].read_text()
        assert "word,translation,example" in content
        assert "hello,bonjour,Hello world" in content
        assert "helo" not in content  # original typo should not appear


class TestValidateAllBackups:
    """Test bulk backup validation."""

    def test_validate_all_empty(self, tmp_path, fake_home, monkeypatch):
        """Validate returns empty results for no backups."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        result = recovery.validate_all_backups("english", "french")

        assert result["total"] == 0
        assert result["valid"] == 0
        assert result["invalid"] == 0

    def test_validate_all_with_mixed_backups(self, tmp_path, fake_home, monkeypatch):
        """Validate handles mixed valid/invalid backups."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        backup_dir = data_dir / ".backup" / "english-french"
        backup_dir.mkdir(parents=True)

        # Valid vocabulary backup
        valid_backup = backup_dir / "vocab_list_english-french_valid.bak"
        valid_backup.write_text("word,translation,example\nhello,bonjour,Hello\n")

        # Invalid vocabulary backup (wrong columns)
        invalid_backup = backup_dir / "vocab_list_english-french_invalid.bak"
        invalid_backup.write_text("wrong,columns,here\ndata,data,data\n")

        result = recovery.validate_all_backups("english", "french")

        assert result["total"] == 2
        assert result["valid"] == 1
        assert result["invalid"] == 1


class TestFormatMigration:
    """Test format migration functions."""

    def test_migrate_3col_gpt_response(self, tmp_path):
        """Migrate 3-col GPT response to 4-col format."""
        backup_file = tmp_path / "gpt_request_timestamp.bak"
        backup_file.write_text("hello\t'bonjour'\t\"Hello world\"\nworld\t'monde'\t\"The world\"\n")

        result = recovery.migrate_gpt_response_backup(backup_file)

        assert result["success"] is True
        assert result["original_format"] == "3-col"
        assert result["rows_migrated"] == 2

        # Check migrated content
        migrated_content = result["output_path"].read_text()
        lines = migrated_content.strip().split("\n")
        assert len(lines) == 2

        # First line should now have 4 columns
        cols = lines[0].split("\t")
        assert len(cols) == 4
        assert cols[0] == "hello"  # original_word
        assert cols[1] == "hello"  # recognized_word (same as original)
        assert cols[2] == "'bonjour'"  # translation
        assert cols[3] == '"Hello world"'  # example

    def test_migrate_already_4col_is_noop(self, tmp_path):
        """Migration of already 4-col file is a no-op."""
        backup_file = tmp_path / "gpt_request_timestamp.bak"
        backup_file.write_text("brethen\tbrethren\t'brothers'\t\"The brethren\"\n")

        result = recovery.migrate_gpt_response_backup(backup_file)

        assert result["success"] is True
        assert result["original_format"] == "4-col"
        assert result["rows_migrated"] == 0
        # Output path should be the original file (no new file created)
        assert result["output_path"] == backup_file

    def test_migrate_vocabulary_backup(self, tmp_path):
        """Migrate vocabulary backup normalizes format."""
        backup_file = tmp_path / "vocab_list_en-fr_timestamp.bak"
        backup_file.write_text("word,translation,example\nhello,bonjour,Hello\nworld,monde,World\n")

        result = recovery.migrate_vocabulary_backup(backup_file)

        assert result["success"] is True
        assert result["rows_migrated"] == 2

        # Check output is properly formatted
        with open(result["output_path"], "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["word"] == "hello"
        assert rows[0]["translation"] == "bonjour"

    def test_migrate_nonexistent_file_fails(self, tmp_path):
        """Migration of nonexistent file fails gracefully."""
        result = recovery.migrate_gpt_response_backup(tmp_path / "nonexistent.bak")

        assert result["success"] is False
        assert "does not exist" in result["error"]


class TestGetLatestBackup:
    """Test getting most recent backup."""

    def test_get_latest_with_no_backups(self, tmp_path, fake_home, monkeypatch):
        """Returns None when no backups exist."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        result = recovery.get_latest_backup("english", "french", "vocabulary")

        assert result is None

    def test_get_latest_returns_most_recent(self, tmp_path, fake_home, monkeypatch):
        """Returns most recent backup by modification time."""
        from vocabmaster import config_handler

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_handler.set_data_directory(data_dir)

        backup_dir = data_dir / ".backup" / "english-french"
        backup_dir.mkdir(parents=True)

        # Create older backup
        old_backup = backup_dir / "vocab_list_english-french_old.bak"
        old_backup.write_text("word,translation,example\nold,old,old\n")

        # Create newer backup
        new_backup = backup_dir / "vocab_list_english-french_new.bak"
        new_backup.write_text("word,translation,example\nnew,new,new\n")

        os.utime(old_backup, (1, 1))
        os.utime(new_backup, (2, 2))

        result = recovery.get_latest_backup("english", "french", "vocabulary")

        assert result is not None
        assert result["filename"] == new_backup.name


class TestFormatBackupTimestamp:
    """Test timestamp formatting."""

    def test_format_valid_timestamp(self):
        """Format valid ISO timestamp."""
        result = recovery.format_backup_timestamp("2024-01-15T14_30_45.123456")

        assert result == "2024-01-15 14:30:45"

    def test_format_invalid_timestamp(self):
        """Invalid timestamp returns original string."""
        result = recovery.format_backup_timestamp("not-a-timestamp")

        assert result == "not-a-timestamp"

    def test_format_empty_timestamp(self):
        """Empty timestamp returns empty string."""
        result = recovery.format_backup_timestamp("")

        assert result == ""
