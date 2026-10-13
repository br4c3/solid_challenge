from __future__ import annotations

import ast
import json
import math
import os
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION        = 1
DEFAULT_PROFILE_ID    = "default-v1"
MAX_EXPRESSION_LENGTH = 500
MAX_AST_NODES         = 100
MAX_AST_DEPTH         = 32

FORMULA_SLOTS = {
    "tx_stage_output_dbm": {
        "label": "송신 단계 출력 전력",
        "unit": "dBm",
        "variables": {
            "input_dbm": "dBm",
            "gain_db": "dB"
        },
        "expression": "input_dbm + gain_db",
    },
    "tx_allowed_output_dbm": {
        "label": "송신 허용 출력 전력",
        "unit": "dBm",
        "variables": {
            "limit_dbm": "dBm",
            "output_backoff_db": "dB",
            "is_pa": "ratio"
        },
        "expression": "limit_dbm - output_backoff_db if is_pa else limit_dbm",
    },
    "peak_eirp_dbw": {
        "label": "최대 EIRP",
        "unit": "dBW",
        "variables": {
            "antenna_input_dbm": "dBm",
            "antenna_gain_db": "dB",
            "feed_loss_db": "dB"
        },
        "expression": "antenna_input_dbm - 30 + antenna_gain_db - feed_loss_db",
    },
    "beam_eirp_dbw": {
        "label": "빔당 선형 EIRP",
        "unit": "dBW",
        "variables": {
            "peak_eirp_dbw": "dBW",
            "num_beams": "count",
            "output_backoff_db": "dB"
        },
        "expression": "peak_eirp_dbw - 10 * log10(num_beams) - output_backoff_db",
    },
    "slant_range_km": {
        "label":
        "경사거리",
        "unit":
        "km",
        "variables": {
            "earth_radius_km": "km",
            "altitude_km": "km",
            "elevation_deg": "deg"
        },
        "expression":
        "sqrt((earth_radius_km + altitude_km) ** 2 - (earth_radius_km * cos(radians(elevation_deg))) ** 2) - earth_radius_km * sin(radians(elevation_deg))",
    },
    "fspl_db": {
        "label": "자유 공간 경로 손실",
        "unit": "dB",
        "variables": {
            "frequency_ghz": "GHz",
            "distance_km": "km"
        },
        "expression": "92.45 + 20 * log10(frequency_ghz) + 20 * log10(distance_km)",
    },
    "system_temperature_k": {
        "label": "시스템 잡음 온도",
        "unit": "K",
        "variables": {
            "receiver_nf_db": "dB",
            "sky_temperature_k": "K"
        },
        "expression": "290 * (10 ** (receiver_nf_db / 10) - 1) + sky_temperature_k",
    },
    "gt_db_per_k": {
        "label": "수신기 G/T",
        "unit": "dB/K",
        "variables": {
            "antenna_gain_db": "dB",
            "bf_error_db": "dB",
            "system_temperature_k": "K"
        },
        "expression": "antenna_gain_db - bf_error_db - 10 * log10(system_temperature_k)",
    },
    "eis_dbm": {
        "label": "등가 입력 잡음",
        "unit": "dBm",
        "variables": {
            "thermal_noise_dbm_hz": "dBm/Hz",
            "bandwidth_mhz": "MHz",
            "receiver_nf_db": "dB",
            "receiver_gain_db": "dB"
        },
        "expression": "thermal_noise_dbm_hz + 10 * log10(bandwidth_mhz * 1000000) + receiver_nf_db - receiver_gain_db",
    },
    "noise_snr_db": {
        "label": "잡음 제한 SNR",
        "unit": "dB",
        "variables": {
            "eirp_dbw": "dBW",
            "path_loss_db": "dB",
            "propagation_loss_db": "dB",
            "eis_dbm": "dBm"
        },
        "expression": "eirp_dbw + 30 - path_loss_db - propagation_loss_db - eis_dbm",
    },
    "combined_snr_db": {
        "label": "결합 SNR",
        "unit": "dB",
        "variables": {
            "noise_snr_db": "dB",
            "nonlinear_snr_db": "dB"
        },
        "expression": "-10 * log10(10 ** (-noise_snr_db / 10) + 10 ** (-nonlinear_snr_db / 10))",
    },
    "throughput_mbps": {
        "label": "처리량",
        "unit": "Mbps",
        "variables": {
            "spectral_efficiency": "bit/s/Hz",
            "bandwidth_mhz": "MHz",
            "control_overhead": "ratio",
            "fill_factor": "ratio"
        },
        "expression": "spectral_efficiency * bandwidth_mhz * (1 - control_overhead) * fill_factor",
    },
    "throughput_margin_mbps": {
        "label": "처리량 마진",
        "unit": "Mbps",
        "variables": {
            "throughput_mbps": "Mbps",
            "target_throughput_mbps": "Mbps"
        },
        "expression": "throughput_mbps - target_throughput_mbps",
    },
    "link_margin_db": {
        "label": "링크 마진",
        "unit": "dB",
        "variables": {
            "total_snr_db": "dB",
            "required_snr_db": "dB"
        },
        "expression": "total_snr_db - required_snr_db",
    },
    "rx_noise_factor": {
        "label": "수신 단계 잡음 계수",
        "unit": "ratio",
        "variables": {
            "noise_figure_db": "dB"
        },
        "expression": "10 ** (noise_figure_db / 10)",
    },
    "rx_friis_contribution": {
        "label": "Friis 잡음 기여도",
        "unit": "ratio",
        "variables": {
            "noise_factor": "ratio",
            "preceding_gain_linear": "ratio",
            "is_first_stage": "ratio"
        },
        "expression": "noise_factor if is_first_stage else (noise_factor - 1) / preceding_gain_linear",
    },
    "rx_total_gain_db": {
        "label": "수신기 누적 이득",
        "unit": "dB",
        "variables": {
            "current_total_gain_db": "dB",
            "stage_gain_db": "dB"
        },
        "expression": "current_total_gain_db + stage_gain_db",
    },
    "rx_total_nf_db": {
        "label": "수신기 전체 잡음 지수",
        "unit": "dB",
        "variables": {
            "total_noise_factor": "ratio"
        },
        "expression": "10 * log10(total_noise_factor)",
    },
}

