# VocabMaster

Master new languages with this user-friendly CLI tool, designed to help you record vocabulary, access translations and examples, and seamlessly import them into Anki for an optimized language learning experience.

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

You can install VocabMaster using pip. The package includes all the required dependencies. Simply run the following command:

```
pip install vocabmaster
```

### Install via `pipx` (recommended)

`pipx` is an alternative package manager for Python applications. It allows you to install and run Python applications in isolated environments, preventing conflicts between dependencies and ensuring that each application uses its own set of packages. I recommend using `pipx` to install VocabMaster.

**First, install `pipx` if you haven't already:**

* On macOS and Linux:

  ```
  python3 -m pip install --user pipx
  python3 -m pipx ensurepath
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

### Shell Completion

To enable shell completion for bash or zsh, source the completion file (see the `completion` folder) related to your shell by adding the following line to your `.bashrc` or `.zshrc` file:

#### For bash:

```
source /path/to/vocabmaster/completion/_complete_vocabmaster.bash
```

#### For zsh:

```
source /path/to/vocabmaster/completion/_complete_vocabmaster.zsh
```

Remember to replace `/path/to/vocabmaster` with the actual path where VocabMaster is installed.

## Usage

Before using VocabMaster, you need to set up the OpenAI API key, which is required for the translations and usage examples. 
Follow the instructions provided within the CLI tool to configure the API key:

```
vocabmaster config key
```

Below is an example of common commands and their usage:

### Set up a new language pair:

```
vocabmaster setup
```

### Add words to your vocabulary list:

```
vocabmaster add to have
```

### Generate an Anki deck from your vocabulary list:

```
vocabmaster translate
```

### For detailed help on each command, run:

```
vocabmaster <command> --help
```

