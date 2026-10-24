"""Pure-data locale catalogs shared by the runtime and contributor tools."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
from string import Formatter


LOCALES_DIR = Path(__file__).parent / "locales"
CODE_PATTERN = re.compile(r"[a-z]{2,3}(?:_[A-Za-z0-9]{2,8})*")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def placeholders(text):
    fields = set()
    for _, field, spec, conversion in Formatter().parse(text):
        if field is not None:
            fields.add((field, spec, conversion))
            fields.update(placeholders(spec))
    return fields


def valid_translation(source, translated):
    try:
        return isinstance(translated, str) and placeholders(source) == placeholders(translated)
    except (ValueError, RecursionError):
        return False


@dataclass(frozen=True)
class LocaleCatalog:
    code: str
    name: str
    contributors: tuple[str, ...]
    messages: dict[str, str]

    @classmethod
    def load(cls, path, *, require_metadata=True):
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(data, dict) or not CODE_PATTERN.fullmatch(path.stem):
            raise ValueError("Expected a locale-named JSON object")
        metadata = data.pop("_meta", None)
        if metadata is None and not require_metadata:
            metadata = {"code": path.stem, "name": path.stem.upper(), "contributors": []}
        if (not isinstance(metadata, dict) or metadata.get("code") != path.stem or
                not isinstance(metadata.get("name"), str) or not metadata["name"].strip() or
                not isinstance(metadata.get("contributors", []), list) or
                not all(isinstance(name, str) for name in metadata.get("contributors", []))):
            raise ValueError("Invalid _meta: use matching code, native name and contributor names")
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in data.items()):
            raise ValueError("Translation entries must map English strings to strings")
        return cls(path.stem, metadata["name"], tuple(metadata.get("contributors", [])), data)
