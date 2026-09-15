import csv

from rf_design.csv_repository import ComponentRepository
from rf_design.models import Component


def test_component_csv_round_trip_and_delete(tmp_path):
    repo      = ComponentRepository(tmp_path / "store")
    component = Component(
        component_id=None,
        category="PA",
        manufacturer="Example RF",
        part_no="PA-30",
        application="Common",
        function="Power Amplifier",
        freq_min_ghz=27.0,
        freq_max_ghz=31.0,
        image_url="https://example.com/pa-30.png",
        grade="Space-grade",
        specs={"gain_db": 24.5,"output_p1db_dbm": 31.0},
    )

    component_id = repo.upsert(component)
    loaded       = repo.get(component_id)

    assert repo.component_path.name == "components.csv"
    assert repo.component_path.exists()
    assert repo.mcs_path.exists()
    assert loaded is not None
    assert loaded.part_no == "PA-30"
    assert loaded.image_url == "https://example.com/pa-30.png"
    assert loaded.grade == "Space-grade"
    assert loaded.specs == {"gain_db": 24.5,"output_p1db_dbm": 31.0}
    with repo.component_path.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert "specs_json" not in row
    assert row["gain_db"] == "24.5"

    repo.delete(component_id)
    assert repo.get(component_id) is None
