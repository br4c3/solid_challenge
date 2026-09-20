from __future__ import annotations

import argparse
import ast
import io
import tokenize
from pathlib import Path
from typing import Iterable

from yapf.yapflib.yapf_api import FormatCode

ROOT            = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = (ROOT / "backend", ROOT / "scripts", ROOT / "tests")
YAPF_STYLE = {
    "based_on_style": "pep8",
    "column_limit": 120,
    "dedent_closing_brackets": True,
    "split_before_logical_operator": True,
}


def python_files(targets: Iterable[Path]) -> list[Path]:
    files = []
    for target in targets:
        if target.is_file() and target.suffix == ".py":
            files.append(target)
        elif target.is_dir():
            files.extend(target.rglob("*.py"))
    return sorted(set(files))


def assignment_lines(source: str) -> set[int]:
    tree  = ast.parse(source)
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and node.lineno == node.end_lineno:
            lines.add(node.lineno)
        elif isinstance(node, ast.AnnAssign) and node.value is not None and node.lineno == node.end_lineno:
            lines.add(node.lineno)
    return lines


def assignment_columns(source: str, candidates: set[int]) -> dict[int, int]:
    columns = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.OP and token.string == "=" and token.start[0] in candidates:
            columns.setdefault(token.start[0], token.start[1])
    return columns


def align_assignments(source: str) -> str:
    lines      = source.splitlines(keepends=True)
    candidates = assignment_lines(source)
    columns    = assignment_columns(source, candidates)
    groups     = []
    current    = []

    for line_number in sorted(columns):
        line   = lines[line_number - 1]
        indent = len(line) - len(line.lstrip())
        if current:
            previous        = current[-1]
            previous_line   = lines[previous - 1]
            previous_indent = len(previous_line) - len(previous_line.lstrip())
            if line_number != previous + 1 or indent != previous_indent:
                if len(current) > 1: groups.append(current)
                current = []
        current.append(line_number)
    if len(current) > 1: groups.append(current)

    for group in groups:
        width = max(len(lines[number - 1][:columns[number]].rstrip()) for number in group)
        for number in group:
            line              = lines[number - 1]
            column            = columns[number]
            left              = line[:column].rstrip()
            right             = line[column + 1:].lstrip(" ")
            lines[number - 1] = f"{left:<{width}} = {right}"
    return "".join(lines)


def format_source(source: str, filename: Path) -> str:
    formatted, _ = FormatCode(source, filename=str(filename), style_config=YAPF_STYLE)
    return align_assignments(formatted)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply YAPF and align consecutive Python assignment operators.")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--check", action="store_true", help="Check formatting without modifying files.")
    args    = parser.parse_args()
    targets = tuple(path.resolve() for path in args.paths) or DEFAULT_TARGETS
    changed = []

    for path in python_files(targets):
        source    = path.read_text(encoding="utf-8")
        formatted = format_source(source, path)
        if formatted == source: continue
        changed.append(path)
        if not args.check: path.write_text(formatted, encoding="utf-8")

    if changed:
        print("Files requiring formatting:")
        for path in changed:
            print(path.relative_to(ROOT))
    return int(args.check and bool(changed))


if __name__ == "__main__": raise SystemExit(main())
