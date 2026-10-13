from pathlib import Path

from backend.app import create_app
from backend.app.catalog.crawler import CrawlManager
from backend.app.catalog.repository import ComponentRepository
from backend.runtime import ensure_runtime_data

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_data_is_initialized_in_writable_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("RF_DESIGN_RESOURCE_DIR", str(PROJECT_ROOT))
    monkeypatch.setenv("RF_DESIGN_DATA_DIR", str(tmp_path))

    assert ensure_runtime_data() == tmp_path
    assert (tmp_path / "catalog/manufacturer_product_seeds.csv").is_file()


def test_runtime_data_replaces_an_empty_catalog(monkeypatch, tmp_path):
    (tmp_path / "components.csv").write_text("component_id,category\n", encoding="utf-8")
    monkeypatch.setenv("RF_DESIGN_RESOURCE_DIR", str(PROJECT_ROOT))
    monkeypatch.setenv("RF_DESIGN_DATA_DIR", str(tmp_path))

    ensure_runtime_data()

    assert len((tmp_path / "components.csv").read_text(encoding="utf-8-sig").splitlines()) > 2


def test_desktop_api_requires_session_token(monkeypatch, tmp_path):
    monkeypatch.setenv("RF_DESIGN_API_TOKEN", "test-token")
    repository = ComponentRepository(tmp_path)
    app        = create_app(repository=repository, crawler=CrawlManager(command=["true"]))
    client     = app.test_client()

    assert client.get("/api/health").status_code == 401
    response = client.get("/api/health", headers={"X-RF-Design-Token": "test-token"})
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
