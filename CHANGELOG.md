# Changelog

All notable changes to this project will be documented in this file.

For versions before 0.2.0, see [GitHub Releases](https://github.com/sderev/vocabmaster/releases).

<!-- scriv-insert-here -->

<a id='changelog-0.3.0'></a>
## 0.3.0 - 2026-02-19

Added
-----
* Recovery CLI commands (`vocabmaster recover list`, `recover restore`, `recover validate`) for data restoration from backups.
* Atomic CSV writes to prevent data corruption during file operations.
* Same-language definition mode for monolingual vocabulary study.
* Custom Anki deck naming via `vocabmaster pairs set-deck-name` command.
* CLI support for removing language pairs (`pairs remove`).
* CLI support for renaming language pairs (`pairs rename`).
* Vocabulary statistics via `pairs inspect`.
* Configurable vocabulary storage directory (`config dir`).
* `--show` option for `config dir` commands to display current paths.
* Pre-operation validation before CSV operations.
* Format migration support in recovery module.
* Command aliasing: `pair` accepted as alias for `pairs`.
* Vocabulary files are backed up before translation runs.

Changed
-------
* Restructured CLI into `pairs` command group with subcommands (`list`, `add`, `set-default`, `remove`, `rename`, `inspect`); removed deprecated top-level commands (`setup`, `default`, `show`).
* Switched OpenAI integration to the Responses API with streaming.
* Read OpenAI API keys from `~/.config/lmt/key.env` before environment variables.
* Defaulted the translation model to `gpt-5.2`; updated token cost estimation to per-million pricing with support for `gpt-4.1`, `gpt-4o`, `o1`, `o3`, and `gpt-5` model families.
* Removed `/opt` from the list of allowed data directory locations. User data directories under the home directory are sufficient for all normal use cases.
* Redirected all error and warning output to stderr for cleaner CLI experience.
* Require Python 3.10+ (dropped support for older versions).
* Improved CLI help messages and docstrings.
* Removed decorative emojis from CLI output.
* Parsing warnings now include line numbers, the offending word, and a failure summary.

Fixed
-----
* Raised OpenAI errors for non-200 streaming responses.
* Filtered streaming output to skip `recognized_word` tokens.
* Blocked `translate` when vocabulary CSV files contain duplicate words, with line numbers to resolve issues.
* Ignored header rows in `word_exists` so the literal word `word` can be added when a header is present.
* Normalized header detection in `ensure_csv_has_fieldnames` to avoid duplicate headers with BOM or case variants.
* Pointed missing default-pair errors to `vocabmaster pairs add` and `vocabmaster pairs set-default`.
* Fixed a home-directory containment check in `validate_data_directory` that could pass for paths like `/home/userfoo` when the configured home is `/home/user`. Now uses `Path.relative_to` instead of a string prefix comparison.
* Fixed CSV header validation bug in `get_words_to_translate`.
* Fixed blank `recognized_word` detection.
* Restored backward compatibility for 3-column TSV format.
* Fixed exit code handling when no subcommand is provided.
* Fixed Anki export to retain the first vocabulary row.

Security
--------
* Pinned `urllib3>=2.6.3` to address CVE-2026-21441 (decompression bomb in streaming API). `urllib3` is a transitive dependency via `scriv`; risk is limited to dev tooling.
* Fixed prompt injection vulnerability in LLM prompts.
* Fixed path traversal vulnerability in language pair names.
* Prevented API key leakage in `chatgpt_request` error handling.
* Blocked CSV injection patterns (DDE, cell references, formula-like values) in `sanitize_csv_value`.
* Added CLI input validation for language pair names and file paths to prevent corruption and injection.
