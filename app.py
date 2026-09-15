from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

from rf_design.csv_repository import ComponentRepository
from rf_design.datasheet_parser import parse_datasheet_pdf
from rf_design.engine.compatibility import check_component, esa_band, overall_status, required_function
from rf_design.engine.link_budget import calculate_eirp, calculate_link_budget
from rf_design.importer import import_components_csv, import_mcs
from rf_design.models import Component, LinkRequirement, Status
from rf_design.optimizer import generate_rx_candidates, generate_tx_candidates


ROOT        = Path(__file__).resolve().parent
STATUS_ICON = {Status.PASS: "✅", Status.WARN: "⚠️", Status.FAIL: "❌", Status.UNKNOWN: "❔"}


@st.cache_resource
def repository() -> ComponentRepository:
    repo = ComponentRepository()
    if not repo.list_mcs():
        books = list((ROOT / "references").glob("4-*.xlsx"))
        if books:
            import_mcs(books[0], repo)
    return repo


def default_requirement() -> LinkRequirement:
    return LinkRequirement("Terminal", "Uplink", 29.25, 20.0, 40.0, 888.0, 30.0)


def component_rows(items):
    rows = []
    for item in items:
        row = {
            "ID": item.component_id, "Block": item.category, "Manufacturer": item.manufacturer,
            "Part No.": item.part_no, "Application": item.application, "Function": item.function, "Grade": item.grade,
            "Freq Min (GHz)": item.freq_min_ghz, "Freq Max (GHz)": item.freq_max_ghz,
            "Power (W)": item.power_consumption_w, "Extraction": item.extraction_method,
            "Datasheet": item.datasheet_url, "Note": item.note,
        }
        row.update(item.specs)
        rows.append(row)
    return rows


def show_purchase_list(candidate):
    st.subheader("구매 부품 상세")
    st.caption("평가용 단일 RF chain 기준으로 각 1개입니다. 실제 배열의 BFIC·PA 수량은 안테나 소자 수를 정한 뒤 산정하고, 제조사 페이지에서 재고와 수명주기를 최종 확인하세요.")
    for index,item in enumerate(candidate.components, start=1):
        with st.container(border=True):
            st.markdown(f"#### {index}. {item.part_no}")
            st.write(f"**제조사:** {item.manufacturer}  \n**역할:** {item.category} · {item.function or '-'}  \n**등급:** {item.grade}  \n**평가용 수량:** 1개  \n**패키지:** {item.package or '확인 필요'}")
            if item.freq_min_ghz is not None and item.freq_max_ghz is not None:
                st.write(f"**주파수:** {item.freq_min_ghz:g}~{item.freq_max_ghz:g} GHz")
            links = st.columns(2)
            if item.product_url: links[0].link_button("제품·구매 페이지", item.product_url, width="stretch")
            else: links[0].caption("제품·구매 링크 확인 필요")
            if item.datasheet_url: links[1].link_button("데이터시트", item.datasheet_url, width="stretch")
            else: links[1].caption("데이터시트 링크 확인 필요")


