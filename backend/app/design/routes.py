from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from enum import Enum
from typing import Any

from flask import Blueprint, jsonify, request

from .candidates import generate_rx_candidates, generate_tx_candidates
from .compatibility import check_component, esa_band, overall_status, required_function
from .link_budget import calculate_link_budget, calculate_peak_eirp
from ..catalog.repository import ComponentRepository
from ..models import LinkRequirement
from ..preferences import ComponentKey, PreferenceRepository
from ..formulas import DEFAULT_PROFILE_ID, FormulaEngine, FormulaProfileRepository

REQUIREMENT_FIELDS = {field.name for field in fields(LinkRequirement)}


def default_requirement() -> LinkRequirement:
    return LinkRequirement("Terminal", "Uplink", 29.25, 20.0, 40.0, 888.0, 30.0)


def serialize(value: Any):
    if isinstance(value, Enum): return value.value
    if is_dataclass(value): return serialize(asdict(value))
    if isinstance(value, dict): return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [serialize(item) for item in value]
    return value


def parse_requirement(payload: dict) -> LinkRequirement:
    if not isinstance(payload, dict): raise ValueError("요구사항은 JSON 객체 형식이어야 합니다.")
    unknown = set(payload) - REQUIREMENT_FIELDS
    if unknown: raise ValueError(f"지원하지 않는 요구사항 항목: {', '.join(sorted(unknown))}")
    values = asdict(default_requirement())
    values.update(payload)
    requirement = LinkRequirement(**values)
    requirement.validate()
    return requirement


def serialize_tx_candidate(candidate) -> dict:
    result           = serialize(candidate)
    result["status"] = candidate.status.value
    return result


def parse_pinned_components(payload: Any, components: list, function: str) -> list[ComponentKey]:
    if payload is None: return []
    if not isinstance(payload, list): raise ValueError("pinned_components는 배열이어야 합니다.")
    allowed = {
        "Tx": {
            "DAC": "CONVERTER",
            "CONVERTER": "CONVERTER",
            "MIXER": "MIXER",
            "PLL": "PLL",
            "BFIC": "BFIC",
            "PA": "PA",
            "FEM": "PA",
            "SWITCH": "SWITCH"
        },
        "Rx": {
            "ADC": "CONVERTER",
            "CONVERTER": "CONVERTER",
            "LNA": "LNA",
            "FEM": "LNA",
            "BFIC": "BFIC",
            "MIXER": "MIXER",
            "PLL": "PLL",
            "SWITCH": "SWITCH"
        },
    }[function]
    resolved = []
    stages   = set()
    for value in payload:
        requested = ComponentKey.from_mapping(value)
        match     = next((component for component in components if requested.matches(component)), None)
        if match is None:
            raise ValueError(f"고정 부품을 찾을 수 없습니다: {requested.manufacturer} {requested.part_no}.")
        category = match.category.upper()
        if category not in allowed:
            raise ValueError(f"{function} 체인에는 {match.category} 부품을 고정할 수 없습니다.")
        stage = allowed[category]
        if stage in stages: raise ValueError(f"{stage} 단계에는 부품 하나만 고정할 수 있습니다.")
        stages.add(stage)
        resolved.append(ComponentKey.from_component(match))
    return resolved


def create_design_blueprint(
    repository: ComponentRepository,
    preference_repository: PreferenceRepository,
    formula_repository: FormulaProfileRepository,
) -> Blueprint:
    api = Blueprint("design", __name__)

    @api.get("/config")
    def config():
        bands = {
            f"{application}-{direction}": esa_band(application, direction)
            for application in ("Terminal", "Payload")
            for direction in ("Uplink", "Downlink", "Tx", "Rx")
        }
        return jsonify({"default_requirement": serialize(default_requirement()), "bands": bands})

    @api.post("/compatibility")
    def compatibility():
        requirement = parse_requirement(request.get_json() or {})
        results     = []
        for component in repository.list():
            checks = check_component(component, requirement)
            results.append(
                {
                    "component": serialize(component),
                    "status": overall_status(checks).value,
                    "checks": serialize(checks),
                }
            )
        return jsonify({"function": required_function(requirement), "results": results})

    @api.post("/designs")
    def designs():
        payload = request.get_json() or {}
        if not isinstance(payload, dict): raise ValueError("요청 본문은 JSON 객체 형식이어야 합니다.")
        requirement = parse_requirement(payload.get("requirement", payload))
        limit       = min(max(int(payload.get("limit", 5000)), 1), 5000)
        function    = required_function(requirement)
        if function not in ("Tx", "Rx"): raise ValueError(f"지원하지 않는 링크 방향: {requirement.direction}")
        components        = repository.list()
        pinned            = parse_pinned_components(payload.get("pinned_components"), components, function)
        preferences       = preference_repository.load()
        formula_selection = payload.get("formula_profile") or {"id": DEFAULT_PROFILE_ID}
        if not isinstance(formula_selection, dict): raise ValueError("formula_profile은 객체 형식이어야 합니다.")
        profile = formula_repository.get(
            str(formula_selection.get("id", DEFAULT_PROFILE_ID)), formula_selection.get("revision")
        )
        formula_engine = FormulaEngine(profile)
        if function == "Tx":
            candidates, warnings = generate_tx_candidates(
                requirement,
                components,
                repository.list_mcs(),
                limit=limit,
                preferences=preferences,
                pinned_components=pinned,
                formula_engine=formula_engine,
            )
            serialized = [serialize_tx_candidate(candidate) for candidate in candidates[:50]]
        elif function == "Rx":
            candidates, warnings = generate_rx_candidates(
                requirement,
                components,
                limit=limit,
                preferences=preferences,
                pinned_components=pinned,
                formula_engine=formula_engine,
            )
            serialized = serialize(candidates[:50])
        else:
            raise ValueError(f"지원하지 않는 링크 방향: {requirement.direction}")
        return jsonify(
            {
                "function": function,
                "requirement": serialize(requirement),
                "evaluated_candidates": len(candidates),
                "returned_candidates": len(serialized),
                "candidates": serialized,
                "warnings": warnings,
                "formula_profile": {
                    key: profile[key]
                    for key in ("id", "name", "revision")
                },
            }
        )

    @api.post("/link-budget")
    def link_budget():
        payload = request.get_json() or {}
        if not isinstance(payload, dict): raise ValueError("요청 본문은 JSON 객체 형식이어야 합니다.")
        requirement       = parse_requirement(payload.get("requirement", {}))
        antenna_input_dbm = float(payload.get("antenna_input_dbm", 34.0))
        peak_eirp         = requirement.peak_eirp_dbw
        if peak_eirp is None:
            peak_eirp = calculate_peak_eirp(antenna_input_dbm, requirement.antenna_gain_db, requirement.feed_loss_db)
        result = calculate_link_budget(requirement, peak_eirp, repository.list_mcs())
        return jsonify({"eirp_dbw": result.linear_eirp_per_beam_dbw, "link_budget": serialize(result)})

    return api
