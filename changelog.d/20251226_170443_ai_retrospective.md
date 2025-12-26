Added
-----
* Recovery CLI commands (`vocabmaster recover list`, `recover restore`, `recover validate`) for data restoration from backups
* Atomic CSV writes to prevent data corruption during file operations
* Same-language definition mode for monolingual vocabulary study
* Custom Anki deck naming via `vocabmaster config deck-name` command
* CLI support for removing language pairs (`pairs remove`)
* Configurable vocabulary storage directory (`config dir`)
* `--show` option for `config dir` commands to display current paths
* Pre-operation validation before CSV operations
* Format migration support in recovery module

Changed
-------
* Redirect all error and warning output to stderr for cleaner CLI experience
* Require Python 3.10+ (dropped support for older versions)
* Improve CLI help messages and docstrings
* Remove decorative emojis from CLI output

Fixed
-----
* Prompt injection vulnerability in LLM prompts
* Path traversal vulnerability in language pair names
* CSV header validation bug in `get_words_to_translate`
* Blank `recognized_word` detection
* Backward compatibility for 3-column TSV format
* Exit code handling when no subcommand is provided
* Anki export now retains first vocabulary row

Security
--------
* Prevent API key leakage in `chatgpt_request` error handling
* Add data validation and security infrastructure against corruption and injection
* Add input validation in CLI to prevent corruption and injection attacks