def page_components(repo: ComponentRepository):
    st.header("Component CSV")
    col1,col2 = st.columns([2,1])
    with col1:
        uploaded = st.file_uploader("정규화 Component CSV 가져오기", type=["csv"])
    with col2:
        st.write("")
        if uploaded and st.button("CSV Import", width="stretch"):
            temp = ROOT / "data/uploaded_components.csv"
            temp.write_bytes(uploaded.getvalue())
            count = import_components_csv(temp, repo)
            st.success(f"{count}개 부품을 저장했습니다.")
            st.rerun()

    categories      = ["ALL"]+sorted({item.category for item in repo.list()})
    selected        = st.selectbox("Block", categories)
    items           = repo.list(None if selected == "ALL" else selected)
    component_frame = pd.DataFrame(component_rows(items))
    st.dataframe(component_frame, width="stretch", hide_index=True)
    st.download_button("현재 목록 CSV 다운로드", component_frame.to_csv(index=False).encode("utf-8-sig"), "components_export.csv", "text/csv")

    with st.expander("Datasheet PDF 자동 추출 및 검토"):
        pdf_category = st.selectbox("PDF Category", ["BFIC","PA","LNA","SWITCH","MIXER","PLL","ADC","DAC"])
        pdf          = st.file_uploader("Datasheet PDF", type=["pdf"], key="datasheet_pdf")
        if pdf and st.button("필드 후보 추출"):
            try:
                st.session_state.pdf_fields = parse_datasheet_pdf(pdf.getvalue(), pdf_category)
            except Exception as exc:
                st.error(f"PDF를 읽을 수 없습니다: {exc}")
        fields = st.session_state.get("pdf_fields", [])
        if fields:
            st.caption("자동 추출값은 저장 전에 반드시 수정·확인하세요. Page와 evidence가 함께 저장 근거가 됩니다.")
            edited          = st.data_editor(pd.DataFrame(fields), width="stretch", hide_index=True, key="pdf_field_editor")
            p1,p2           = st.columns(2)
            pdf_manufacturer = p1.text_input("PDF Manufacturer")
            pdf_part         = p2.text_input("PDF Part No.")
            if st.button("검토값을 CSV에 저장", type="primary"):
                if not pdf_manufacturer.strip() or not pdf_part.strip():
                    st.error("Manufacturer와 Part No.를 입력하세요.")
                else:
                    values = {row["field"]: float(row["value"]) for row in edited.to_dict("records")}
                    freq_min,freq_max = values.pop("freq_min_ghz", None),values.pop("freq_max_ghz", None)
                    pages             = sorted({str(row["page"]) for row in edited.to_dict("records")})
                    component = Component(
                        None,
                        pdf_category,
                        pdf_manufacturer.strip(),
                        pdf_part.strip(),
                        freq_min_ghz=freq_min,
                        freq_max_ghz=freq_max,
                        datasheet_page=",".join(pages),
                        source_file=pdf.name if pdf else None,
                        note="PDF automatic extraction; user reviewed",
                        specs=values,
                    )
                    repo.upsert(component)
                    st.session_state.pdf_fields = []
                    st.success("검토된 값을 저장했습니다.")
                    st.rerun()

    st.subheader("수동 추가 / 수정")
    choices = {"새 부품": None, **{f"#{item.component_id} {item.part_no}": item for item in repo.list()}}
    label   = st.selectbox("편집 대상", list(choices))
    current = choices[label]
    with st.form("component_form"):
        categories    = ["BFIC","PA","LNA","SWITCH","MIXER","PLL","ADC","DAC"]
        applications  = ["Common","Terminal","Payload"]
        grades        = ["Commercial-grade","Space-grade"]
        c1,c2,c3       = st.columns(3)
        category       = c1.selectbox("Category", categories, index=categories.index(current.category) if current and current.category in categories else 0)
        manufacturer   = c2.text_input("Manufacturer", current.manufacturer if current else "")
        part_no        = c3.text_input("Part No.", current.part_no if current else "")
        application    = c1.selectbox("Application", applications, index=applications.index(current.application) if current and current.application in applications else 0)
        function       = c2.text_input("Function", current.function if current else "")
        datasheet      = c3.text_input("Datasheet URL", current.datasheet_url or "" if current else "")
        grade          = c1.selectbox("Grade", grades, index=grades.index(current.grade) if current and current.grade in grades else 0)
        freq_min       = c1.number_input("Freq Min (GHz)", value=float(current.freq_min_ghz or 0) if current else 0.0)
        freq_max       = c2.number_input("Freq Max (GHz)", value=float(current.freq_max_ghz or 0) if current else 0.0)
        power_w        = c3.number_input("DC Power (W)", min_value=0.0, value=float(current.power_consumption_w or 0) if current else 0.0)
        gain_value     = current.value("gain_db", "pa_gain_db", "lna_gain_db", "conversion_gain_db") if current else None
        gain_text      = c1.text_input("Gain (dB, 빈 값=NULL)", "" if gain_value is None else str(gain_value))
        p1_value       = current.value("output_p1db_dbm") if current else None
        p1_text        = c2.text_input("Output P1dB (dBm, 빈 값=NULL)", "" if p1_value is None else str(p1_value))
        nf_value       = current.value("noise_figure_db") if current else None
        nf_text        = c3.text_input("Noise Figure (dB, 빈 값=NULL)", "" if nf_value is None else str(nf_value))
        specs_text     = st.text_area(
            "Advanced specs (JSON)",
            json.dumps(current.specs if current else {}, ensure_ascii=False, indent=2),
            help="PLL/Mixer 범위 등 category별 필드는 JSON으로 입력할 수 있습니다.",
        )
        submitted = st.form_submit_button("저장", type="primary")
        if submitted:
            if not manufacturer.strip() or not part_no.strip():
                st.error("Manufacturer와 Part No.는 필수입니다.")
            else:
                try:
                    specs    = json.loads(specs_text or "{}")
                    gain_key = {"PA": "pa_gain_db", "LNA": "lna_gain_db", "MIXER": "conversion_gain_db"}.get(category, "gain_db")
                    for key,text in ((gain_key,gain_text),("output_p1db_dbm",p1_text),("noise_figure_db",nf_text)):
                        if text.strip():
                            specs[key] = float(text)
                        else:
                            specs.pop(key, None)
                    component = Component(
                        current.component_id if current else None,
                        category,
                        manufacturer.strip(),
                        part_no.strip(),
                        application,
                        function.strip(),
                        freq_min_ghz=freq_min or None,
                        freq_max_ghz=freq_max or None,
                        power_consumption_w=power_w or None,
                        datasheet_url=datasheet or None,
                        grade=grade,
                        specs=specs,
                    )
                    repo.upsert(component)
                except (ValueError, json.JSONDecodeError) as exc:
                    st.error(f"숫자 또는 JSON 형식을 확인하세요: {exc}")
                else:
                    st.success("저장했습니다.")
                    st.rerun()
    if current and st.button("선택 부품 삭제", type="secondary"):
        repo.delete(current.component_id)
        st.rerun()


