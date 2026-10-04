"""Shared CSV cell protection against spreadsheet formula injection."""

import re

NUMERIC_RE = re.compile(r"^[-+]?\d+(\.\d+)?$")


def neutralize_formula(text: str) -> str:
    """Prefix a quote to text that a spreadsheet could run as a formula.

    Catches =, +, -, @ even after leading whitespace, and cells starting with a
    tab or carriage return. Plain signed numbers (e.g. -12.5, +3) are kept.
    """
    if text.startswith(("\t", "\r")):
        return f"'{text}"
    stripped = text.lstrip(" \t\r\n")
    if stripped.startswith(("=", "+", "-", "@")):
        if NUMERIC_RE.match(text.strip()) and text == text.strip():
            return text
        return f"'{text}"
    return text
