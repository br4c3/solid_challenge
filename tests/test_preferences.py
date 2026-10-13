from pathlib import Path

from backend.app import create_app
from backend.app.catalog.crawler import CrawlManager
from backend.app.catalog.repository import ComponentRepository
from backend.app.preferences import ComponentKey, PreferenceRepository, Preferences

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def component_key(component: dict) -> dict:
    return {
        "category": component["category"],
        "manufacturer": component["manufacturer"],
        "part_no": component["part_no"],
    }


def populated_repository(path: Path) -> ComponentRepository:
    source     = ComponentRepository(PROJECT_ROOT / "data")
    repository = ComponentRepository(path)
    repository.replace_components(source.list())
    repository.replace_mcs(source.list_mcs())
    return repository


def test_preference_repository_normalizes_and_persists(tmp_path):
    repository = PreferenceRepository(tmp_path)
    preferences = Preferences.from_mapping(
        {
            "favorite_manufacturers": ["Qorvo", " qorvo "],
            "favorite_components": [
                {
                    "category": "LNA",
                    "manufacturer": "Example",
                    "part_no": "ABC-1",
                },
                {
                    "category": "lna",
                    "manufacturer": "example",
                    "part_no": "abc-1",
                },
            ],
        }
    )

    repository.save(preferences)
    restored = repository.load()

    assert restored.favorite_manufacturers == ["Qorvo"]
    assert restored.favorite_components == [ComponentKey("LNA", "Example", "ABC-1")]


def test_preference_api_validates_and_restores_settings(tmp_path):
    repository = populated_repository(tmp_path)
    app        = create_app(repository=repository, crawler=CrawlManager(command=["true"]))
    client     = app.test_client()
    payload = {
        "favorite_manufacturers": ["Qorvo", "qorvo"],
        "favorite_components": [{
            "category": "PA",
            "manufacturer": "Qorvo",
            "part_no": "QPA2212T"
        }],
    }

    response = client.put("/api/preferences", json=payload)

    assert response.status_code == 200
    assert response.get_json()["favorite_manufacturers"] == ["Qorvo"]
    assert client.get("/api/preferences").get_json() == response.get_json()
    assert client.put("/api/preferences", json={"unknown": []}).status_code == 400


def test_favorite_and_pinned_parts_affect_rx_candidates(tmp_path):
    repository = populated_repository(tmp_path)
    app        = create_app(repository=repository, crawler=CrawlManager(command=["true"]))
    client     = app.test_client()
    requirement = {
        "application": "Terminal",
        "direction": "Downlink",
        "center_freq_ghz": 20,
        "channel_bw_mhz": 20,
        "target_throughput_mbps": 40,
        "altitude_km": 888,
        "elevation_deg": 30,
    }
    baseline   = client.post("/api/designs", json={"requirement": requirement}).get_json()
    first_keys = {tuple(component_key(item).values()) for item in baseline["candidates"][0]["components"]}
    preferred = next(
        component_key(component) for candidate in reversed(baseline["candidates"])
        for component in candidate["components"]
        if component["category"] == "LNA" and tuple(component_key(component).values()) not in first_keys
    )
    client.put(
        "/api/preferences",
        json={
            "favorite_manufacturers": [],
            "favorite_components": [preferred]
        },
    )

    ranked = client.post("/api/designs", json={"requirement": requirement}).get_json()
    assert preferred in [component_key(item) for item in ranked["candidates"][0]["components"]]
    assert ranked["candidates"][0]["preference_score"] == 2

    pinned = client.post(
        "/api/designs",
        json={
            "requirement": requirement,
            "pinned_components": [preferred]
        },
    ).get_json()
    assert pinned["candidates"]
    assert all(
        preferred in [component_key(item) for item in candidate["components"]] for candidate in pinned["candidates"]
    )
