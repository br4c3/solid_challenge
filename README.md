# Ka-band RF Designer

Ka-band RF component collection, RF chain calculation, and link-budget analysis in a local Electron desktop application. The Vue interface runs in Electron, while a bundled Python/Flask process performs calculations, PDF extraction, OCR, and manufacturer catalog crawling.

## Architecture

```text
Electron main process
├── starts and stops the local Python backend
├── selects an available localhost port
└── opens the Vue renderer
        ↓ /api on 127.0.0.1
Flask backend
├── RF compatibility and chain calculations
├── link-budget calculations
├── component CSV repository
└── datasheet download, PDF parsing, and OCR
```

The packaged application stores writable data under Electron's per-user application data directory. Seed data and reference workbooks are copied from the application resources on first launch. Development mode continues to use the repository's `data/` directory.

## Design workflow

- The desktop wizard walks through design type, requirements, formula profile, preferences, component stages, review, and results.
- Required design inputs use a pale yellow background and native range validation.
- Preferred manufacturers and parts are managed from the **Components** view and persist on the local PC.
- Each RF stage can use automatic selection or a pinned part. Incompatible parts are identified before calculation and cannot be selected.
- Candidate and RF-stage controls provide sequential inspection of each result.
- **Formula Profiles** can clone the built-in model, edit formulas and ranking rules, validate changes, and save immutable revisions. Results retain the selected profile revision and expose a calculation trace with actual inputs.
- Up to five candidates can be compared and exported as a UTF-8 CSV file through the Electron save dialog.
- The in-app Help Center is available from the activity bar or with **F1** and includes searchable workflow guidance, an RF glossary, and troubleshooting tips.

Formula expressions use a restricted mathematical language rather than Python execution. Each formula slot has fixed input and output units shown in the editor. Profiles can be imported and exported as JSON; the built-in profile remains read-only.

## Repository layout

```text
frontend/
  electron/          Electron main and preload processes
  src/               Vue 3 renderer
backend/
  desktop.py         desktop backend entry point
  app/               Flask API and RF logic
scripts/
  pipeline.py        component collection pipeline
data/                development data and catalog seed
references/          reference workbooks
```

## Development setup

Install Tesseract on macOS, create the Python environment, and install both dependency sets.

```bash
brew install tesseract
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
playwright install chromium
cd frontend
npm install
```

The desktop package still expects Tesseract to be installed for scanned-document OCR and Google Chrome to be installed for Qorvo downloads that require browser automation.

Run the desktop application from `frontend/`. This command starts Vite, Electron, and the local Flask backend together.

```bash
cd frontend
npm run dev
```

Set `RF_DESIGN_PYTHON` when development mode should use a Python executable other than `.venv/bin/python`.

## Component pipeline

Pipeline behavior is configured in `backend/config.json`.

```json
{
  "pipeline": {
    "offline": false,
    "limit": 0,
    "part_no": "",
    "workers": 4,
    "discover": true
  }
}
```

The **Data Crawl** view runs the same pipeline and displays its output. It downloads public manufacturer datasheets, extracts text with `pypdf`, and uses Tesseract for scanned pages. Protected or NDA-only documents are not bypassed.

The pipeline can also be run directly during development.

```bash
.venv/bin/python scripts/pipeline.py
```

## Desktop packaging

PyInstaller first bundles the Python backend. Electron Builder then packages that executable, the Vue build, catalog seed, configuration, and reference workbooks.

```bash
cd frontend
npm run desktop:dir
```

Use `npm run desktop:pack` to create the platform installer under `frontend/release/`. Packaging must be run separately on each target operating system. Public distribution additionally requires the appropriate macOS or Windows code-signing credentials.

## Validation

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/format_python.py
.venv/bin/python scripts/format_python.py --check
cd frontend && npm test && npm run build
```

Python formatting follows the repository's YAPF-based formatter, including aligned consecutive assignments.
