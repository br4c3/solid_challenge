import math

import pytest

from rf_design.engine.compatibility import check_bfic_pa, check_frequency, esa_band
from rf_design.engine.link_budget import calculate_gt, combine_snr_db, free_space_path_loss_db, slant_range_km
from rf_design.engine.noise_figure import calculate_receiver_nf
from rf_design.engine.power_chain import calculate_tx_chain
from rf_design.models import Component, LinkRequirement, Status
from rf_design.parsing import parse_power_w
from rf_design.csv_repository import ComponentRepository
from rf_design.engine.link_budget import calculate_link_budget
from rf_design.importer import import_mcs
from pathlib import Path
from rf_design.optimizer import generate_rx_candidates, generate_tx_candidates


def component(category, part_no, **specs):
    return Component(None, category, "Test", part_no, specs=specs)


def test_mixed_power_unit_uses_explicit_value_unit_or_mw_default():
    assert parse_power_w("6500 (8ch 2빔 @21dBm)", "mW / W") == pytest.approx(6.5)
    assert parse_power_w("1.7W@P1dB / 1.0W@5dBBO", "mW / W") == pytest.approx(1.7)


def test_frequency_checks_the_whole_channel():
    req = LinkRequirement("Terminal", "Uplink", 30.0, 100.0, 40.0, 888.0, 30.0)
    item = Component(None, "BFIC", "Test", "BF-1", "Terminal", "Tx", freq_min_ghz=29.96, freq_max_ghz=30.04)
    assert check_frequency(item, req).status == Status.FAIL


def test_esa_bands_reverse_between_terminal_and_payload():
    assert esa_band("Terminal", "Uplink") == (27.5,31.0)
    assert esa_band("Terminal", "Downlink") == (17.7,21.2)
    assert esa_band("Payload", "Uplink") == (27.5,31.0)
    assert esa_band("Payload", "Downlink") == (17.7,21.2)
    assert esa_band("Terminal", "Tx") == (27.5,31.0)
    assert esa_band("Payload", "Tx") == (17.7,21.2)


def test_converter_frequency_uses_if_instead_of_rf():
    req  = LinkRequirement("Terminal", "Downlink", 19.5, 100.0, 40.0, 888.0, 30.0, if_freq_ghz=4.0)
    item = Component(
        None,
        "ADC",
        "Test",
        "ADC-1",
        "Common",
        "ADC",
        freq_min_ghz=0.0,
        freq_max_ghz=7.5,
    )
    result = check_frequency(item, req)
    assert result.status == Status.PASS
    assert "IF" in result.message


def test_bfic_pa_uses_estimated_input_p1db():
    bfic = component("BFIC", "BF", output_p1db_dbm=15.0)
    pa = component("PA", "PA", pa_gain_db=25.0, output_p1db_dbm=35.0)
    result = check_bfic_pa(bfic, pa, 3.0)
    assert result.status == Status.PASS
    assert result.estimated is True
    assert result.details["pa_ip1db_dbm"] == 10.0


def test_tx_chain_automatically_sets_bfic_drive_for_pa_backoff():
    bfic = component("BFIC", "BF", gain_db=28.0, output_p1db_dbm=21.0)
    pa   = component("PA", "PA", pa_gain_db=22.0, psat_dbm=43.4)

    result = calculate_tx_chain([bfic,pa], -7.0, 3.0, automatic_level_control=True)

    assert result.output_dbm == pytest.approx(40.4)
    assert result.status == Status.PASS
    assert result.stages[0].output_dbm == pytest.approx(18.4)
    assert "자동 레벨 제어" in result.stages[0].message


def test_friis_includes_passive_switch_loss_first():
    switch = component("SWITCH", "SW", insertion_loss_db=1.0)
    lna = component("LNA", "LNA", lna_gain_db=20.0, noise_figure_db=2.0)
    gain, nf = calculate_receiver_nf([switch, lna])
    assert gain == pytest.approx(19.0)
    assert nf == pytest.approx(3.0)


def test_linkbudget_matches_reference_workbook_uplink_geometry():
    distance = slant_range_km(888.0, 30.0)
    assert distance == pytest.approx(1531.580691487, rel=1e-9)
    assert free_space_path_loss_db(30.0, distance) == pytest.approx(185.695222746, rel=1e-9)
    temperature, gt = calculate_gt(2.0, 28.5, 30.0, 0.5)
    assert temperature == pytest.approx(199.619025814, rel=1e-9)
    assert gt == pytest.approx(4.997980682, rel=1e-9)
    assert combine_snr_db(6.8047772537, 28.0) == pytest.approx(6.771920989, rel=1e-9)


