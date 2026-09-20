import pytest

from backend.app.catalog.repository import ComponentRepository
from backend.app.models import Component, MCS

from backend.app import create_app


def component(category, part_no, function, **specs):
    return Component(
        None,
        category,
        "Test",
        part_no,
        "Common",
        function,
        freq_min_ghz=1.0,
        freq_max_ghz=40.0,
        specs=specs,
    )


def api_client(tmp_path):
    repository = ComponentRepository(tmp_path / "api-store")
    repository.replace_mcs([MCS(0, 2, -10.0, 100.0, 1.0)])
    repository.replace_components(
        [
            component(
                "MIXER",
                "MIX",
                "TRx",
                rf_min_ghz=1.0,
                rf_max_ghz=40.0,
                lo_min_ghz=1.0,
                lo_max_ghz=40.0,
                conversion_gain_db=5.0,
                channel_bandwidth_ghz=1.0,
                output_p1db_dbm=12.0,
                lo_drive_min_dbm=3.0,
            ),
            component(
                "PLL",
                "PLL",
                "PLL",
                output_freq_min_ghz=1.0,
                output_freq_max_ghz=40.0,
                output_power_dbm=5.0,
            ),
            component(
                "BFIC",
                "BF",
                "TRx",
                gain_db=15.0,
                output_p1db_dbm=15.0,
                channel_bandwidth_ghz=1.0,
                number_beams=1,
            ),
            component("PA", "PA", "PA", pa_gain_db=20.0, output_p1db_dbm=35.0),
        ]
    )
    return create_app(repository).test_client()


def test_health_and_component_endpoints(tmp_path):
    client = api_client(tmp_path)

    health     = client.get("/api/health")
    components = client.get("/api/components")

    assert set(client.application.blueprints) == {"catalog", "design"}
    assert health.status_code == 200
    assert health.get_json() == {"status": "ok", "components": 4, "mcs": 1}
    assert len(components.get_json()["components"]) == 4


def test_design_endpoint_returns_serialized_tx_candidate(tmp_path):
    client = api_client(tmp_path)
    response = client.post(
        "/api/designs",
        json={
            "requirement": {
                "application": "Terminal",
                "direction": "Tx",
                "center_freq_ghz": 30.0,
                "channel_bw_mhz": 20.0,
                "target_throughput_mbps": 1.0,
                "altitude_km": 888.0,
                "elevation_deg": 30.0,
                "antenna_gain_db": 100.0,
            }
        },
    )

    body = response.get_json()
    assert response.status_code == 200
    assert body["function"] == "Tx"
    assert body["requirement"]["center_freq_ghz"] == 30.0
    assert body["requirement"]["target_throughput_mbps"] == 1.0
    assert body["evaluated_candidates"] == 1
    assert body["candidates"][0]["status"] == "PASS"


def test_design_endpoint_rejects_invalid_requirement(tmp_path):
    client   = api_client(tmp_path)
    response = client.post("/api/designs", json={"requirement": {"channel_bw_mhz": 0}})

    assert response.status_code == 400
    assert "bandwidth" in response.get_json()["error"].lower()


def test_link_budget_endpoint_returns_boresight_and_max_slant_results(tmp_path):
    client = api_client(tmp_path)
    response = client.post(
        "/api/link-budget",
        json={
            "requirement": {
                "peak_eirp_dbw": 49.0,
                "output_backoff_db": 6.0,
                "center_freq_ghz": 30.0,
                "channel_bw_mhz": 100.0,
                "altitude_km": 888.0,
                "elevation_deg": 30.0,
            }
        },
    )

    body   = response.get_json()
    budget = body["link_budget"]
    assert response.status_code == 200
    assert body["eirp_dbw"] == pytest.approx(43.0)
    assert budget["peak_eirp_dbw"] == pytest.approx(49.0)
    assert budget["boresight_path_loss_db"] < budget["max_slant_path_loss_db"]
    assert budget["max_throughput_mbps"] >= budget["min_throughput_mbps"]
