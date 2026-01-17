Changed
-------
* Switched OpenAI integration to the Responses API with streaming.
* Read OpenAI API keys from `~/.config/lmt/key.env` before environment variables.

Fixed
-----
* Raised OpenAI errors for non-200 streaming responses.
