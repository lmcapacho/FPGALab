"""Framework-free message formatting with an optional presentation adapter.

Importing domain modules must not load a GUI toolkit or user preferences.
English source messages are the default; a desktop host may explicitly install
its process-wide translator. Server hosts should retain the default or supply
their own adapter rather than importing the Qt translation layer.
"""

from collections.abc import Callable


_translator: Callable[[str], str] | None = None


def set_translator(translator: Callable[[str], str] | None) -> Callable[[str], str] | None:
    """Install a process-wide adapter and return the previous one for restoration."""
    global _translator
    previous = _translator
    _translator = translator
    return previous


def format_message(source: str, translated: str, /, **values: object) -> str:
    """Keep source formatting as fallback for a malformed catalog entry."""
    try:
        return translated.format(**values)
    except (KeyError, ValueError, IndexError, AttributeError, TypeError):
        if translated == source:
            raise
        return source.format(**values)


def t(source: str, /, **values: object) -> str:
    """Format an English domain message, optionally through the host adapter."""
    translated = _translator(source) if _translator is not None else source
    return format_message(source, translated, **values)
