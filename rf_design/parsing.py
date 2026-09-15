from __future__ import annotations

import re
from typing import Any, Optional, Tuple


MISSING = {"", "-", "—", "–", "tbd", "n/a", "na", "none"}


def is_missing(value: Any) -> bool:
    return value is None or str(value).strip().lower() in MISSING


def first_number(value: Any) -> Optional[float]:
    if isinstance(value, (int,float)): return float(value)
    if is_missing(value): return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def parse_range(value: Any) -> Tuple[Optional[float], Optional[float]]:
    if is_missing(value): return None,None
    if isinstance(value, (int,float)):
        number = float(value)
        return number,number
    text = str(value).replace("−", "-").replace("–", "-").replace("—", "-")
    numbers = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", text)]
    # A separator dash may be captured as a negative sign: normalize common positive ranges.
    if len(numbers) >= 2 and numbers[0] >= 0 and numbers[1] < 0 and " -" not in text:
        numbers[1] = abs(numbers[1])
    if len(numbers) >= 2:
        a,b = numbers[0],numbers[1]
        if a >= 0 and b < 0: b = abs(b)
        return min(a, b),max(a, b)
    if numbers: return numbers[0],numbers[0]
    return None,None


def parse_power_w(value: Any, unit: str) -> Optional[float]:
    number = first_number(value)
    if number is None: return None

    text  = str(value).replace(",", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?\s*(m?w)\b", text, re.IGNORECASE)
    if match and match.group(1).lower() == "w": return number
    if match and match.group(1).lower() == "mw": return number / 1000.0
    if "mw" in unit.strip().lower(): return number / 1000.0

    return number


def normalize_application(value: Any) -> str:
    text = str(value or "Common").strip().lower()
    if text in {"t", "terminal", "단말"}: return "Terminal"
    if text in {"p", "payload", "탑재체"}: return "Payload"
    if "terminal" in text and "payload" not in text: return "Terminal"
    if "payload" in text and "terminal" not in text: return "Payload"
    return "Common"


def infer_grade(part_no: Any, *descriptions: Any) -> str:
    part = str(part_no or "").upper()
    text = " ".join(str(value or "") for value in descriptions).lower()
    space_parts = {"ADAR3000S","ADAR3001S"}
    if part.endswith("-SP") or part in space_parts or any(label in text for label in ("space-grade","space grade","space qualified","radiation hardened","rad-hard")):
        return "Space-grade"

    return "Commercial-grade"
