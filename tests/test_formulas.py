from copy import deepcopy

import pytest

from backend.app.formulas import FormulaEngine, FormulaProfileRepository, SafeExpression, default_profile
from backend.app import create_app
from backend.app.catalog.crawler import CrawlManager
from backend.app.catalog.repository import ComponentRepository

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_safe_expression_rejects_unsafe_python():
    with pytest.raises(ValueError, match="허용된 수학 함수"):
        SafeExpression("__import__('os').system('whoami')", set())

    with pytest.raises(ValueError, match="지원하지 않는 수식 요소"):
        SafeExpression("[value for value in values]", {"values"})


def test_formula_profile_repository_keeps_revisions(tmp_path):
    repository     = FormulaProfileRepository(tmp_path)
    source         = default_profile()
    source["name"] = "Team Model"
    created        = repository.create(source)

    changed                                = deepcopy(created)
    changed["formulas"]["throughput_mbps"] = "spectral_efficiency * bandwidth_mhz"
    updated                                = repository.update(created["id"], created["revision"], changed)

    assert updated["revision"] == 2
    assert repository.get(created["id"], 1)["formulas"]["throughput_mbps"] != updated["formulas"]["throughput_mbps"]
    assert repository.get(created["id"])["revision"] == 2


def test_custom_formula_changes_evaluation_and_trace():
    profile                                = default_profile()
    profile["name"]                        = "Custom Throughput"
    profile["formulas"]["throughput_mbps"] = "spectral_efficiency * bandwidth_mhz * 0.5"
    engine                                 = FormulaEngine(profile)
    trace                                  = []

    result = engine.evaluate(
        "throughput_mbps", {
            "spectral_efficiency": 2.0,
            "bandwidth_mhz": 20.0,
            "control_overhead": 0.1,
            "fill_factor": 0.9,
        }, trace
    )

    assert result == 20.0
    assert trace[0]["expression"] == "spectral_efficiency * bandwidth_mhz * 0.5"
    assert trace[0]["unit"] == "Mbps"


def test_formula_validation_rejects_nominal_domain_error():
    profile                        = default_profile()
    profile["name"]                = "Broken"
    profile["formulas"]["fspl_db"] = "log10(-1)"

    with pytest.raises(ValueError, match="fspl_db"):
        FormulaEngine(profile)


def test_design_api_uses_selected_formula_profile(tmp_path):
    source     = ComponentRepository(PROJECT_ROOT / "data")
    repository = ComponentRepository(tmp_path)
    repository.replace_components(source.list())
    repository.replace_mcs(source.list_mcs())
    client = create_app(repository=repository, crawler=CrawlManager(command=["true"])).test_client()

    created                                = client.post("/api/formula-profiles", json={"name": "Zero Throughput"}).get_json()
    profile                                = client.get(f"/api/formula-profiles/{created['id']}").get_json()
    profile["formulas"]["throughput_mbps"] = "spectral_efficiency * bandwidth_mhz * 0"
    updated = client.put(
        f"/api/formula-profiles/{created['id']}",
        json={
            **profile, "base_revision": profile["revision"]
        },
    ).get_json()
    response = client.post(
        "/api/designs",
        json={
            "requirement": {
                "application": "Terminal",
                "direction": "Uplink",
                "center_freq_ghz": 29.25,
                "channel_bw_mhz": 20,
                "target_throughput_mbps": 40,
                "altitude_km": 888,
                "elevation_deg": 30,
            },
            "formula_profile": {
                "id": updated["id"],
                "revision": updated["revision"]
            },
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["formula_profile"]["name"] == "Zero Throughput"
    assert payload["candidates"][0]["link_budget"]["max_throughput_mbps"] == 0
    assert any(
        item["kind"] == "throughput_mbps" and item["expression"].endswith("* 0")
        for item in payload["candidates"][0]["calculation_trace"]
    )
