# Ka-band RF Component Pipeline

제조사 제품 페이지를 크롤링하고 Datasheet PDF를 내려받아 텍스트/OCR로 사양을 추출한 뒤, 앱이 직접 사용하는 CSV에 저장합니다.

## 구조

```text
data/catalog/manufacturer_product_seeds.csv
references/3-Ka-band_RF_Chip_*.xlsx (BFIC 기준값)
        ↓
scripts/pipeline.py
  공식 카탈로그 신규 부품 발견 → PDF 다운로드 → 텍스트/OCR → 필드 추출 → BFIC 병합
        ↓
data/components.csv
        ↓
app.py
```

- `data/catalog/manufacturer_product_seeds.csv`: 조사할 부품과 공식 제조사 URL
- `data/pdfs/`: 내려받은 Datasheet PDF
- `data/components.csv`: 추출 결과와 근거를 포함한 최종 부품 CSV
- `data/mcs.csv`: 링크 버짓 계산용 MCS CSV
- `rf_design/spec_extractor.py`: RF 필드 추출 규칙
- `rf_design/datasheet_parser.py`: PDF 텍스트 추출과 OCR fallback

중간 DB, 후보 큐, 여러 단계의 processed CSV는 사용하지 않습니다. RF 스펙도 JSON이 아니라 `gain_db`, `noise_figure_db`, `output_p1db_dbm` 같은 CSV 열로 저장됩니다.

기본 부품에 더해, 전체 온라인 실행마다 공식 Qorvo 카탈로그와 Anokiwave SATCOM 전체 목록에서 목표 K/Ka 중심주파수를 지원하는 신규 제품을 찾습니다. 공식 자료로 확인된 Qorvo PA/Mixer, Analog Devices LNA/Mixer/PLL, TI PLL 후보 풀도 함께 seed에 추가합니다. 여기에 기준 엑셀의 BFIC를 병합해 하나의 `components.csv`로 만들며, 앱의 Tx/Rx chain 생성기가 별도 변환 없이 이 CSV를 바로 사용합니다.

## 설치

macOS에서는 OCR 엔진을 먼저 설치합니다.

```bash
brew install tesseract
source .venv/bin/activate
pip install -r requirements.txt
```

텍스트가 포함된 일반 Datasheet는 `pypdf`로 빠르게 읽고, 스캔된 페이지만 Tesseract OCR을 사용합니다.

## 실행

전체 파이프라인을 실행하고 앱까지 엽니다.

```bash
.venv/bin/python scripts/pipeline.py --serve
```

CSV 생성까지만 실행하려면 다음 명령을 사용합니다.

```bash
.venv/bin/python scripts/pipeline.py
```

테스트 목적으로 처음 몇 개만 처리할 수 있습니다.

```bash
.venv/bin/python scripts/pipeline.py --limit 2
```

특정 부품만 처리할 수도 있습니다.

```bash
.venv/bin/python scripts/pipeline.py --part-no LMX2624-SP
```

`--limit`와 `--part-no`는 기존 CSV를 지우지 않고 해당 부품만 갱신합니다. 옵션 없이 전체 실행할 때만 자동수집 목록을 새로 구성합니다.

공식 카탈로그 신규 부품 탐색만 생략하려면 `--skip-discovery`를 붙입니다. `--offline`, `--limit`, `--part-no` 실행에서는 탐색이 자동으로 생략됩니다.

카탈로그에서 발견됐더라도 NDA 양식이나 비공개 Preview로 보호된 Datasheet는 우회하지 않습니다. 해당 부품은 주파수와 공식 제품 URL까지만 CSV에 남고, `note` 열에 공개 다운로드 불가 사유가 표시됩니다.

이미 받은 `data/pdfs/*.pdf`만 다시 분석하려면 네트워크 없이 실행합니다.

```bash
.venv/bin/python scripts/pipeline.py --offline
```

결과는 `data/components.csv`에서 바로 확인할 수 있습니다. `extraction_method`는 `PDF_TEXT`, `OCR`, `PDF_TEXT+OCR` 중 하나이며, `extraction_evidence`에는 페이지와 원문 근거가 저장됩니다.

Analog Devices와 Texas Instruments는 공식 PDF 주소로 바로 다운로드합니다. Qorvo가 일반 HTTP 요청을 429로 차단하면 설치된 Google Chrome을 자동 제어해 공식 제품 페이지의 Datasheet를 내려받습니다.

## 검증

```bash
.venv/bin/python -m pytest -q
```