def requirement_form():
    st.header("Requirement")
    req = st.session_state.get("requirement", default_requirement())
    with st.form("requirement_form"):
        directions = ["Uplink","Downlink","Tx","Rx"]
        c1,c2,c3    = st.columns(3)
        application = c1.selectbox("Application", ["Terminal","Payload"], index=0 if req.application == "Terminal" else 1)
        direction   = c2.selectbox("Direction", directions, index=directions.index(req.direction))
        center      = c3.number_input("Center Frequency (GHz)", min_value=0.001, value=req.center_freq_ghz)
        auto_band   = c3.checkbox("ESA 표준 대역 자동 적용", value=True)
        bw          = c1.number_input("Channel BW (MHz)", min_value=0.001, value=req.channel_bw_mhz)
        target      = c2.number_input("Target Throughput (Mbps)", min_value=0.0, value=req.target_throughput_mbps)
        beams       = c3.number_input("Number of Beams", min_value=1, value=req.num_beams, step=1)
        altitude    = c1.number_input("Altitude / Boresight Range (km)", min_value=0.001, value=req.altitude_km)
        elevation   = c2.number_input("Elevation (deg)", min_value=0.0, max_value=90.0, value=req.elevation_deg)
        antenna     = c3.number_input("Tx Antenna Gain (dBi)", value=req.antenna_gain_db)
        coherent    = c1.number_input("Rx Coherent Gain (dB)", value=req.coherent_gain_db, help="BFIC single-channel gain과 별도인 antenna/array 값")
        receiver_nf = c2.number_input("Receiver NF (dB)", min_value=0.0, value=float(req.receiver_nf_db or 0))
        sky         = c3.number_input("Sky Temperature (K)", min_value=0.01, value=req.sky_temperature_k)
        atmosphere  = c1.number_input("Atmospheric Loss (dB)", min_value=0.0, value=req.atmospheric_loss_db)
        rain        = c2.number_input("Rain Loss (dB)", min_value=0.0, value=req.rain_loss_db)
        scintillation = c3.number_input("Scintillation Loss (dB)", min_value=0.0, value=req.scintillation_loss_db)
        overhead    = c1.number_input("Control Overhead", min_value=0.0, max_value=0.99, value=req.control_overhead)
        fill        = c2.number_input("Fill Factor", min_value=0.0, max_value=1.0, value=req.fill_factor, format="%.5f")
        if_freq     = c3.number_input("IF Frequency (GHz)", min_value=0.0, value=float(req.if_freq_ghz or 0))
        feed        = c1.number_input("Feed Loss (dB)", min_value=0.0, value=req.feed_loss_db)
        backoff     = c2.number_input("Output Back-off (dB)", min_value=0.0, value=req.output_backoff_db)
        tx_input    = c3.number_input("Tx Chain Input (dBm)", value=req.tx_input_power_dbm)
        saved       = st.form_submit_button("요구조건 저장", type="primary")
    if saved:
        selected_band = esa_band(application, direction)
        if auto_band and selected_band: center = sum(selected_band) / 2
        st.session_state.requirement = LinkRequirement(
            application,
            direction,
            center,
            bw,
            target,
            altitude,
            elevation,
            int(beams),
            antenna,
            sky,
            atmosphere,
            rain,
            scintillation,
            overhead,
            fill,
            feed,
            req.bf_error_db,
            coherent,
            receiver_nf,
            if_freq,
            req.lo_routing_loss_db,
            tx_input,
            backoff,
            req.nonlinear_snr_db,
        )
        band_text = f" · ESA 기준 {selected_band[0]:g}~{selected_band[1]:g} GHz" if selected_band else ""
        st.success(f"필요 대역 {st.session_state.requirement.required_low_ghz:.4f}~{st.session_state.requirement.required_high_ghz:.4f} GHz로 저장했습니다.{band_text}")


