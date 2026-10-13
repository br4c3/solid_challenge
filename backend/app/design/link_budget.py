from __future__ import annotations

import math
from typing import Iterable, Optional

from ..models import LinkBudgetResult, LinkRequirement, MCS, Status
from ..formulas import FormulaEngine, default_profile
from .mcs import select_mcs

EARTH_RADIUS_KM      = 6371.0
THERMAL_NOISE_DBM_HZ = -174.0


def _engine(engine: FormulaEngine | None) -> FormulaEngine:
    return engine or FormulaEngine(default_profile())


def slant_range_km(
    altitude_km: float,
    elevation_deg: float,
    engine: FormulaEngine | None = None,
    trace: list[dict] | None = None,
) -> float:
    return _engine(engine).evaluate(
        "slant_range_km", {
            "earth_radius_km": EARTH_RADIUS_KM,
            "altitude_km": altitude_km,
            "elevation_deg": elevation_deg,
        }, trace
    )


def free_space_path_loss_db(
    freq_ghz: float,
    distance_km: float,
    engine: FormulaEngine | None = None,
    trace: list[dict] | None = None,
) -> float:
    if freq_ghz <= 0 or distance_km <= 0: raise ValueError("Frequency and distance must be greater than zero.")
    return _engine(engine).evaluate("fspl_db", {"frequency_ghz": freq_ghz, "distance_km": distance_km}, trace)


def calculate_eirp(
    antenna_input_dbm: float, antenna_gain_db: float, feed_loss_db: float = 0.0, num_beams: int = 1
) -> float:
    if num_beams < 1: raise ValueError("Number of beams must be at least one.")
    # EIRP[dBW] = Pin[dBm]-30 + Gantenna-Lfeed - 10*log10(Nbeams).
    return calculate_peak_eirp(antenna_input_dbm, antenna_gain_db, feed_loss_db) - 10.0 * math.log10(num_beams)


def calculate_peak_eirp(
    antenna_input_dbm: float,
    antenna_gain_db: float,
    feed_loss_db: float = 0.0,
    formula_engine: FormulaEngine | None = None,
    calculation_trace: list[dict] | None = None,
) -> float:
    return _engine(formula_engine).evaluate(
        "peak_eirp_dbw", {
            "antenna_input_dbm": antenna_input_dbm,
            "antenna_gain_db": antenna_gain_db,
            "feed_loss_db": feed_loss_db,
        }, calculation_trace
    )


def calculate_gt(receiver_nf_db: float, antenna_gain_db: float, sky_temperature_k: float, bf_error_db: float = 0.0):
    # Te[K] = 290*(10^(NF/10)-1); Tsys adds the antenna sky temperature.
    system_temperature = 290.0 * (10**(receiver_nf_db / 10.0) - 1.0) + sky_temperature_k
    if system_temperature <= 0: raise ValueError("System noise temperature must be greater than zero.")
    # G/T[dB/K] = Gantenna-Gerror-10*log10(Tsys).
    gt = antenna_gain_db - bf_error_db - 10.0 * math.log10(system_temperature)
    return system_temperature, gt


def combine_snr_db(noise_snr_db: float, nonlinear_snr_db: float) -> float:
    # Independent impairments combine as 1/SNRtotal = 1/SNRnoise + 1/SNRnonlinear.
    return -10.0 * math.log10(10**(-noise_snr_db / 10.0) + 10**(-nonlinear_snr_db / 10.0))


