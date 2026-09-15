from rf_design.datasheet_parser import extract_fields_from_pages


def test_datasheet_fields_include_page_and_evidence():
    rows = extract_fields_from_pages([
        "Features: 27.5 GHz to 31 GHz. Small signal gain: 24 dB. Output P1dB: 32 dBm.",
        "Noise Figure: 2.1 dB. PAE: 28 %.",
    ])
    values = {row.field: row for row in rows}
    assert values["freq_min_ghz"].value == 27.5
    assert values["freq_max_ghz"].value == 31.0
    assert values["output_p1db_dbm"].value == 32.0
    assert values["noise_figure_db"].page == 2
    assert values["pae_percent"].evidence == "PAE: 28 %"


def test_pll_mixed_frequency_units_and_test_condition_are_distinguished():
    rows = extract_fields_from_pages([
        "LMX2624-SP Wide band frequency synthesizer: 5 MHz to 30 GHz output frequency. "
        "Test condition RFOUTA from 9.5 GHz to 9.52 GHz. Phase noise: -102 dBc/Hz at 100 kHz."
    ], category="PLL")
    values = {row.field: row.value for row in rows}
    assert values["output_freq_min_ghz"] == 0.005
    assert values["output_freq_max_ghz"] == 30.0
    assert values["phase_noise_100khz"] == -102.0


def test_invalid_phase_noise_value_is_rejected():
    rows = extract_fields_from_pages(["Phase noise: 102 dBc/Hz at 100 kHz."], category="PLL")
    assert "phase_noise_100khz" not in {row.field for row in rows}


def test_pa_gain_does_not_use_input_power_test_condition():
    rows = extract_fields_from_pages([
        "Gain (PIN = 26 dBm): 14.4 dB. Small signal gain: 24.8 dB. PAE: 22.6 %."
    ], category="PA")
    values = {row.field: row.value for row in rows}
    assert values["pa_gain_db"] == 24.8
    assert values["pa_pae_percent"] == 22.6


def test_adc_ignores_unrelated_noise_and_phase_noise_values():
    rows = extract_fields_from_pages([
        "12-bit 6 GSPS ADC. Noise figure: 25.3 dB. Phase noise -105 dBc/Hz at 100 kHz."
    ], category="ADC")
    values = {row.field: row.value for row in rows}
    assert values == {"resolution_bit": 12.0,"sample_rate_gsps": 6.0}