DEFAULT_RANKING = {
    "Tx": [
        {
            "expression": "status_priority",
            "direction": "asc",
            "enabled": True
        },
        {
            "expression": "commercial_count if application_is_payload else 0",
            "direction": "asc",
            "enabled": True
        },
        {
            "expression": "preference_score",
            "direction": "desc",
            "enabled": True
        },
        {
            "expression": "link_margin_db",
            "direction": "desc",
            "enabled": True
        },
        {
            "expression": "throughput_margin_mbps",
            "direction": "desc",
            "enabled": True
        },
        {
            "expression": "total_power_w",
            "direction": "asc",
            "enabled": True
        },
        {
            "expression": "component_count",
            "direction": "asc",
            "enabled": True
        },
    ],
    "Rx": [
        {
            "expression": "commercial_count if application_is_payload else 0",
            "direction": "asc",
            "enabled": True
        },
        {
            "expression": "preference_score",
            "direction": "desc",
            "enabled": True
        },
        {
            "expression": "total_nf_db",
            "direction": "asc",
            "enabled": True
        },
        {
            "expression": "total_gain_db",
            "direction": "desc",
            "enabled": True
        },
        {
            "expression": "total_power_w",
            "direction": "asc",
            "enabled": True
        },
    ],
}

RANKING_VARIABLES = {
    "status_priority", "commercial_count", "application_is_payload", "preference_score", "link_margin_db",
    "throughput_margin_mbps", "total_power_w", "component_count", "total_nf_db", "total_gain_db"
}

SAMPLE_VALUES_BY_UNIT = {
    "dBm": 10.0,
    "dBm/Hz": -174.0,
    "dBW": 10.0,
    "dB": 3.0,
    "dB/K": 10.0,
    "GHz": 20.0,
    "MHz": 20.0,
    "km": 100.0,
    "K": 290.0,
    "deg": 30.0,
    "count": 2.0,
    "ratio": 0.5,
    "bit/s/Hz": 2.0,
    "Mbps": 40.0,
}

ALLOWED_FUNCTIONS = {
    "abs": abs,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "log10": math.log10,
    "ln": math.log,
    "pow": pow,
    "clamp": lambda value, low, high: min(max(value, low), high),
    "if_else": lambda condition, yes, no: yes if condition else no,
    "sin": math.sin,
    "cos": math.cos,
    "radians": math.radians,
}

ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_profile() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "id": DEFAULT_PROFILE_ID,
        "name": "기본 프로필 v1",
        "description": "표준 RF 설계 모델에 맞춘 기본 제공 수식입니다.",
        "revision": 1,
        "built_in": True,
        "created_at": "",
        "updated_at": "",
        "formulas": {
            key: value["expression"]
            for key, value in FORMULA_SLOTS.items()
        },
        "ranking": deepcopy(DEFAULT_RANKING),
    }


