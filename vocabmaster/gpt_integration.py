import os
import time

import openai
import tiktoken


def format_prompt(
    language_to_learn, mother_tongue, words_to_translate, mode="translation"
):
    """
    Generate a prompt for translation or definition mode.

    Args:
        language_to_learn (str): Target language.
        mother_tongue (str): User's mother tongue.
        words_to_translate (list): List of words to process.
        mode (str): "translation" or "definition" mode.

    Returns:
        list: Formatted prompt messages for the LLM.
    """
    words_to_translate = "\n".join(words_to_translate)

    if mode == "definition":
        prompt = [
            {
                "role": "system",
                "content": """
                You are an expert at building vocabulary lists and formatting them as Tab-Separated Values TSV file.
                You do NOT say anything else but the content of the TSV file.""",
            },
            {
                "role": "user",
                "content": f"""
                Provide definitions for the following {language_to_learn} words
                and create a TSV file with each row consisting of the {language_to_learn} word,
                a definition, and an example sentence in {language_to_learn}.

                Always give ONLY ONE example! The example HAS TO BE in {language_to_learn}!
                Separate each column with a tab character.
                For the definition column, provide a brief, clear definition.

                When you start a new row, you HAVE TO add a newline character.
                The format should look like this:
                word\tdefinition\texample sentence in {language_to_learn}

                Below is the list of words.
                ---
                {words_to_translate}""",
            },
        ]
    else:  # translation mode
        prompt = [
            {
                "role": "system",
                "content": """
                You are an expert at building vocabulary lists and formatting them as Tab-Separated Values TSV file.
                You do NOT say anything else but the content of the TSV file.""",
            },
            {
                "role": "user",
                "content": f"""
                Translate the following {language_to_learn} words into {mother_tongue}
                and provide a TSV file with each row consisting of the {language_to_learn} word,
                its {mother_tongue} translations (if there are multiple translations possible,
                list them in the same column), and an example sentence in {language_to_learn}.

                Always give ONLY ONE example! The example HAS TO BE in {language_to_learn}!
                Separate each column with a tab character.
                For the translation column, ALWAYS give at least two or three possible translations!

                When you start a new row, you HAVE TO add a newline character.
                The format should look like this:
                word\ttranslation1, translation2, translation3\texample sentence in {language_to_learn}

                Below is the list of words to translate.
                ---
                {words_to_translate}""",
            },
        ]
    return prompt


def chatgpt_request(
    prompt,
    model="gpt-4.1",
    # max_tokens=3600,
    n=1,
    temperature=0.7,
    stop=None,
    stream=False,
):
    start_time = time.monotonic_ns()
    openai.api_key = os.getenv("OPENAI_API_KEY")

    # Make the API request
    response = openai.ChatCompletion.create(
        messages=prompt,
        model=model,
        # max_tokens=max_tokens,
        n=n,
        temperature=temperature,
        stop=stop,
        stream=stream,
    )

    if stream:
        # Create variables to collect the stream of chunks
        collected_chunks = []
        collected_messages = []

        # Iterate through the stream of events
        for chunk in response:
            collected_chunks.append(chunk)  # save the event response
            chunk_message = chunk["choices"][0]["delta"]  # extract the message
            collected_messages.append(chunk_message)  # save the message
            print(chunk_message.get("content", ""), end="")  # stream the message
        print()
        response = collected_chunks

        # Save the time delay and text received
        response_time = (time.monotonic_ns() - start_time) / 1e9
        generated_text = "".join([m.get("content", "") for m in collected_messages])

    else:
        # Extract and save the generated response
        generated_text = response["choices"][0]["message"]["content"]

        # Save the time delay
        response_time = (time.monotonic_ns() - start_time) / 1e9

    return (
        generated_text,
        response_time,
        response,
    )


def num_tokens_from_string(string, model="gpt-4.1"):
    """Returns the number of tokens in a text string."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(string))
    return num_tokens


def num_tokens_from_messages(messages, model="gpt-4.1"):
    """Returns the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    # Use default token overhead for modern models (cl100k_base encoding)
    tokens_per_message = 3
    tokens_per_name = 1

    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens


def estimated_cost(num_tokens, price_per_1M_tokens):
    """Returns the estimated cost of a number of tokens."""
    return f"{num_tokens / 10**6 * price_per_1M_tokens:.6f}"


def estimate_prompt_cost(message, model):
    """
    Returns the estimated cost of a prompt for a specific model.

    Args:
        message: The message(s) to estimate cost for
        model: The model name to use for pricing

    Returns:
        str or None: Formatted cost string if pricing is available, None otherwise
    """
    num_tokens = num_tokens_from_messages(message, model)

    # Prices in USD per 1M input tokens
    prices = {
        "gpt-3.5-turbo": 0.50,
        "gpt-3.5-turbo-0125": 0.50,
        "gpt-3.5-turbo-1106": 0.50,
        "gpt-3.5-turbo-instruct": 1.50,
        "gpt-4": 30,
        "gpt-4-turbo-preview": 10,
        "gpt-4-turbo": 10,
        "gpt-4-turbo-2024-04-09": 0.01,
        "gpt-4-0613": 0.03,
        "gpt-4-1106-preview": 10,
        "gpt-4-0125-preview": 10,
        "gpt-4-32k": 60,
        "gpt-4-32k-0613": 60,
        "gpt-4o": 2.50,
        "gpt-4o-2024-05-13": 5,
        "gpt-4o-2024-08-06": 2.50,
        "gpt-4o-2024-11-20": 2.50,
        "gpt-4o-mini": 0.15,
        "gpt-4o-mini-2024-07-18": 0.15,
        "chatgpt-4o-latest": 5,
        "o1": 15,
        "o1-2024-12-17": 15,
        "o1-preview": 15,
        "o1-preview-2024-09-12": 15,
        "o1-mini": 1.10,
        "o1-mini-2024-09-12": 1.10,
        "gpt-4.1": 2,
        "gpt-4.1-2025-04-14": 2,
        "gpt-4.1-mini": 0.40,
        "gpt-4.1-mini-2025-04-14": 0.40,
        "gpt-4.1-nano": 0.1,
        "gpt-4.1-nano-2025-04-14": 0.10,
        "gpt-4.5-preview": 75,
        "o3": 2,
        "o3-2025-04-16": 2,
        "o3-mini": 1.10,
        "o3-mini-2025-01-31": 1.10,
        "o4-mini": 1.10,
        "o4-mini-2025-04-16": 1.10,
        "gpt-5": 1.25,
        "gpt-5-mini": 0.25,
        "gpt-5-nano": 0.05,
        "gpt-5-chat-latest": 1.25,
    }

    if model in prices:
        return estimated_cost(num_tokens, prices[model])
    return None
