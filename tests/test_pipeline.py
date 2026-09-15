from rf_design.datasheet_parser import ExtractedField
from rf_design.csv_repository import ComponentRepository
from rf_design.models import Component
from scripts.pipeline import RESEARCHED_PRODUCT_ROWS, anokiwave_rows_from_html, append_discovered_rows, apply_extracted_fields, discovered_row, find_datasheet_url, import_reference_components, read_rows, resolve_datasheet_url, save_components


def test_find_datasheet_url_uses_official_pdf():
    html = b'<a href="/documents/1234/example-data-sheet.pdf">Data Sheet</a>'
    result = find_datasheet_url("Qorvo", "https://www.qorvo.com/products/p/QPA0001", html)
    assert result == "https://www.qorvo.com/documents/1234/example-data-sheet.pdf"


def test_find_datasheet_url_rejects_unrelated_pdf():
    html = b'<a href="/documents/iso-certificate.pdf">ISO Certificate</a>'
    assert find_datasheet_url("Qorvo", "https://www.qorvo.com/products/p/QPA0001", html) == ""


def test_extracted_fields_feed_component_csv_model():
    component = Component(None, "PA", "Example RF", "PA-30")
    fields    = [
        ExtractedField("freq_min_ghz", 27.0, "GHz", 1, "27 GHz to 31 GHz"),
        ExtractedField("freq_max_ghz", 31.0, "GHz", 1, "27 GHz to 31 GHz"),
        ExtractedField("output_p1db_dbm", 33.0, "dBm", 2, "Output P1dB 33 dBm"),
    ]

    apply_extracted_fields(component, fields)

    assert component.freq_min_ghz == 27.0
    assert component.freq_max_ghz == 31.0
    assert component.specs["output_p1db_dbm"] == 33.0


def test_analog_datasheet_url_is_resolved_without_product_page():
    row = {"manufacturer": "Analog Devices","part_no": "HMC517-DIE","datasheet_url": ""}
    assert resolve_datasheet_url(row).endswith("/hmc517chips.pdf")


def test_downlink_mixer_datasheet_url_is_direct():
    row = {"manufacturer": "Analog Devices","part_no": "HMC8191","datasheet_url": ""}
    assert resolve_datasheet_url(row).endswith("/hmc8191.pdf")


def test_researched_official_pool_covers_multiple_categories():
    categories = {row["category"] for row in RESEARCHED_PRODUCT_ROWS}
    parts      = {row["part_no"] for row in RESEARCHED_PRODUCT_ROWS}

    assert categories == {"PA","LNA","MIXER","PLL"}
    assert {"QPA2211","QPC4610","HMC519-DIE","HMC8192","ADF4371","LMX2595"} <= parts


def test_qorvo_catalog_card_discovers_ka_band_component():
    row = discovered_row(
        "PRODUCTION NEW 17.3 - 21.2 GHz 20 Watt GaN Power Amplifier QPA1724D",
        "https://www.qorvo.com/products/p/QPA1724D",
    )

    assert row is not None
    assert row["category"] == "PA"
    assert row["part_no"] == "QPA1724D"
    assert row["freq_min_ghz"] == 17.3
    assert row["freq_max_ghz"] == 21.2


def test_qorvo_catalog_card_rejects_non_ka_component():
    row = discovered_row(
        "PRODUCTION 3.3 - 4.2 GHz Power Amplifier QPA9862",
        "https://www.qorvo.com/products/p/QPA9862",
    )
    assert row is None


def test_qorvo_catalog_card_rejects_external_sspa():
    row = discovered_row(
        "PRODUCTION 18 - 40 GHz Wideband GaN Solid State Power Amplifier SSPA QPB1840N",
        "https://www.qorvo.com/products/p/QPB1840N",
    )
    assert row is None


def test_discovered_rows_are_appended_once(tmp_path):
    path = tmp_path / "seeds.csv"
    path.write_text("part_no,category,manufacturer\nBASE,PA,Qorvo\n", encoding="utf-8-sig")
    discovered = [{"part_no": "NEW","category": "SWITCH","manufacturer": "Qorvo"}]

    assert len(append_discovered_rows(path, discovered)) == 1
    assert append_discovered_rows(path, discovered) == []
    assert [row["part_no"] for row in read_rows(path)] == ["BASE","NEW"]


def test_anokiwave_catalog_discovers_target_band_bfic():
    html = b'''<a href="awmf-0198/index.html"><div class="productcard">
        <p class="description">AWMF-0198 27.5 - 31 GHz Gen-2 Tx Beamformer IC 4x2 Tx</p>
    </div></a>'''

    rows = anokiwave_rows_from_html(html)

    assert len(rows) == 1
    assert rows[0]["part_no"] == "AWMF-0198"
    assert rows[0]["category"] == "BFIC"
    assert rows[0]["function"] == "Tx"
    assert rows[0]["number_channels"] == 4


def test_reference_bfics_are_added_to_final_component_csv(tmp_path):
    repo = ComponentRepository(tmp_path)
    save_components(repo, [Component(None, "PA", "Qorvo", "QPA2212T")], True)

    count,warnings = import_reference_components(repo)

    assert count == 10
    assert warnings == []
    assert len(repo.list("BFIC")) == 10
    assert len(repo.list()) == 11


def test_partial_refresh_keeps_existing_components(tmp_path):
    repo = ComponentRepository(tmp_path)
    save_components(repo, [Component(None, "PA", "Qorvo", "OLD")], True)

    save_components(repo, [Component(None, "PLL", "TI", "NEW")], False)

    assert {component.part_no for component in repo.list()} == {"OLD","NEW"}


def test_failed_refresh_preserves_previous_extraction(tmp_path):
    repo     = ComponentRepository(tmp_path)
    previous = Component(None, "PA", "Qorvo", "QPA", extraction_method="PDF_TEXT", specs={"pa_gain_db": 22.0})
    failed   = Component(None, "PA", "Qorvo", "QPA", note="추출 실패")
    save_components(repo, [previous], True)

    save_components(repo, [failed], False)

    saved = repo.list()[0]
    assert saved.extraction_method == "PDF_TEXT"
    assert saved.specs["pa_gain_db"] == 22.0
