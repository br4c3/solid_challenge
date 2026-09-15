#!/usr/bin/env python3
"""Crawl product pages, download datasheets, extract specs, and write CSV."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from rf_design.csv_repository import ComponentRepository
from rf_design.datasheet_parser import extract_fields_from_pages, extract_pdf_pages
from rf_design.importer import component_from_csv_row, import_mcs


SEED_CSV = ROOT / "data/catalog/manufacturer_product_seeds.csv"
PDF_DIR  = ROOT / "data/pdfs"

MANUFACTURER_DOMAINS = {
    "Qorvo": ("qorvo.com",),
    "Analog Devices": ("analog.com",),
    "Texas Instruments": ("ti.com",),
    "Renesas": ("renesas.com","axiro.com"),
}

DIRECT_DATASHEETS = {
    "HMC517-DIE": "https://www.analog.com/media/en/technical-documentation/data-sheets/hmc517chips.pdf",
    "HMC751": "https://www.analog.com/media/en/technical-documentation/data-sheets/hmc751.pdf",
    "ADRF5024": "https://www.analog.com/media/en/technical-documentation/data-sheets/adrf5024.pdf",
    "ADMV1013S": "https://www.analog.com/media/en/technical-documentation/data-sheets/admv1013s-csl.pdf",
    "ADMV1014": "https://www.analog.com/media/en/technical-documentation/data-sheets/admv1014.pdf",
    "HMC798A": "https://www.analog.com/media/en/technical-documentation/data-sheets/hmc798a.pdf",
    "AD9207": "https://www.analog.com/media/en/technical-documentation/data-sheets/ad9207.pdf",
    "AD9176": "https://www.analog.com/media/en/technical-documentation/data-sheets/ad9176.pdf",
}


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def safe_name(value: str) -> str: return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def allowed_url(manufacturer: str, url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith("."+domain) for domain in MANUFACTURER_DOMAINS.get(manufacturer, ()))


def get(session: requests.Session, manufacturer: str, url: str) -> requests.Response:
    if not allowed_url(manufacturer, url): raise ValueError(f"허용되지 않은 제조사 URL: {url}")
    response = session.get(url, timeout=30)
    if response.status_code == 429: raise RuntimeError("제조사 사이트가 자동 요청을 차단함 (HTTP 429)")
    response.raise_for_status()
    if not allowed_url(manufacturer, response.url): raise ValueError(f"제조사 도메인 밖으로 이동함: {response.url}")
    return response


def find_datasheet_url(manufacturer: str, page_url: str, html: bytes) -> str:
    soup       = BeautifulSoup(html, "html.parser")
    candidates = []
    for anchor in soup.select("a[href]"):
        url   = urljoin(page_url, anchor.get("href", ""))
        label = " ".join(anchor.get_text(" ", strip=True).lower().split())
        path  = urlparse(url).path.lower()
        if not allowed_url(manufacturer, url): continue
        score = 3 * int(path.endswith(".pdf"))+2 * int("datasheet" in label or "data sheet" in label)+int("/data-sheets/" in path or "/lit/ds/" in path)
        if score: candidates.append((score,url))
    return max(candidates, default=(0,""))[1]


def download_qorvo_pdf(product_url: str, pdf_path: Path) -> str:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page    = browser.new_page(accept_downloads=True)
        page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        link         = page.locator('a[href*="/products/r/"]').filter(has_text="Product Data Sheet").first
        document_url = urljoin(page.url, link.get_attribute("href") or "")
        if not document_url: raise RuntimeError("Qorvo Datasheet 링크를 찾지 못함")

        try:
            with page.expect_download(timeout=15000) as event:
                link.click()
            download = event.value
        except PlaywrightTimeoutError:
            proceed = page.get_by_text("PROCEED", exact=True).first
            if not proceed.is_visible(): raise RuntimeError("Qorvo Datasheet 다운로드가 시작되지 않음")
            with page.expect_download(timeout=30000) as event:
                proceed.click()
            download = event.value

        download.save_as(pdf_path)
        browser.close()
    if not pdf_path.read_bytes().startswith(b"%PDF"): raise RuntimeError("Qorvo 응답이 PDF가 아님")
    return document_url


def resolve_datasheet_url(row: dict) -> str:
    return row.get("datasheet_url", "").strip() or DIRECT_DATASHEETS.get(row.get("part_no", "").upper(), "")


def apply_extracted_fields(component, fields) -> None:
    for field in fields:
        if field.field == "freq_min_ghz" and component.freq_min_ghz is None: component.freq_min_ghz = field.value
        elif field.field == "freq_max_ghz" and component.freq_max_ghz is None: component.freq_max_ghz = field.value
        elif field.field not in {"freq_min_ghz","freq_max_ghz"} and component.specs.get(field.field) is None:
            component.specs[field.field] = field.value


def process_row(session: requests.Session, row: dict, offline: bool = False):
    component       = component_from_csv_row(row, "manufacturer_product_seeds.csv")
    manufacturer    = component.manufacturer
    product_url     = row.get("product_url", "").strip()
    datasheet_url   = resolve_datasheet_url(row)
    pdf_path        = PDF_DIR / f"{safe_name(component.part_no)}.pdf"
    component.product_url = product_url or None

    try:
        if pdf_path.exists():
            datasheet_url = datasheet_url or component.datasheet_url or ""
        elif offline:
            raise RuntimeError("캐시된 Datasheet PDF가 없음")
        elif manufacturer == "Qorvo":
            datasheet_url = download_qorvo_pdf(product_url, pdf_path)
        elif product_url and not datasheet_url:
            product        = get(session, manufacturer, product_url)
            datasheet_url  = find_datasheet_url(manufacturer, product.url, product.content)
        if not pdf_path.exists():
            if not datasheet_url: raise RuntimeError("제품 페이지에서 Datasheet PDF를 찾지 못함")
            pdf = get(session, manufacturer, datasheet_url)
            if "pdf" not in pdf.headers.get("Content-Type", "").lower() and not pdf.content.startswith(b"%PDF"):
                raise RuntimeError("Datasheet 응답이 PDF가 아님")
            PDF_DIR.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(pdf.content)
            datasheet_url = pdf.url

        content          = pdf_path.read_bytes()
        pages,method     = extract_pdf_pages(content)
        fields           = extract_fields_from_pages(pages, component.category)
        evidence         = [asdict(field) for field in fields]
        component.datasheet_url       = datasheet_url or component.datasheet_url
        component.datasheet_page      = ",".join(sorted({str(field.page) for field in fields})) or None
        component.source_file         = str(pdf_path.relative_to(ROOT))
        component.source_date         = datetime.now(timezone.utc).isoformat()
        component.extraction_method   = method
        component.extraction_evidence = json.dumps(evidence, ensure_ascii=False)
        component.note                = f"Datasheet에서 {len(fields)}개 필드 자동 추출; 검토 필요"
        apply_extracted_fields(component, fields)
    except Exception as exc:
        component.note = f"추출 실패: {type(exc).__name__}: {exc}"
    return component


def make_session() -> requests.Session:
    retry   = Retry(total=3, backoff_factor=1, status_forcelist=[500,502,503,504])
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 KaRFComponentPipeline/1.0"})
    session.mount("https://", adapter)
    return session


def run(offline: bool = False, limit: int = 0, part_no: str = "") -> ComponentRepository:
    rows = read_rows(SEED_CSV)
    if part_no: rows = [row for row in rows if row.get("part_no", "").lower() == part_no.lower()]
    if limit: rows = rows[:limit]
    if not rows: raise SystemExit(f"seed CSV에서 부품을 찾지 못함: {part_no}")
    session = make_session()

    components = []
    for index,row in enumerate(rows, start=1):
        component = process_row(session, row, offline)
        components.append(component)
        print(f"[{index}/{len(rows)}] {component.manufacturer} {component.part_no}: {component.extraction_method or component.note}")

    repository = ComponentRepository()
    repository.replace_components(components)
    link_book = next((ROOT / "references").glob("4-*.xlsx"), None)
    if link_book: import_mcs(link_book, repository)
    print(f"완료: {len(components)}개 부품 -> {repository.component_path}")
    return repository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="네트워크 대신 data/pdfs의 기존 PDF 사용")
    parser.add_argument("--limit", type=int, default=0, help="처리할 부품 수, 0이면 전체")
    parser.add_argument("--part-no", default="", help="지정한 Part No. 하나만 처리")
    parser.add_argument("--serve", action="store_true", help="완료 후 Streamlit 앱 실행")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()

    run(args.offline, args.limit, args.part_no)
    if not args.serve: return 0
    command = [
        sys.executable,"-m","streamlit","run",str(ROOT / "app.py"),
        "--server.address",args.host,"--server.port",str(args.port),
    ]
    os.execv(sys.executable, command)
    return 0


if __name__ == "__main__": raise SystemExit(main())
