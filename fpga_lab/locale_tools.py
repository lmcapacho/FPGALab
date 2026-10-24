"""Generate and validate contributor translations without importing Qt."""

import argparse
import ast
import json
from pathlib import Path

from .locale_catalog import CODE_PATTERN, LOCALES_DIR, LocaleCatalog, valid_translation


def source_messages(root=None):
    root = root or Path(__file__).parent
    messages = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t" and
                    node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                messages.add(node.args[0].value)
    for path in (root / "peripherals").glob("*/manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for field in ("label", "description"):
            if manifest.get(field):
                messages.add(manifest[field])
        for schema in manifest.get("properties", {}).values():
            if schema.get("label"):
                messages.add(schema["label"])
    return messages


def write_catalog(path, code, name, messages, *, overwrite=False):
    if not CODE_PATTERN.fullmatch(code) or not name.strip():
        raise ValueError("Use a locale code such as fr or pt_BR and its native language name")
    data = {"_meta": {"code": code, "name": name, "contributors": []}, **messages}
    with Path(path).open("w" if overwrite else "x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def update_source(directory=LOCALES_DIR):
    # Retain legacy/dynamic keys rather than deleting contributors' translations.
    reference = directory / "en.json"
    existing = reference if reference.exists() else directory / "es.json"
    keys = source_messages() | set(LocaleCatalog.load(existing, require_metadata=False).messages)
    write_catalog(reference, "en", "English", {key: key for key in sorted(keys)}, overwrite=True)
    return len(keys)


def validate(directory=LOCALES_DIR, *, check_source=True):
    errors, reports = [], []
    try:
        english = LocaleCatalog.load(directory / "en.json")
    except (OSError, ValueError) as error:
        return [f"en.json: {error}"], reports
    keys = set(english.messages)
    if check_source:
        missing = source_messages() - keys
        if missing:
            errors.append(f"English reference is missing {len(missing)} source strings; run update-source")
    for path in sorted(directory.glob("*.json")):
        try:
            catalog = LocaleCatalog.load(path)
        except (OSError, ValueError) as error:
            errors.append(f"{path.name}: {error}")
            continue
        for key, value in catalog.messages.items():
            if key not in keys:
                errors.append(f"{path.name}: unknown source key: {key}")
            elif value and not valid_translation(key, value):
                errors.append(f"{path.name}: invalid placeholders/formatting: {key}")
            elif catalog.code == "en" and value != key:
                errors.append(f"{path.name}: English reference values must match their keys: {key}")
        count = sum(bool(value.strip()) for key, value in catalog.messages.items() if key in keys)
        reports.append(f"{path.name}: {count}/{len(keys)} translated; missing/empty entries use English")
    return errors, reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    commands.add_parser("update-source")
    template = commands.add_parser("template")
    template.add_argument("--code", required=True)
    template.add_argument("--name", required=True, help="Native language name")
    template.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "update-source":
        print(f"Updated English reference: {update_source()} strings")
    elif args.command == "template":
        keys = LocaleCatalog.load(LOCALES_DIR / "en.json").messages
        write_catalog(args.output, args.code, args.name, {key: "" for key in keys})
        print(f"Created {args.output}; translate values, not English keys")
    else:
        errors, reports = validate()
        print("\n".join(reports + errors))
        raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
