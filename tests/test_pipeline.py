from rf_design.datasheet_parser import ExtractedField
from rf_design.models import Component
from scripts.pipeline import apply_extracted_fields, find_datasheet_url, resolve_datasheet_url


def test_find_datasheet_url_uses_official_pdf():
    html = b'<a href="/documents/1234/example-data-sheet.pdf">Data Sheet</a>'
    result = find_datasheet_url("Qorvo", "https://www.qorvo.com/products/p/QPA0001", html)
    assert result == "https://www.qorvo.com/documents/1234/example-data-sheet.pdf"


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
