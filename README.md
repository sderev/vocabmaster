# VocabMaster

CLI tool to record vocabulary and create Anki flashcards. Translations and example sentences are generated automatically.

![vocabmaster translate](assets/demos/03_translate.gif)

<!-- TOC -->
## Table of Contents

1. [Features](#features)
1. [Installation](#installation)
    1. [Prerequisites](#prerequisites)
    1. [Install via `pip`](#install-via-pip)
    1. [Install via `uv` (recommended)](#install-via-uv-recommended)
    1. [OpenAI API key](#openai-api-key)
    1. [Shell Completion](#shell-completion)
1. [Usage](#usage)
    1. [Add a new language pair](#add-a-new-language-pair)
    1. [Add words to your vocabulary list](#add-words-to-your-vocabulary-list)
    1. [Translate and generate an Anki deck](#translate-and-generate-an-anki-deck)
    1. [Estimate token usage](#estimate-token-usage)
    1. [Manage language pairs](#manage-language-pairs)
    1. [Check API key status](#check-api-key-status)
    1. [Choose where your files live](#choose-where-your-files-live)
    1. [Recover from backups](#recover-from-backups)
1. [Importing into Anki](#importing-into-anki)
1. [Licence](#licence)
<!-- /TOC -->

## Features

* Record vocabulary words
* Automatic translation and usage examples via OpenAI GPT
* Definition mode: same-language pairs (e.g., french:french) for definitions instead of translations
* Custom Anki deck names
* Backup and recovery
* Multiple languages

## Installation

### Prerequisites

* Python 3.10+
* Compatible with Windows, Linux, and macOS

### Install via `pip`

```
python3 -m pip install vocabmaster
```

### Install via `uv` (recommended)

```
uv tool install vocabmaster
```

### OpenAI API key

Vocabmaster requires an OpenAI API key to function. You can obtain a key by signing up for an account at [OpenAI's website](https://platform.openai.com/settings/organization/api-keys).

Once you have your API key, store it in `~/.config/lmt/key.env` (preferred) or set it as an environment variable. The `lmt` path is a shared convention with [`lmterminal`](https://github.com/sderev/lmterminal).

You can check whether VocabMaster finds your key with:

```
vocabmaster config key
```

* On macOS and Linux:

  ```bash
  mkdir -p ~/.config/lmt
  cat << 'EOF' > ~/.config/lmt/key.env
  OPENAI_API_KEY="your-api-key-here"
  EOF
  chmod 600 ~/.config/lmt/key.env
  ```

  The key file accepts `OPENAI_API_KEY=...`, `export OPENAI_API_KEY=...`, or a single bare key on its own line.

  To use an environment variable instead, add this to your shell configuration file (`.bashrc`, `.zshrc`, etc.):

  ```bash
  export OPENAI_API_KEY="your-api-key-here"
  ```

* On Windows:

  ```
  setx OPENAI_API_KEY your_key
  ```

### Shell Completion

To enable shell completion for bash or zsh, source the completion file (see the [`completion`](https://github.com/sderev/vocabmaster/tree/main/completion) folder) related to your shell by adding the following line to your `.bashrc` or `.zshrc` file:

#### For bash

```
source /path/to/vocabmaster/completion/_complete_vocabmaster.bash
```

#### For zsh

```
source /path/to/vocabmaster/completion/_complete_vocabmaster.zsh
```

Remember to replace `/path/to/vocabmaster` with the actual path where the completion file is located.

## Usage

Most commands accept a `--pair` option (e.g., `--pair spanish:english`) to target a specific language pair instead of the default.

### Add a new language pair

```
vocabmaster pairs add
```

![vocabmaster pairs add](assets/demos/01_pairs_add.gif)

#### Definition mode for same-language pairs

VocabMaster supports same-language pairs for getting definitions instead of translations.

For example, to create a French vocabulary list with definitions in French:

```
vocabmaster pairs add
# When prompted, enter: french (language to learn) and french (mother tongue)
```

When using same-language pairs:
* The LLM provides concise definitions (2-3 words) instead of translations
* Example sentences are in the target language
* Anki decks are named "{Language} definitions" instead of "{Language} vocabulary"

### Add words to your vocabulary list

```
vocabmaster add 猫
```

![vocabmaster add](assets/demos/02_add_word.gif)

### Translate and generate an Anki deck

`vocabmaster translate` fetches AI-generated translations and example sentences for pending words, then generates an Anki-ready CSV file:

```
vocabmaster translate
```

Check how many words are pending translation with `--count`:

```
vocabmaster translate --count
```

If your words are already translated and you only need to regenerate the Anki file (e.g., after editing the CSV by hand), use `anki` instead — it skips the API call:

```
vocabmaster anki
vocabmaster anki --pair spanish:english
```

### Estimate token usage

See the input-token count and estimated cost before running a translation:

```
vocabmaster tokens
vocabmaster tokens --pair japanese:english
```

### Manage language pairs

```
vocabmaster pairs list
vocabmaster pairs default
vocabmaster pairs set-default
vocabmaster pairs remove
vocabmaster pairs rename
vocabmaster pairs inspect --pair english:french
```

`pair` is accepted as an alias for `pairs` (e.g., `vocabmaster pair list`).

`default` shows the current default pair. `inspect` shows file locations, translation counts, and the estimated input-token cost (input tokens only) for a specific pair.

#### Custom deck names

Set a custom name for your Anki deck instead of using auto-generated names:

```
# Set a custom deck name
vocabmaster pairs set-deck-name --pair english:french --name "Business English"

# Interactive mode (prompts for pair selection and name)
vocabmaster pairs set-deck-name

# Remove custom name (revert to auto-generation)
vocabmaster pairs set-deck-name --pair english:french --remove
```

Once set, the custom deck name will be used automatically when generating Anki decks. You can also override it temporarily:

```
# Use custom name from config
vocabmaster anki --pair english:french

# Override with a different name for this generation only
vocabmaster anki --pair english:french --deck-name "Temporary Name"
```

The same `--deck-name` option works with the `translate` command.

### Check API key status

```
vocabmaster config key
```

Reports whether an OpenAI API key is found in `~/.config/lmt/key.env` or the `OPENAI_API_KEY` environment variable.

### Choose where your files live

```
vocabmaster config dir --show
vocabmaster config dir ~/Documents/vocabmaster
```

Use `--show` to print your current storage directory. Vocabulary CSV and Anki decks default to `~/.vocabmaster`, but you can relocate them anywhere under your home directory. The configuration file itself always stays under `~/.config/vocabmaster/config.json`.

### Recover from backups

VocabMaster automatically creates backups before modifying your vocabulary files. Use the `recover` command group to list, validate, or restore from these backups.

```
# List available backups
vocabmaster recover list
vocabmaster recover list --pair spanish:english

# Restore from the most recent backup
vocabmaster recover restore --latest

# Restore a specific backup (use the ID from 'recover list')
vocabmaster recover restore --backup-id 3

# Validate backup integrity
vocabmaster recover validate
```

### For detailed help on each command, run

```
vocabmaster <command> --help
```

## Importing into Anki

To import the vocabulary deck into Anki, follow the steps below:

1. Launch Anki.
1. Click on the `Import File` button. This will open a file picker dialog.
1. In the file picker, locate and select the `anki_deck_language1-language2.csv` file.
1. Ensure the `Existing notes` field is set to *Update*. This will prevent the creation of duplicate cards if the same note already exists in your deck.

## Licence

VocabMaster is released under the [Apache Licence version 2](LICENSE).

___

<https://github.com/sderev/vocabmaster>
