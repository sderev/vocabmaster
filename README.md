# VocabMaster

Master new languages with this CLI tool, designed to help you record vocabulary and create Anki flashcards without the need to manually input translations or example sentences.

![vocabmaster_translate_japanese](https://github.com/sderev/vocabmaster/assets/24412384/d2196f6a-3094-40dd-9b2f-3caffd8ba3dd)

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
        1. [Definition mode for same-language pairs](#definition-mode-for-same-language-pairs)
    1. [Add words to your vocabulary list](#add-words-to-your-vocabulary-list)
    1. [Manage language pairs](#manage-language-pairs)
    1. [Generate an Anki deck from your vocabulary list](#generate-an-anki-deck-from-your-vocabulary-list)
    1. [Choose where your files live](#choose-where-your-files-live)
    1. [For detailed help on each command, run](#for-detailed-help-on-each-command-run)
1. [Importing into Anki](#importing-into-anki)
1. [Licence](#licence)
<!-- /TOC -->

## Features

* Record vocabulary words with ease
* Automatic translation and usage examples via OpenAI GPT
* Definition mode: use same-language pairs (e.g., french:french) to get concise definitions instead of translations
* Anki integration for seamless language learning
* Supports multiple languages

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

Vocabmaster requires an OpenAI API key to function. You can obtain a key by signing up for an account at [OpenAI's website](https://platform.openai.com/account/api-keys).

Once you have your API key, set it as an environment variable:

* On macOS and Linux:

  ```bash
  export OPENAI_API_KEY="your-api-key-here"
  ```

  To avoid having to type it everyday, you can create a file with the key:

  ```bash
  echo "your-api-key" > ~/.openai-api-key.txt
  ```

  **Note:** Remember to replace `"your-api-key"` with your actual API key.

  And then, you can add this to your shell configuration file (`.bashrc`, `.zshrc`, etc.):

    ```bash
    export OPENAI_API_KEY="$(cat ~/.openai-api-key.txt)"
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

### Add a new language pair

```
vocabmaster pairs add
```

![vocabmaster_setup](https://github.com/sderev/vocabmaster/assets/24412384/88742afa-fdc4-4808-b106-493b3c0afa8d)

#### Definition mode for same-language pairs

VocabMaster supports same-language pairs for getting definitions instead of translations. This is useful when you want to learn more advanced vocabulary in a language you're already studying.

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
vocabmaster add la casa
```

![vocabmaster_add](https://github.com/sderev/vocabmaster/assets/24412384/fb566562-f96c-418e-b2bb-cdb603d08aef)

### Manage language pairs

```
vocabmaster pairs list
vocabmaster pairs set-default
vocabmaster pairs remove
vocabmaster pairs rename
vocabmaster pairs inspect --pair english:french
```

`inspect` shows file locations, translation counts, and the estimated input-token cost (input tokens only) for a specific pair.

### Generate an Anki deck from your vocabulary list

```
vocabmaster translate
```

![vocabmaster_translate](https://github.com/sderev/vocabmaster/assets/24412384/63e5423a-6f1b-4452-aefd-dd15444cb8df)

Generate a deck for a specific pair with:

```
vocabmaster anki --pair spanish:english
```

### Choose where your files live

```
vocabmaster config dir --show
vocabmaster config dir ~/Documents/vocabmaster
```

Use `--show` to print your current storage directory. Vocabulary CSV and Anki decks default to `~/.vocabmaster`, but you can relocate them anywhere. The configuration file itself always stays under `~/.config/vocabmaster/config.json`.

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
