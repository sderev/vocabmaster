# VocabMaster

Master new languages with this CLI tool, designed to help you record vocabulary and create Anki flashcards without the need to manually input translations or example sentences.

![vocabmaster_translate_japanese](https://github.com/sderev/vocabmaster/assets/24412384/d2196f6a-3094-40dd-9b2f-3caffd8ba3dd)

<!-- TOC -->
## Table of Contents

1. [Features](#features)
1. [Installation](#installation)
    1. [Prerequisites](#prerequisites)
    1. [Install via pip](#install-via-pip)
    1. [Install via pipx (recommended)](#install-via-pipx-recommended)
    1. [Shell Completion](#shell-completion)
1. [Usage](#usage)
    1. [Set up a new language pair](#set-up-a-new-language-pair)
    1. [Add words to your vocabulary list](#add-words-to-your-vocabulary-list)
    1. [Generate an Anki deck from your vocabulary list](#generate-an-anki-deck-from-your-vocabulary-list)
    1. [For detailed help on each command, run](#for-detailed-help-on-each-command-run)
1. [Licence](#licence)
<!-- /TOC -->

## Features

* Record vocabulary words with ease
* Automatic translation and usage examples via OpenAI GPT
* Anki integration for seamless language learning
* Supports multiple languages

## Installation

### Prerequisites

* Python 3.8 or higher
* Compatible with Windows, Linux, and macOS

### Install via pip

You can install VocabMaster using pip. Simply run the following command:

```
python3 -m pip install vocabmaster
```

### Install via pipx (recommended)

[`pipx`](https://pypi.org/project/pipx/) is an alternative package manager for Python applications. It allows you to install and run Python applications in isolated environments, preventing conflicts between dependencies and ensuring that each application uses its own set of packages. I recommend using `pipx` to install VocabMaster.

**First, install `pipx` if you haven't already:**

* On macOS and Linux:

  ```
  python3 -m pip install --user pipx
  pipx ensurepath
  ```

Alternatively, you can use your package manager (`brew`, `apt`, etc.).

* On Windows:

  ```
  py -m pip install --user pipx
  py -m pipx ensurepath
  ```

**Once `pipx` is installed, you can install VocabMaster using the following command:**

```
pipx install vocabmaster
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

Before using VocabMaster, you need to set up the OpenAI API key, which is required for the translations and usage examples. 

Follow the instructions provided within the CLI tool to configure the API key:

```
vocabmaster config key
```

Below is an example of common commands and their usage:

### Set up a new language pair

```
vocabmaster setup
```

![vocabmaster_setup](https://github.com/sderev/vocabmaster/assets/24412384/88742afa-fdc4-4808-b106-493b3c0afa8d)

### Add words to your vocabulary list

```
vocabmaster add la casa
```

![vocabmaster_add](https://github.com/sderev/vocabmaster/assets/24412384/fb566562-f96c-418e-b2bb-cdb603d08aef)

### Generate an Anki deck from your vocabulary list

```
vocabmaster translate
```

![vocabmaster_translate](https://github.com/sderev/vocabmaster/assets/24412384/63e5423a-6f1b-4452-aefd-dd15444cb8df)

### For detailed help on each command, run

```
vocabmaster <command> --help
```

## Importing into Anki

To import the vocabulary deck into Anki, follow the steps below:

1. Launch Anki.
1. Click on the `Import File` button. This will open a file picker dialog.
1. In the file picker, locate and select the `anki_deck_language1-language2.csv` file.
1. When prompted for the field separator, use "semicolon" (this should be set as the default in Anki).
1. Ensure that the *Allow HTML in fields* option is selected. This allows the app to correctly interpret any HTML formatting in your card fields.
1. In the import options, choose *Basic (and reversed card)* for the `Note type` field.
1. Select the name of your vocabulary deck in which you want the cards to be added.
1. For the `Existing notes` field, choose *Update*. This will prevent the creation of duplicate cards if the same note already exists in your deck.

These instructions will ensure your imported cards appear correctly in your Anki deck.

Remember that the naming scheme `anki_deck_language1-language2.csv` is an example, replace `language1` and `language2` with the appropriate languages you're learning and the deck corresponds to.

## Licence

VocabMaster is released under the [Apache Licence version 2](LICENSE).

___

<https://github.com/sderev/vocabmaster>
