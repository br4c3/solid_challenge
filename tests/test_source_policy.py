from pathlib import Path
import re

from backend.app.models import Component, ComponentSpec

ROOT             = Path(__file__).resolve().parents[1]
CODE_DIRECTORIES = (ROOT / "backend", ROOT / "scripts", ROOT / "tests", ROOT / "frontend" / "src")
CODE_SUFFIXES    = {".py", ".js", ".vue", ".css", ".html"}
HANGUL           = re.compile("[\uac00-\ud7a3]")


def test_component_uses_typed_spec_structure():
    component = Component(None, "PA", "Test", "PA-1", specs={"pa_gain_db": 20.0})

    assert isinstance(component.specs, ComponentSpec)
    assert component.specs.pa_gain_db == 20.0


def test_source_code_contains_no_hangul():
    paths = [
        path for directory in CODE_DIRECTORIES for path in directory.rglob("*")
        if path.is_file() and path.suffix in CODE_SUFFIXES
    ]
    paths.append(ROOT / "frontend" / "index.html")

    violations = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if HANGUL.search(line): violations.append(f"{path.relative_to(ROOT)}:{line_number}")

    assert violations == [], f"Hangul found in source code: {', '.join(violations)}"
