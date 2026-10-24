# Contribute a translation

FPGALab discovers interface languages from `fpga_lab/locales/*.json`. Adding a
catalog does not require Python code changes. English is the fallback language;
partial translations are welcome. This workflow translates the application,
not the documentation website.

## Create a catalog

Run from the root of a source checkout, with Python 3.10+ (Qt is not needed
for these tools):

```text
python -m fpga_lab.locale_tools template --code fr --name Français --output fpga_lab/locales/fr.json
```

Use the command that launches Python 3 on your system: replace `python` with
`python3` on Linux/macOS or `py -3` on Windows if necessary.

Use an ISO language code such as `fr`, or a regional locale such as `pt_BR`.
The command creates the file directly in the application's source catalog
folder, `fpga_lab/locales/`, not in the installed executable's folder. The
filename must match the code. Existing files are not overwritten.

```json
{
  "_meta": {
    "code": "fr",
    "name": "Français",
    "contributors": ["Your name or handle"]
  },
  "Open {path}": ""
}
```

`name` is the language's native name; `contributors` optionally credits people
who actually translated or reviewed this catalog. Do not automatically credit
project maintainers or unrelated contributors. Additional translators can append
their names later.

## Translate safely

- Edit the **values**, not the English keys. Leave unfinished values empty or
  omit them; the interface uses English for those entries.
- Preserve placeholders exactly, including formatting: `{path}`, `{count}`,
  `{value:.1f}`. They may be reordered, but not renamed, added or reformatted.
- Preserve Markdown/HTML markup and useful keyboard mnemonics (`&`) where used.
  JSON strings encode newlines as `\n` and quotes as `\"`.
- Save UTF-8 JSON, without comments, duplicate keys or trailing commas.

Validate from the repository root:

```bash
python -m fpga_lab.locale_tools validate
```

The report shows coverage; incompleteness is not an error. Invalid metadata,
unknown keys, malformed JSON and mismatched parameters fail validation and CI.
The runtime skips damaged catalog files and falls back to English for invalid
individual entries rather than blocking application startup.

Restart a source run to discover a new file, then choose the language from the
top-bar selector. The popup shows native names; the closed selector stays compact.
Selection is remembered, and existing live-translated controls update when the
language changes. Test dialogs, long labels and both themes. Right-to-left locale
direction follows Qt. Standard Qt buttons use bundled `qtbase` translations,
including a base-language fallback for regional locales; if Qt supplies none,
those standard strings remain in English.

Submit a pull request containing the catalog. Distributed packages include the
new language after rebuilding; editing a separate user folder does not install
a language. Documentation translations can be proposed separately.

## Maintain the English reference

When adding `t("English text")` strings or bundled peripheral labels, run:

```bash
python -m fpga_lab.locale_tools update-source
python -m fpga_lab.locale_tools validate
```

`en.json` is the reference for template generation and validation, not a second
translation of English. The updater preserves existing keys, including dynamic
strings. Add new dynamic keys that cannot be extracted to that reference using
the same English key and value. Do not rewrite other languages or require their
completion when adding a feature.