def calculate_link_budget(
    requirement: LinkRequirement,
    peak_eirp_dbw: float,
    mcs_table: Iterable[MCS],
    receiver_nf_db: Optional[float] = None,
    formula_engine: FormulaEngine | None = None,
    calculation_trace: list[dict] | None = None,
) -> LinkBudgetResult:
    engine = _engine(formula_engine)
    trace  = calculation_trace
    nf     = requirement.receiver_nf_db if receiver_nf_db is None else receiver_nf_db
    if nf is None: raise ValueError("Receiver noise figure is required.")

    # D and F: boresight range equals altitude; maximum range uses the requested elevation angle.
    boresight_range = requirement.altitude_km
    slant_range     = slant_range_km(requirement.altitude_km, requirement.elevation_deg, engine, trace)

    # H, I, K, L: split composite peak EIRP by beam count and apply output backoff.
    peak_per_beam_eirp     = peak_eirp_dbw - 10.0 * math.log10(requirement.num_beams)
    composite_backoff_eirp = peak_eirp_dbw - requirement.output_backoff_db
    linear_per_beam_eirp = engine.evaluate(
        "beam_eirp_dbw", {
            "peak_eirp_dbw": peak_eirp_dbw,
            "num_beams": requirement.num_beams,
            "output_backoff_db": requirement.output_backoff_db,
        }, trace
    )

    # M and N: free-space path loss at boresight and maximum slant range.
    boresight_path_loss = free_space_path_loss_db(requirement.center_freq_ghz, boresight_range, engine, trace)
    max_slant_path_loss = free_space_path_loss_db(requirement.center_freq_ghz, slant_range, engine, trace)
    temperature = engine.evaluate(
        "system_temperature_k", {
            "receiver_nf_db": nf,
            "sky_temperature_k": requirement.sky_temperature_k,
        }, trace
    )
    gt = engine.evaluate(
        "gt_db_per_k", {
            "antenna_gain_db": requirement.coherent_gain_db,
            "bf_error_db": requirement.bf_error_db,
            "system_temperature_k": temperature,
        }, trace
    )
    # Equivalent input noise[dBm] = -174 + 10*log10(B[Hz]) + NF - Grx.
    eis = engine.evaluate(
        "eis_dbm", {
            "thermal_noise_dbm_hz": THERMAL_NOISE_DBM_HZ,
            "bandwidth_mhz": requirement.channel_bw_mhz,
            "receiver_nf_db": nf,
            "receiver_gain_db": requirement.coherent_gain_db,
        }, trace
    )
    propagation_loss = requirement.atmospheric_loss_db + requirement.scintillation_loss_db + requirement.rain_loss_db

    # Y and AB: noise-limited SNR = L[dBW]+30-path loss-environment loss-EIS[dBm].
    boresight_noise_snr = engine.evaluate(
        "noise_snr_db", {
            "eirp_dbw": linear_per_beam_eirp,
            "path_loss_db": boresight_path_loss,
            "propagation_loss_db": propagation_loss,
            "eis_dbm": eis,
        }, trace
    )
    max_slant_noise_snr = engine.evaluate(
        "noise_snr_db", {
            "eirp_dbw": linear_per_beam_eirp,
            "path_loss_db": max_slant_path_loss,
            "propagation_loss_db": propagation_loss,
            "eis_dbm": eis,
        }, trace
    )

    # Z and AC are direct nonlinearity limits for boresight and maximum slant range.
    boresight_nonlinear_snr = requirement.nonlinear_snr_db
    max_slant_nonlinear_snr = requirement.max_slant_nonlinear_snr_db

    # AA and AD: combine thermal-noise and nonlinearity SNR in the linear domain.
    boresight_total_snr = engine.evaluate(
        "combined_snr_db", {
            "noise_snr_db": boresight_noise_snr,
            "nonlinear_snr_db": boresight_nonlinear_snr,
        }, trace
    )
    max_slant_total_snr = engine.evaluate(
        "combined_snr_db", {
            "noise_snr_db": max_slant_noise_snr,
            "nonlinear_snr_db": max_slant_nonlinear_snr,
        }, trace
    )

    # AE and AF: select the highest-efficiency MCS whose SNR interval contains each total SNR.
    table   = list(mcs_table)
    max_mcs = select_mcs(boresight_total_snr, table)
    min_mcs = select_mcs(max_slant_total_snr, table)

    # AG and AH: throughput = spectral efficiency * bandwidth * (1-overhead) * resource factor.
    def throughput(mcs: Optional[MCS], record: bool = True) -> float:
        return engine.evaluate(
            "throughput_mbps", {
                "spectral_efficiency": mcs.spectral_efficiency if mcs else 0.0,
                "bandwidth_mhz": requirement.channel_bw_mhz,
                "control_overhead": requirement.control_overhead,
                "fill_factor": requirement.fill_factor,
            }, trace if record else None
        )

    max_throughput = throughput(max_mcs)
    min_throughput = throughput(min_mcs)
    # Throughput and link margins are signed available-minus-required values.
    margin = engine.evaluate(
        "throughput_margin_mbps", {
            "throughput_mbps": min_throughput,
            "target_throughput_mbps": requirement.target_throughput_mbps,
        }, trace
    )
    needed = [row for row in table if throughput(row, record=False) >= requirement.target_throughput_mbps]
    link_margin = engine.evaluate(
        "link_margin_db", {
            "total_snr_db": max_slant_total_snr,
            "required_snr_db": min(needed, key=lambda row: row.min_snr_db).min_snr_db,
        }, trace
    ) if needed else None

    return LinkBudgetResult(
        slant_range_km=slant_range,
        fspl_db=max_slant_path_loss,
        system_noise_temperature_k=temperature,
        gt_db_per_k=gt,
        eis_dbm=eis,
        snr_noise_db=max_slant_noise_snr,
        snr_total_db=max_slant_total_snr,
        mcs=min_mcs,
        throughput_mbps=min_throughput,
        throughput_margin_mbps=margin,
        result=Status.PASS if margin >= 0 else Status.FAIL,
        link_margin_db=link_margin,
        boresight_range_km=boresight_range,
        peak_eirp_dbw=peak_eirp_dbw,
        peak_eirp_per_beam_dbw=peak_per_beam_eirp,
        composite_eirp_backoff_dbw=composite_backoff_eirp,
        linear_eirp_per_beam_dbw=linear_per_beam_eirp,
        boresight_path_loss_db=boresight_path_loss,
        max_slant_path_loss_db=max_slant_path_loss,
        boresight_noise_snr_db=boresight_noise_snr,
        boresight_nonlinear_snr_db=boresight_nonlinear_snr,
        boresight_total_snr_db=boresight_total_snr,
        max_slant_noise_snr_db=max_slant_noise_snr,
        max_slant_nonlinear_snr_db=max_slant_nonlinear_snr,
        max_slant_total_snr_db=max_slant_total_snr,
        max_mcs=max_mcs,
        min_mcs=min_mcs,
        max_throughput_mbps=max_throughput,
        min_throughput_mbps=min_throughput,
    )