def _depth(node: ast.AST) -> int:
    children = list(ast.iter_child_nodes(node))
    return 1 + max((_depth(child) for child in children), default=0)


class SafeExpression:

    def __init__(self, expression: str, variables: set[str]):
        if not isinstance(expression, str) or not expression.strip(): raise ValueError("수식은 비워둘 수 없습니다.")
        if len(expression) > MAX_EXPRESSION_LENGTH: raise ValueError("수식은 500자를 초과할 수 없습니다.")
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as error:
            raise ValueError(f"수식 문법이 올바르지 않습니다: {error.msg}.") from error
        nodes = list(ast.walk(tree))
        if len(nodes) > MAX_AST_NODES or _depth(tree) > MAX_AST_DEPTH:
            raise ValueError("수식이 너무 복잡합니다.")
        for node in nodes:
            if not isinstance(node, ALLOWED_NODES):
                raise ValueError(f"지원하지 않는 수식 요소입니다: {type(node).__name__}.")
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
                    raise ValueError("허용된 수학 함수만 호출할 수 있습니다.")
                if node.keywords: raise ValueError("수식에서는 키워드 인자를 사용할 수 없습니다.")
            if isinstance(node, ast.Name) and node.id not in variables and node.id not in ALLOWED_FUNCTIONS:
                raise ValueError(f"알 수 없는 수식 변수입니다: {node.id}.")
            if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
                raise ValueError("숫자와 불리언 상수만 사용할 수 있습니다.")
        self.expression = expression.strip()
        self.code       = compile(tree, "<formula>", "eval")

    def evaluate(self, values: Mapping[str, float]) -> float:
        try:
            result = eval(self.code, {"__builtins__": {}}, {**ALLOWED_FUNCTIONS, **values})
        except (ArithmeticError, ValueError, TypeError, OverflowError) as error:
            raise ValueError(f"수식 계산에 실패했습니다: {error}.") from error
        if isinstance(result, bool): result = float(result)
        if not isinstance(result, (int, float)) or not math.isfinite(float(result)):
            raise ValueError("수식 결과는 유한한 숫자여야 합니다.")
        return float(result)


class FormulaEngine:

    def __init__(self, profile: Mapping[str, Any]):
        self.profile = validate_profile(profile)
        self.compiled = {
            key: SafeExpression(expression, set(FORMULA_SLOTS[key]["variables"]))
            for key, expression in self.profile["formulas"].items()
        }
        self.rankings = {
            function: [
                {
                    **item, "compiled": SafeExpression(item["expression"], RANKING_VARIABLES)
                } for item in items if item["enabled"]
            ]
            for function, items in self.profile["ranking"].items()
        }

    def evaluate(self, slot: str, values: Mapping[str, float], trace: list[dict] | None = None, **meta) -> float:
        required = set(FORMULA_SLOTS[slot]["variables"])
        missing  = required - set(values)
        if missing: raise ValueError(f"{slot} 수식에 필요한 변수가 없습니다: {', '.join(sorted(missing))}.")
        result = self.compiled[slot].evaluate(values)
        if trace is not None:
            trace.append(
                {
                    "kind":
                    slot,
                    "label":
                    FORMULA_SLOTS[slot]["label"],
                    "expression":
                    self.profile["formulas"][slot],
                    "inputs": [
                        {
                            "symbol": name,
                            "value": values[name],
                            "unit": unit
                        } for name, unit in FORMULA_SLOTS[slot]["variables"].items()
                    ],
                    "intermediate_values": [],
                    "result":
                    result,
                    "unit":
                    FORMULA_SLOTS[slot]["unit"],
                    **meta,
                }
            )
        return result

    def ranking_key(self, function: str, values: Mapping[str, float]) -> tuple[float, ...]:
        key = []
        for item in self.rankings[function]:
            result = item["compiled"].evaluate(values)
            key.append(-result if item["direction"] == "desc" else result)
        return tuple(key)


def validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, Mapping): raise ValueError("수식 프로필은 객체 형식이어야 합니다.")
    formulas = profile.get("formulas")
    ranking  = profile.get("ranking")
    if not isinstance(formulas, Mapping): raise ValueError("수식 프로필에 formulas 객체가 필요합니다.")
    missing = set(FORMULA_SLOTS) - set(formulas)
    unknown = set(formulas) - set(FORMULA_SLOTS)
    if missing: raise ValueError(f"누락된 수식 항목: {', '.join(sorted(missing))}.")
    if unknown: raise ValueError(f"지원하지 않는 수식 항목: {', '.join(sorted(unknown))}.")
    for key, expression in formulas.items():
        compiled = SafeExpression(expression, set(FORMULA_SLOTS[key]["variables"]))
        samples  = {name: SAMPLE_VALUES_BY_UNIT[unit] for name, unit in FORMULA_SLOTS[key]["variables"].items()}
        try:
            compiled.evaluate(samples)
        except ValueError as error:
            raise ValueError(f"{key}: {error}") from error
    if not isinstance(ranking, Mapping) or set(ranking) != {"Tx", "Rx"}:
        raise ValueError("순위 규칙에는 Tx 및 Rx 목록이 필요합니다.")
    for function, items in ranking.items():
        if not isinstance(items, list) or not items: raise ValueError(f"{function} 순위 규칙은 비워둘 수 없습니다.")
        for item in items:
            if not isinstance(item, Mapping): raise ValueError("각 순위 규칙은 객체 형식이어야 합니다.")
            if item.get("direction") not in {"asc", "desc"}: raise ValueError("정렬 방향은 asc 또는 desc여야 합니다.")
            if not isinstance(item.get("enabled"), bool): raise ValueError("순위 규칙의 사용 여부는 불리언이어야 합니다.")
            compiled = SafeExpression(item.get("expression", ""), RANKING_VARIABLES)
            compiled.evaluate({name: 1.0 for name in RANKING_VARIABLES})
    name = str(profile.get("name", "")).strip()
    if not name: raise ValueError("수식 프로필 이름을 입력해야 합니다.")
    result                   = deepcopy(dict(profile))
    result["schema_version"] = SCHEMA_VERSION
    result["name"]           = name
    return result


class FormulaProfileRepository:

    def __init__(self, path: Path):
        self.path = Path(path) / "formula_profiles.json"

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists(): return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return payload.get("profiles", []) if isinstance(payload, dict) else []

    def _write(self, profiles: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({"schema_version": SCHEMA_VERSION, "profiles": profiles}, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, self.path)

    def list(self) -> list[dict[str, Any]]:
        latest = {}
        for profile in self._read():
            if profile["id"] not in latest or profile["revision"] > latest[profile["id"]]["revision"]:
                latest[profile["id"]] = profile
        return [default_profile(), *sorted(latest.values(), key=lambda item: item["name"].casefold())]

    def get(self, profile_id: str, revision: int | None = None) -> dict[str, Any]:
        if profile_id == DEFAULT_PROFILE_ID: return default_profile()
        matches                          = [item for item in self._read() if item["id"] == profile_id]
        if revision is not None: matches = [item for item in matches if item["revision"] == revision]
        if not matches: raise ValueError("수식 프로필 또는 개정 버전을 찾을 수 없습니다.")
        return max(matches, key=lambda item: item["revision"])

    def create(self, source: Mapping[str, Any]) -> dict[str, Any]:
        profile               = validate_profile(source)
        now                   = timestamp()
        profile["id"]         = uuid.uuid4().hex
        profile["revision"]   = 1
        profile["built_in"]   = False
        profile["created_at"] = now
        profile["updated_at"] = now
        profiles              = self._read()
        profiles.append(profile)
        self._write(profiles)
        return profile

    def update(self, profile_id: str, base_revision: int, source: Mapping[str, Any]) -> dict[str, Any]:
        if profile_id == DEFAULT_PROFILE_ID: raise ValueError("기본 제공 수식 프로필은 수정할 수 없습니다.")
        previous = self.get(profile_id)
        if previous["revision"] != base_revision: raise ValueError("수식 프로필 개정 버전이 충돌합니다.")
        profile               = validate_profile(source)
        profile["id"]         = profile_id
        profile["revision"]   = base_revision + 1
        profile["built_in"]   = False
        profile["created_at"] = previous["created_at"]
        profile["updated_at"] = timestamp()
        profiles              = self._read()
        profiles.append(profile)
        self._write(profiles)
        return profile

    def delete(self, profile_id: str) -> None:
        if profile_id == DEFAULT_PROFILE_ID: raise ValueError("기본 제공 수식 프로필은 삭제할 수 없습니다.")
        profiles = [item for item in self._read() if item["id"] != profile_id]
        self._write(profiles)
