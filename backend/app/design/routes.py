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
    if not isinstance(payload, dict): raise ValueError("Requirements must be a JSON object.")
    unknown = set(payload) - REQUIREMENT_FIELDS
    if unknown: raise ValueError(f"Unsupported requirement fields: {', '.join(sorted(unknown))}")
    values = asdict(default_requirement())
    values.update(payload)
    requirement = LinkRequirement(**values)
    requirement.validate()
    return requirement


def serialize_tx_candidate(candidate) -> dict:
    result           = serialize(candidate)
    result["status"] = candidate.status.value
    return result


def create_design_blueprint(repository: ComponentRepository) -> Blueprint:
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
        if not isinstance(payload, dict): raise ValueError("Request body must be a JSON object.")
        requirement = parse_requirement(payload.get("requirement", payload))
        limit       = min(max(int(payload.get("limit", 5000)), 1), 5000)
        function    = required_function(requirement)
        if function == "Tx":
            candidates, warnings = generate_tx_candidates(
                requirement, repository.list(), repository.list_mcs(), limit=limit
            )
            serialized = [serialize_tx_candidate(candidate) for candidate in candidates[:50]]
        elif function == "Rx":
            candidates, warnings = generate_rx_candidates(requirement, repository.list(), limit=limit)
            serialized           = serialize(candidates[:50])
        else:
            raise ValueError(f"Unsupported link direction: {requirement.direction}")
        return jsonify(
            {
                "function": function,
                "requirement": serialize(requirement),
                "evaluated_candidates": len(candidates),
                "returned_candidates": len(serialized),
                "candidates": serialized,
                "warnings": warnings,
            }
        )

    @api.post("/link-budget")
    def link_budget():
        payload = request.get_json() or {}
        if not isinstance(payload, dict): raise ValueError("Request body must be a JSON object.")
        requirement       = parse_requirement(payload.get("requirement", {}))
        antenna_input_dbm = float(payload.get("antenna_input_dbm", 34.0))
        peak_eirp         = requirement.peak_eirp_dbw
        if peak_eirp is None:
            peak_eirp = calculate_peak_eirp(antenna_input_dbm, requirement.antenna_gain_db, requirement.feed_loss_db)
        result = calculate_link_budget(requirement, peak_eirp, repository.list_mcs())
        return jsonify({"eirp_dbw": result.linear_eirp_per_beam_dbw, "link_budget": serialize(result)})

    return api
