Fixed
-----
* Ignored header rows in `word_exists` so the literal word `word` can be added when a header is present.
* Normalized header detection in `ensure_csv_has_fieldnames` to avoid duplicate headers with BOM or case variants.
