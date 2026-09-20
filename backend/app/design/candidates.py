from __future__ import annotations

import itertools
from typing import Dict, Iterable, List, Sequence, Tuple

from .compatibility import check_bfic_pa, check_component, check_pll_mixer, overall_status, required_function
from .link_budget import calculate_link_budget, calculate_peak_eirp
from .noise_figure import calculate_receiver_nf
from .power_chain import calculate_tx_chain
from ..models import CheckResult, Component, LinkRequirement, MCS, RxCandidate, Status, TxCandidate


def filter_components(components: Iterable[Component],
                      requirement: LinkRequirement) -> Tuple[List[Component], Dict[int, List[CheckResult]]]:
    accepted, results = [], {}
    for component in components:
        checks                                           = check_component(component, requirement)
        results[component.component_id or id(component)] = checks
        if overall_status(checks) != Status.FAIL:
            accepted.append(component)
    return accepted, results


def _by_category(components: Iterable[Component]) -> Dict[str, List[Component]]:
    groups: Dict[str, List[Component]] = {}
    for component in components:
        groups.setdefault(component.category.upper(), []).append(component)
        if component.category.upper() == "FEM":
            groups.setdefault("PA", []).append(component)
            groups.setdefault("LNA", []).append(component)
    return groups


def _total_power(components: Sequence[Component]):
    values = [component.power_consumption_w for component in components]
    return sum(value for value in values if value is not None) if any(value is not None for value in values) else None


def _commercial_count(components: Sequence[Component]) -> int:
    return sum(component.grade != "Space-grade" for component in components)


def generate_tx_candidates(
    requirement: LinkRequirement,
    components: Iterable[Component],
    mcs_table: Iterable[MCS],
    limit: int = 5000
) -> Tuple[List[TxCandidate], List[str]]:
    accepted, _ = filter_components(components, requirement)
    groups      = _by_category(accepted)
    required    = ["MIXER", "PLL", "BFIC", "PA"]
    missing     = [category for category in required if not groups.get(category)]
    if missing: return [], [f"No {category} candidate is available." for category in missing]
    switches                      = [None] + groups.get("SWITCH", [])
    converters                    = groups.get("DAC") or groups.get("CONVERTER") or [None]
    candidates: List[TxCandidate] = []
    combinations                  = itertools.product(converters, groups["MIXER"], groups["PLL"], groups["BFIC"], groups["PA"], switches)
    for index, (converter, mixer, pll, bfic, pa, switch) in enumerate(combinations):
        if index >= limit: break
        pair_checks = [
            check_pll_mixer(
                pll, mixer, requirement.center_freq_ghz, requirement.if_freq_ghz, requirement.lo_routing_loss_db
            ),
            check_bfic_pa(bfic, pa, requirement.output_backoff_db),
        ]
        if any(check.status == Status.FAIL for check in pair_checks): continue
        chain = [component for component in (converter, mixer, bfic, pa, switch) if component is not None]
        power = calculate_tx_chain(
            chain,
            requirement.tx_input_power_dbm,
            requirement.output_backoff_db,
            automatic_level_control=True,
        )
        peak_eirp = calculate_peak_eirp(
            power.output_dbm + requirement.output_backoff_db,
            requirement.antenna_gain_db,
            requirement.feed_loss_db,
        )
        link = calculate_link_budget(requirement, peak_eirp, mcs_table)
        eirp = link.linear_eirp_per_beam_dbw
        candidates.append(TxCandidate(chain + [pll], pair_checks, power, eirp, link, _total_power(chain + [pll])))
    candidates.sort(
        key=lambda item: (
            item.status != Status.PASS,
            _commercial_count(item.components) if requirement.application.lower() == "payload" else 0,
            -(
                item.link_budget.link_margin_db
                if item.link_budget and item.link_budget.link_margin_db is not None else -9999
            ),
            -(item.link_budget.throughput_margin_mbps if item.link_budget else -9999),
            item.total_power_w if item.total_power_w is not None else 9999,
            len(item.components),
        )
    )
    if not candidates: return [], ["No Tx combination satisfies the LO and output constraints."]
    return candidates, []


def generate_rx_candidates(requirement: LinkRequirement,
                           components: Iterable[Component],
                           limit: int = 5000) -> Tuple[List[RxCandidate], List[str]]:
    accepted, _ = filter_components(components, requirement)
    groups      = _by_category(accepted)
    required    = ["LNA", "BFIC", "MIXER", "PLL"]
    missing     = [category for category in required if not groups.get(category)]
    if missing: return [], [f"No {category} candidate is available." for category in missing]
    switches   = groups.get("SWITCH") or [None]
    converters = groups.get("ADC") or groups.get("CONVERTER") or [None]
    results    = []
    combinations = itertools.product(
        switches, groups["LNA"], groups["BFIC"], groups["MIXER"], converters, groups["PLL"]
    )
    for index, (switch, lna, bfic, mixer, converter, pll) in enumerate(combinations):
        if index >= limit: break
        lo_check = check_pll_mixer(
            pll, mixer, requirement.center_freq_ghz, requirement.if_freq_ghz, requirement.lo_routing_loss_db
        )
        if lo_check.status == Status.FAIL: continue
        rf_chain = [component for component in (switch, lna, bfic, mixer) if component is not None]
        try:
            gain, nf = calculate_receiver_nf(rf_chain)
        except ValueError:
            continue
        chain = rf_chain + [component for component in (converter, pll) if component is not None]
        results.append(RxCandidate(chain, [lo_check], gain, nf, _total_power(chain)))
    results.sort(
        key=lambda item: (
            _commercial_count(item.components) if requirement.application.lower() == "payload" else 0,
            item.total_nf_db,
            -item.total_gain_db,
            item.total_power_w if item.total_power_w is not None else 9999,
        )
    )
    if not results: return [], ["No Rx combination satisfies the LO, gain, and noise-figure constraints."]
    return results, []
