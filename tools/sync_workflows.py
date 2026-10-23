"""
sync_workflows.py - Transfer user_workflows.json into config_workflows.py

Reads config/user_workflows.json, formats it as a Python dict literal (matching
the existing WORKFLOWS style: sorted keys, 4-space indent, single quotes,
trailing commas, True/False/None), and replaces the entire top-level
WORKFLOWS = { ... } block inside config/config_workflows.py.

Run:  python tools/sync_workflows.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
JSON_PATH = BASE_DIR / "config" / "user_workflows.json"
PY_PATH = BASE_DIR / "config" / "config_workflows.py"

INDENT = "    "  # 4 spaces


def _fmt(value, level: int) -> str:
    pad = INDENT * level
    inner_pad = INDENT * (level + 1)

    if value is True:
        return "True"
    if value is False:
        return "False"
    if value is None:
        return "None"
    if isinstance(value, str):
        # repr() produces single quotes unless the string contains a single
        # quote and no double quote; that behaviour matches the existing file.
        return repr(value)
    if isinstance(value, (int, float)):
        return repr(value)

    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        for k in sorted(value.keys()):
            v = value[k]
            lines.append(f"{inner_pad}{repr(k)}: {_fmt(v, level + 1)},")
        lines.append(f"{pad}}}")
        return "\n".join(lines)

    if isinstance(value, list):
        if not value:
            return "[]"
        # Lists of scalars on a single line (matches roi=[..] in existing file)
        if all(isinstance(x, (int, float, bool)) or x is None for x in value):
            inner = ", ".join(_fmt(x, level + 1) for x in value)
            return f"[{inner}]"
        lines = ["["]
        for item in value:
            lines.append(f"{inner_pad}{_fmt(item, level + 1)},")
        lines.append(f"{pad}]")
        return "\n".join(lines)

    raise TypeError(f"Unsupported value type: {type(value).__name__}")


def format_workflows(data: dict) -> str:
    """Return the full `WORKFLOWS = { ... }` assignment as a string."""
    body = _fmt(data, level=0)
    return f"WORKFLOWS = {body}"


def _find_workflows_block(src: str) -> tuple[int, int]:
    """Return (start, end) char indices of the top-level WORKFLOWS = {...}
    assignment in src. end is one past the closing '}'."""
    marker = "WORKFLOWS = {"
    start = src.find(marker)
    if start == -1:
        raise RuntimeError("Could not find 'WORKFLOWS = {' in config_workflows.py")
    # Walk forward from the opening brace, tracking string/brace state.
    i = start + len(marker) - 1  # position of '{'
    depth = 0
    in_str = False
    str_ch = ""
    escape = False
    while i < len(src):
        ch = src[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == str_ch:
                in_str = False
        else:
            if ch in ("'", '"'):
                in_str = True
                str_ch = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return start, i + 1
        i += 1
    raise RuntimeError("Unterminated WORKFLOWS block")


def main() -> int:
    if not JSON_PATH.exists():
        print(f"ERROR: {JSON_PATH} not found", file=sys.stderr)
        return 1
    if not PY_PATH.exists():
        print(f"ERROR: {PY_PATH} not found", file=sys.stderr)
        return 1

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("ERROR: user_workflows.json must contain a JSON object", file=sys.stderr)
        return 1

    new_block = format_workflows(data)

    src = PY_PATH.read_text(encoding="utf-8")
    start, end = _find_workflows_block(src)
    new_src = src[:start] + new_block + src[end:]

    # Sanity: parse the result so we fail loudly if something went wrong.
    compile(new_src, str(PY_PATH), "exec")

    PY_PATH.write_text(new_src, encoding="utf-8")
    print(f"OK: wrote {len(data)} workflows into {PY_PATH.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
