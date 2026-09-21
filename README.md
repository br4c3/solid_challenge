# Ka-band RF Component Pipeline

제조사 자료 수집부터 RF 체인 계산까지 제공하는 Ka-band 초기 설계 도구입니다. Flask application factory와 Blueprint를 사용하며 Vue 화면과 분리해 실행합니다.

## 구조

```text
frontend/          Vue 3 + Vite 화면
    ↓ /api
backend/wsgi.py    Gunicorn·로컬 실행 진입점
backend/app/       Flask application package
    models.py      dataclass 구조체
    design/        RF 검사·계산·후보 Blueprint
    catalog/       부품 조회·CSV·Excel·PDF Blueprint
    ↓
data/              부품 및 MCS CSV
```

- `data/catalog/manufacturer_product_seeds.csv`: 조사할 부품과 공식 제조사 URL
- `data/pdfs/`: 내려받은 Datasheet PDF
- `data/components.csv`: 추출 결과와 근거를 포함한 최종 부품 CSV
- `data/mcs.csv`: 링크 버짓 계산용 MCS CSV
- `backend/app/__init__.py`: Flask application factory
- `backend/app/catalog/routes.py`: 상태 및 부품 조회 Blueprint
- `backend/app/design/routes.py`: 호환성 검사, 체인 생성, 링크 버짓 Blueprint
- `backend/app/models.py`: `dataclass` 기반 요구조건·부품 사양·계산 결과 구조체
- `backend/app/design/`: RF 호환성, 출력, 잡음지수, 링크 버짓, 후보 생성
- `backend/app/catalog/`: CSV 저장소, Excel import, PDF·OCR 사양 추출
- `frontend/src/App.vue`: 요구조건 입력, 후보 결과, 부품 목록 화면

중간 DB, 후보 큐, 여러 단계의 processed CSV는 사용하지 않습니다. RF 스펙도 JSON이 아니라 `gain_db`, `noise_figure_db`, `output_p1db_dbm` 같은 CSV 열로 저장됩니다.

기본 부품에 더해, 전체 온라인 실행마다 공식 Qorvo 카탈로그와 Anokiwave SATCOM 전체 목록에서 목표 K/Ka 중심주파수를 지원하는 신규 제품을 찾습니다. 공식 자료로 확인된 Qorvo PA/Mixer, Analog Devices LNA/Mixer/PLL, TI PLL 후보 풀도 함께 seed에 추가합니다. 여기에 기준 엑셀의 BFIC를 병합해 하나의 `components.csv`로 만들며, 앱의 Tx/Rx chain 생성기가 별도 변환 없이 이 CSV를 바로 사용합니다.

ESA 대역은 Terminal Tx/Payload Rx `27.5~31 GHz`, Terminal Rx/Payload Tx `17.7~21.2 GHz`로 적용합니다. Payload 후보는 Space-grade를 우선 정렬하되 Commercial-grade도 비교 대상에 포함하며, 모든 부품은 `grade` 열에 등급을 명시합니다. 기준 엑셀에서 Payload로 기재된 ADAR3002는 병합할 때 Terminal Rx 부품으로 교정합니다.

## 설치

macOS에서는 OCR 엔진을 먼저 설치합니다.

```bash
brew install tesseract
source .venv/bin/activate
pip install -r backend/requirements.txt
```

텍스트가 포함된 일반 Datasheet는 `pypdf`로 빠르게 읽고, 스캔된 페이지만 Tesseract OCR을 사용합니다.

## 로컬 실행

터미널 두 개에서 백엔드와 프론트엔드를 각각 실행합니다. Vite 개발 서버는 `/api` 요청을 Flask로 전달합니다.

```bash
.venv/bin/python -m backend.wsgi
```

```bash
cd frontend
npm install
npm run dev
```

파이프라인과 로컬 서버 실행 조건은 `backend/config.json`에서 관리합니다.

```json
{
  "pipeline": {
    "offline": false,
    "limit": 0,
    "part_no": "",
    "workers": 4,
    "discover": true
  },
  "server": {
    "start_after_pipeline": false,
    "host": "127.0.0.1",
    "port": 5000,
    "debug": false
  }
}
```

설정을 저장한 뒤 별도 옵션 없이 실행합니다.

```bash
.venv/bin/python scripts/pipeline.py
```

PDF 탐색·다운로드·텍스트/OCR 추출은 `pipeline.workers` 수만큼 병렬 처리합니다. 메모리 사용량이 크거나 사이트 제한이 심하면 `workers`를 `1`로 설정합니다. `limit`는 처리할 최대 부품 수, `part_no`는 하나의 특정 부품, `discover`는 공식 카탈로그 신규 부품 탐색 여부를 지정합니다. `limit` 또는 `part_no`를 지정하면 기존 CSV를 유지하면서 해당 범위만 갱신합니다.

카탈로그에서 발견됐더라도 NDA 양식이나 비공개 Preview로 보호된 Datasheet는 우회하지 않습니다. 해당 부품은 주파수와 공식 제품 URL까지만 CSV에 남고, `note` 열에 공개 다운로드 불가 사유가 표시됩니다.

이미 받은 `data/pdfs/*.pdf`만 다시 분석하려면 `pipeline.offline`을 `true`로 설정합니다. 자료 수집 완료 후 Flask 서버도 실행하려면 `server.start_after_pipeline`을 `true`로 설정합니다.

결과는 `data/components.csv`에서 바로 확인할 수 있습니다. `extraction_method`는 `PDF_TEXT`, `OCR`, `PDF_TEXT+OCR` 중 하나이며, `extraction_evidence`에는 페이지와 원문 근거가 저장됩니다.

프론트엔드의 **Data Crawl** 탭에서도 파이프라인을 실행할 수 있습니다. **Start Crawl**을 누르면 제조사 탐색부터 CSV 갱신까지의 출력이 터미널 패널에 실시간으로 표시되며, 완료 후 부품 목록이 자동으로 갱신됩니다. 크롤링 작업은 한 번에 하나만 실행됩니다.

Analog Devices와 Texas Instruments는 공식 PDF 주소로 바로 다운로드합니다. Qorvo가 일반 HTTP 요청을 429로 차단하면 설치된 Google Chrome을 자동 제어해 공식 제품 페이지의 Datasheet를 내려받습니다.

## Firebase 배포

Flask API는 루트 `Dockerfile`로 Cloud Run에 배포하고, Vue 빌드 결과는 Firebase Hosting에 배포합니다. `firebase.json`의 `/api/**` rewrite가 두 서비스를 같은 도메인으로 연결합니다.

```bash
gcloud run deploy rf-design-api --source . --region asia-northeast3 --allow-unauthenticated
cd frontend && npm install && npm run build && cd ..
firebase deploy --only hosting
```

## 검증

```bash
.venv/bin/python -m pytest -q
```

Python 코드는 YAPF를 적용한 뒤 연속된 대입문의 `=`를 정렬합니다.

```bash
.venv/bin/python scripts/format_python.py
.venv/bin/python scripts/format_python.py --check
```