def page_compatible(repo: ComponentRepository):
    st.header("Compatible Components")
    req = st.session_state.get("requirement", default_requirement())
    rows,detail = [],{}
    for item in repo.list():
        checks = check_component(item, req)
        status = overall_status(checks)
        rows.append({
            "ID": item.component_id,
            "Stage": item.category,
            "Part No.": item.part_no,
            "Grade": item.grade,
            "Application": checks[0].status.value,
            "Frequency": next((x.status.value for x in checks if x.rule == "frequency"), "-"),
            "Overall": status.value,
        })
        detail[item.component_id] = checks
    st.caption(f"{req.application} {req.direction} · {req.required_low_ghz:.4f}~{req.required_high_ghz:.4f} GHz · 요구 기능 {required_function(req)}")
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    if rows:
        selected = st.selectbox("판정 상세", [row["ID"] for row in rows], format_func=lambda value: next(row["Part No."] for row in rows if row["ID"] == value))
        for check in detail[selected]:
            st.write(f"{STATUS_ICON[check.status]} **{check.rule}** — {check.message}"+(" · estimated" if check.estimated else ""))


def show_link(result):
    cols = st.columns(4)
    cols[0].metric("SNR", f"{result.snr_total_db:.2f} dB")
    cols[1].metric("MCS", str(result.mcs.index) if result.mcs else "N/A")
    cols[2].metric("Modulation", result.mcs.modulation if result.mcs else "N/A")
    cols[3].metric("Throughput", f"{result.throughput_mbps:.2f} Mbps", f"{result.throughput_margin_mbps:+.2f}")
    st.write(f"**{result.result.value}** · Slant range {result.slant_range_km:.2f} km · FSPL {result.fspl_db:.2f} dB · G/T {result.gt_db_per_k:.2f} dB/K · System T {result.system_noise_temperature_k:.2f} K")


