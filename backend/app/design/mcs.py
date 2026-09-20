from __future__ import annotations

from typing import Iterable, Optional

from ..models import MCS


def select_mcs(snr_db: float, table: Iterable[MCS]) -> Optional[MCS]:
    eligible = [row for row in table if row.min_snr_db <= snr_db <= row.max_snr_db]
    if eligible: return max(eligible, key=lambda row: row.spectral_efficiency)
    below = [row for row in table if row.min_snr_db <= snr_db]
    return max(below, key=lambda row: row.spectral_efficiency) if below else None


def calculate_throughput(mcs: Optional[MCS], bandwidth_mhz: float, overhead: float, fill_factor: float = 1.0) -> float:
    if mcs is None: return 0.0
    # R[Mbps] = spectral efficiency[bit/s/Hz] * B[MHz] * usable fraction * fill factor.
    return mcs.spectral_efficiency * bandwidth_mhz * (1.0 - overhead) * fill_factor
