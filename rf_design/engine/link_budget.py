from __future__ import annotations

import math
from typing import Iterable, Optional

from ..models import LinkBudgetResult, LinkRequirement, MCS, Status
from .mcs import calculate_throughput, select_mcs


EARTH_RADIUS_KM = 6371.0
THERMAL_NOISE_DBM_HZ = -174.0


def slant_range_km(altitude_km: float, elevation_deg: float) -> float:
    angle = math.radians(elevation_deg)
    return math.sqrt((EARTH_RADIUS_KM+altitude_km)**2-(EARTH_RADIUS_KM * math.cos(angle))**2)-EARTH_RADIUS_KM * math.sin(angle)


def free_space_path_loss_db(freq_ghz: float, distance_km: float) -> float:
    if freq_ghz <= 0 or distance_km <= 0: raise ValueError("주파수와 거리는 0보다 커야 합니다.")
    return 92.45+20.0 * math.log10(freq_ghz)+20.0 * math.log10(distance_km)


def calculate_eirp(antenna_input_dbm: float, antenna_gain_db: float, feed_loss_db: float = 0.0, num_beams: int = 1) -> float:
    if num_beams < 1: raise ValueError("빔 수는 1 이상이어야 합니다.")
    return antenna_input_dbm-30.0+antenna_gain_db-feed_loss_db-10.0 * math.log10(num_beams)


def calculate_gt(receiver_nf_db: float, antenna_gain_db: float, sky_temperature_k: float, bf_error_db: float = 0.0):
    system_temperature = 290.0 * (10**(receiver_nf_db / 10.0)-1.0)+sky_temperature_k
    if system_temperature <= 0: raise ValueError("System noise temperature가 0보다 커야 합니다.")
    gt = antenna_gain_db-bf_error_db-10.0 * math.log10(system_temperature)
    return system_temperature,gt


def combine_snr_db(noise_snr_db: float, nonlinear_snr_db: float) -> float:
    return -10.0 * math.log10(10**(-noise_snr_db / 10.0)+10**(-nonlinear_snr_db / 10.0))


def calculate_link_budget(requirement: LinkRequirement, eirp_dbw: float, mcs_table: Iterable[MCS], receiver_nf_db: Optional[float] = None) -> LinkBudgetResult:
    nf = requirement.receiver_nf_db if receiver_nf_db is None else receiver_nf_db
    if nf is None: raise ValueError("Receiver NF가 필요합니다.")

    distance       = slant_range_km(requirement.altitude_km, requirement.elevation_deg)
    fspl           = free_space_path_loss_db(requirement.center_freq_ghz, distance)
    temperature,gt = calculate_gt(nf, requirement.coherent_gain_db, requirement.sky_temperature_k, requirement.bf_error_db)
    eis            = THERMAL_NOISE_DBM_HZ+10.0 * math.log10(requirement.channel_bw_mhz * 1_000_000.0)+nf-requirement.coherent_gain_db
    noise_snr      = eirp_dbw+30.0-fspl-requirement.atmospheric_loss_db-requirement.scintillation_loss_db-requirement.rain_loss_db-eis
    total_snr      = combine_snr_db(noise_snr, requirement.nonlinear_snr_db)
    table          = list(mcs_table)
    mcs            = select_mcs(total_snr, table)
    throughput     = calculate_throughput(mcs, requirement.channel_bw_mhz, requirement.control_overhead, requirement.fill_factor)
    margin         = throughput-requirement.target_throughput_mbps
    needed         = [row for row in table if calculate_throughput(row, requirement.channel_bw_mhz, requirement.control_overhead, requirement.fill_factor) >= requirement.target_throughput_mbps]
    link_margin    = total_snr-min(needed, key=lambda row: row.min_snr_db).min_snr_db if needed else None

    return LinkBudgetResult(distance, fspl, temperature, gt, eis, noise_snr, total_snr, mcs, throughput, margin, Status.PASS if margin >= 0 else Status.FAIL, link_margin)