def page_design(repo: ComponentRepository):
    st.header("Design Result")
    req = st.session_state.get("requirement", default_requirement())
    if required_function(req) == "Tx":
        candidates,reasons = generate_tx_candidates(req, repo.list(), repo.list_mcs())
        if reasons:
            st.warning("자동 chain을 만들 수 없습니다: "+" ".join(reasons))
        if candidates:
            best = candidates[0]
            st.subheader("Recommended Chain" if best.status == Status.PASS else "Best Available Chain")
            if best.status != Status.PASS:
                st.warning("현재 요구조건을 PASS하는 조합이 없어 가장 가까운 후보를 표시합니다. 아래 단계별 한계와 Link Margin을 확인하세요.")
            st.write(" → ".join(f"{item.category}: {item.part_no}" for item in best.components))
            st.metric("EIRP per beam", f"{best.eirp_dbw:.2f} dBW")
            show_link(best.link_budget)
            st.dataframe(pd.DataFrame([asdict(stage) for stage in best.power_chain.stages]), width="stretch", hide_index=True)
            st.subheader("후보 순위")
            ranking = pd.DataFrame([
                {
                    "Rank": index+1,
                    "Chain": " → ".join(x.part_no for x in item.components),
                    "Status": item.status.value,
                    "Grade": " / ".join(sorted({x.grade for x in item.components})),
                    "Link Margin (dB)": item.link_budget.link_margin_db,
                    "Throughput (Mbps)": item.link_budget.throughput_mbps,
                    "DC Power (W)": item.total_power_w,
                }
                for index,item in enumerate(candidates[:50])
            ])
            selection = st.dataframe(
                ranking,
                width="stretch",
                hide_index=True,
                key="candidate_ranking",
                on_select="rerun",
                selection_mode="single-row",
            )
            selected_rows  = selection.selection.rows
            selected_index = selected_rows[0] if selected_rows else 0
            st.caption("후보 행을 누르면 아래 구매 부품 상세가 바뀝니다.")
            show_purchase_list(candidates[selected_index])
            st.download_button("설계 결과 CSV 다운로드", ranking.to_csv(index=False).encode("utf-8-sig"), "design_candidates.csv", "text/csv")
    else:
        candidates,reasons = generate_rx_candidates(req, repo.list())
        if reasons:
            st.warning("자동 Rx chain을 만들 수 없습니다: "+" ".join(reasons))
        elif candidates:
            best = candidates[0]
            st.write(" → ".join(f"{item.category}: {item.part_no}" for item in best["components"]))
            st.metric("Receiver Total NF", f"{best['total_nf_db']:.2f} dB")
            st.metric("Receiver Total Gain", f"{best['total_gain_db']:.2f} dB")
            for check in best["checks"]:
                st.write(f"{STATUS_ICON[check.status]} **{check.rule}** — {check.message}")

    st.subheader("독립 Link Budget 계산")
    antenna_input = st.number_input("Antenna input power (dBm)", value=34.0)
    eirp          = calculate_eirp(antenna_input, req.antenna_gain_db, req.feed_loss_db, req.num_beams)
    result        = calculate_link_budget(req, eirp, repo.list_mcs())
    st.metric("Calculated EIRP per beam", f"{eirp:.2f} dBW")
    show_link(result)


def main():
    st.set_page_config(page_title="Ka-band RF Auto Designer", page_icon="📡", layout="wide")
    st.title("Ka-band RF 자동설계")
    page = st.sidebar.radio("화면", ["Component CSV","Requirement","Compatible Components","Design Result"])
    repo = repository()
    {"Component CSV": page_components, "Requirement": lambda _: requirement_form(), "Compatible Components": page_compatible, "Design Result": page_design}[page](repo)


if __name__ == "__main__":
    main()
