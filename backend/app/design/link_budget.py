from __future__ import annotations

import math
from typing import Iterable, Optional

from ..models import LinkBudgetResult, LinkRequirement, MCS, Status
from .mcs import calculate_throughput, select_mcs

EARTH_RADIUS_KM      = 6371.0
THERMAL_NOISE_DBM_HZ = -174.0


def slant_range_km(altitude_km: float, elevation_deg: float) -> float:
    angle = math.radians(elevation_deg)
    # Slant range from spherical-Earth geometry: sqrt((Re+h)^2-(Re*cos(e))^2)-Re*sin(e).
    return math.sqrt((EARTH_RADIUS_KM + altitude_km)**2 -
                     (EARTH_RADIUS_KM * math.cos(angle))**2) - EARTH_RADIUS_KM * math.sin(angle)


def free_space_path_loss_db(freq_ghz: float, distance_km: float) -> float:
    if freq_ghz <= 0 or distance_km <= 0: raise ValueError("Frequency and distance must be greater than zero.")
    # FSPL[dB] = 92.45 + 20*log10(f[GHz]) + 20*log10(d[km]).
    return 92.45 + 20.0 * math.log10(freq_ghz) + 20.0 * math.log10(distance_km)


def calculate_eirp(
    antenna_input_dbm: float, antenna_gain_db: float, feed_loss_db: float = 0.0, num_beams: int = 1
) -> float:
    if num_beams < 1: raise ValueError("Number of beams must be at least one.")
    # EIRP[dBW] = Pin[dBm]-30 + Gantenna-Lfeed - 10*log10(Nbeams).
    return calculate_peak_eirp(antenna_input_dbm, antenna_gain_db, feed_loss_db) - 10.0 * math.log10(num_beams)


def calculate_peak_eirp(antenna_input_dbm: float, antenna_gain_db: float, feed_loss_db: float = 0.0) -> float:
    # Composite peak EIRP[dBW] = Pin[dBm]-30 + Gantenna[dB] - Lfeed[dB].
    return antenna_input_dbm - 30.0 + antenna_gain_db - feed_loss_db


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
    receiver_nf_db: Optional[float] = None
) -> LinkBudgetResult:
    nf = requirement.receiver_nf_db if receiver_nf_db is None else receiver_nf_db
    if nf is None: raise ValueError("Receiver noise figure is required.")

    # D and F: boresight range equals altitude; maximum range uses the requested elevation angle.
    boresight_range = requirement.altitude_km
    slant_range     = slant_range_km(requirement.altitude_km, requirement.elevation_deg)

    # H, I, K, L: split composite peak EIRP by beam count and apply output backoff.
    peak_per_beam_eirp     = peak_eirp_dbw - 10.0 * math.log10(requirement.num_beams)
    composite_backoff_eirp = peak_eirp_dbw - requirement.output_backoff_db
    linear_per_beam_eirp   = peak_per_beam_eirp - requirement.output_backoff_db

    # M and N: free-space path loss at boresight and maximum slant range.
    boresight_path_loss = free_space_path_loss_db(requirement.center_freq_ghz, boresight_range)
    max_slant_path_loss = free_space_path_loss_db(requirement.center_freq_ghz, slant_range)
    temperature, gt = calculate_gt(
        nf, requirement.coherent_gain_db, requirement.sky_temperature_k, requirement.bf_error_db
    )
    # Equivalent input noise[dBm] = -174 + 10*log10(B[Hz]) + NF - Grx.
    eis = THERMAL_NOISE_DBM_HZ + 10.0 * math.log10(
        requirement.channel_bw_mhz * 1_000_000.0
    ) + nf - requirement.coherent_gain_db
    propagation_loss = requirement.atmospheric_loss_db + requirement.scintillation_loss_db + requirement.rain_loss_db

    # Y and AB: noise-limited SNR = L[dBW]+30-path loss-environment loss-EIS[dBm].
    boresight_noise_snr = linear_per_beam_eirp + 30.0 - boresight_path_loss - propagation_loss - eis
    max_slant_noise_snr = linear_per_beam_eirp + 30.0 - max_slant_path_loss - propagation_loss - eis

    # Z and AC are direct nonlinearity limits for boresight and maximum slant range.
    boresight_nonlinear_snr = requirement.nonlinear_snr_db
    max_slant_nonlinear_snr = requirement.max_slant_nonlinear_snr_db

    # AA and AD: combine thermal-noise and nonlinearity SNR in the linear domain.
    boresight_total_snr = combine_snr_db(boresight_noise_snr, boresight_nonlinear_snr)
    max_slant_total_snr = combine_snr_db(max_slant_noise_snr, max_slant_nonlinear_snr)

    # AE and AF: select the highest-efficiency MCS whose SNR interval contains each total SNR.
    table   = list(mcs_table)
    max_mcs = select_mcs(boresight_total_snr, table)
    min_mcs = select_mcs(max_slant_total_snr, table)

    # AG and AH: throughput = spectral efficiency * bandwidth * (1-overhead) * resource factor.
    max_throughput = calculate_throughput(
        max_mcs, requirement.channel_bw_mhz, requirement.control_overhead, requirement.fill_factor
    )
    min_throughput = calculate_throughput(
        min_mcs, requirement.channel_bw_mhz, requirement.control_overhead, requirement.fill_factor
    )
    # Throughput and link margins are signed available-minus-required values.
    margin = min_throughput - requirement.target_throughput_mbps
    needed = [
        row for row in table
        if calculate_throughput(row, requirement.channel_bw_mhz, requirement.control_overhead, requirement.fill_factor)
        >= requirement.target_throughput_mbps
    ]
    link_margin = max_slant_total_snr - min(needed, key=lambda row: row.min_snr_db).min_snr_db if needed else None

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
