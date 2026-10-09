"""
Guard: no French in backend messages that reach the app (Phase 4, finding A14).

Checks every string constant in app/ (error details, alert titles and messages,
notification texts, report labels and notes, validation errors). Not checked: docstrings,
comments, Swagger text (description=, summary=, examples) and log calls. Allowed: the
behaviour-correction values stored before Phase 4 (LEGACY_CORRECTIONS), which are data.
"""

import ast
import re
from pathlib import Path

from app.schemas.feedback import LEGACY_CORRECTIONS

APP_DIR = Path(__file__).resolve().parent.parent / "app"

ACCENTED = re.compile(r"[àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ]")
# Whole words only, never next to a hyphen ("non-null", "sans-serif" stay English).
FRENCH_WORDS = re.compile(
    r"(?<![\w-])(le|la|les|des|du|une|avec|dans|sur|vos|votre|nous|vous|est|sont|pas|aucun|aucune"
    r"|introuvable|appartient|erreur|ferme|animaux|collier|colliers|troupeau|utilisateur|invalide"
    r"|requis|oui|non)(?![\w-])",
    re.IGNORECASE,
)
SWAGGER_KEYWORDS = {"description", "summary", "example", "examples", "json_schema_extra"}
LOG_OBJECTS = {"logger", "logging", "log"}


def looks_french(text: str) -> bool:
    return bool(ACCENTED.search(text) or FRENCH_WORDS.search(text))


def message_strings(source: str):
    """(line, text) of the string constants that can reach a user."""
    tree = ast.parse(source)
    skipped = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                skipped.add(id(first.value))
        if isinstance(node, ast.keyword) and node.arg in SWAGGER_KEYWORDS:
            skipped.update(id(sub) for sub in ast.walk(node.value))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id in LOG_OBJECTS):
            skipped.update(id(sub) for sub in ast.walk(node))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skipped:
            yield node.lineno, node.value


def test_the_detector_flags_french_messages_and_skips_docstrings():
    source = '''
def f():
    """Docstring en français : ignorée."""
    raise HTTPException(404, detail="Animal introuvable")
'''
    found = [text for _, text in message_strings(source) if looks_french(text)]
    assert found == ["Animal introuvable"]
    assert not looks_french("Value must be non-null; font: sans-serif")
    assert looks_french("Utilisateur non trouvé")


def test_no_french_in_backend_messages():
    allowed = set(LEGACY_CORRECTIONS)
    problems = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for line, text in message_strings(path.read_text(encoding="utf-8")):
            if text not in allowed and looks_french(text):
                problems.append(f"{path.relative_to(APP_DIR)}:{line}: {text[:80]!r}")
    assert problems == [], "French text in backend messages:\n" + "\n".join(problems)