def test_full_uplink_result_matches_reference_mcs_throughput(tmp_path):
    repo = ComponentRepository(tmp_path / "test-store")
    workbook = next((Path(__file__).parents[1] / "references").glob("4-*.xlsx"))
    assert import_mcs(workbook, repo) == 29
    requirement = LinkRequirement(
        "Terminal", "Uplink", 30.0, 100.0, 40.0, 888.0, 30.0,
        antenna_gain_db=0.0, coherent_gain_db=28.5, receiver_nf_db=2.0,
        atmospheric_loss_db=1.0, output_backoff_db=6.0,
    )
    result = calculate_link_budget(requirement, 43.0, repo.list_mcs())
    assert result.snr_total_db == pytest.approx(6.771920989, rel=1e-9)
    assert result.throughput_mbps == pytest.approx(123.31242, rel=1e-9)
    assert result.result == Status.PASS


def test_full_tx_candidate_generation(tmp_path):
    repo = ComponentRepository(tmp_path / "candidate-store")
    workbook = next((Path(__file__).parents[1] / "references").glob("4-*.xlsx"))
    import_mcs(workbook, repo)
    parts = [
        Component(None, "MIXER", "Test", "MIX", "Common", "Up", specs={"rf_min_ghz": 27.5, "rf_max_ghz": 31.0, "lo_min_ghz": 20.0, "lo_max_ghz": 35.0, "conversion_gain_db": 5.0, "channel_bandwidth_ghz": 1.0, "output_p1db_dbm": 12.0, "lo_drive_min_dbm": 3.0}),
        Component(None, "PLL", "Test", "PLL", "Common", "Frac-N", specs={"output_freq_min_ghz": 20.0, "output_freq_max_ghz": 35.0, "output_power_dbm": 5.0}),
        Component(None, "BFIC", "Test", "BF", "Terminal", "Tx", freq_min_ghz=27.5, freq_max_ghz=31.0, specs={"gain_db": 15.0, "output_p1db_dbm": 15.0, "channel_bandwidth_ghz": 1.0, "number_beams": 1}),
        Component(None, "PA", "Test", "PA", "Terminal", "PA", freq_min_ghz=27.5, freq_max_ghz=31.0, specs={"pa_gain_db": 20.0, "output_p1db_dbm": 35.0}),
    ]
    requirement = LinkRequirement("Terminal", "Uplink", 30.0, 20.0, 40.0, 888.0, 30.0)
    candidates, reasons = generate_tx_candidates(requirement, parts, repo.list_mcs())
    assert reasons == []
    assert len(candidates) == 1
    assert [part.part_no for part in candidates[0].components] == ["MIX", "BF", "PA", "PLL"]


def test_full_rx_candidate_contains_converter_and_pll():
    parts = [
        Component(
            None,
            "LNA",
            "Test",
            "LNA",
            "Terminal",
            "LNA",
            freq_min_ghz=17.0,
            freq_max_ghz=22.0,
            specs={"lna_gain_db": 20.0,"noise_figure_db": 2.0},
        ),
        Component(
            None,
            "BFIC",
            "Test",
            "BF",
            "Terminal",
            "Rx",
            freq_min_ghz=17.7,
            freq_max_ghz=21.2,
            specs={"gain_db": 20.0,"noise_figure_db": 3.0,"channel_bandwidth_ghz": 1.0,"number_beams": 1},
        ),
        Component(
            None,
            "MIXER",
            "Test",
            "MIX",
            "Common",
            "Downconverter",
            specs={"rf_min_ghz": 6.0,"rf_max_ghz": 26.5,"lo_min_ghz": 6.0,"lo_max_ghz": 26.5,"conversion_gain_db": -9.0,"noise_figure_db": 9.0,"channel_bandwidth_ghz": 5.0},
        ),
        Component(
            None,
            "ADC",
            "Test",
            "ADC",
            "Common",
            "ADC",
            freq_min_ghz=0.0,
            freq_max_ghz=7.5,
            specs={"analog_bandwidth_ghz": 7.5},
        ),
        Component(
            None,
            "PLL",
            "Test",
            "PLL",
            "Common",
            "PLL",
            specs={"output_freq_min_ghz": 0.1,"output_freq_max_ghz": 22.0},
        ),
    ]
    requirement = LinkRequirement("Terminal", "Downlink", 19.5, 20.0, 40.0, 888.0, 30.0)

    candidates,reasons = generate_rx_candidates(requirement, parts)

    assert reasons == []
    assert len(candidates) == 1
    assert [part.part_no for part in candidates[0]["components"]] == ["LNA","BF","MIX","ADC","PLL"]
