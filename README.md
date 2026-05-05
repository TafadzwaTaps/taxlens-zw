# TaxLens Zimbabwe 🇿🇼

Free, independent PAYE transparency tool for Zimbabwean employees.

Enter your salary manually **or** upload a payslip to estimate expected PAYE,
compare it to your actual deductions, and flag possible discrepancies — all privately, with no account required.

> ⚠️ **Disclaimer:** Estimates only. Not affiliated with or endorsed by ZIMRA.

---

## Project Structure

```
taxlens-zw/
│
├── backend/                    ← FastAPI Python app
│   ├── main.py                 All routes (pages + API)
│   ├── config.py               Settings loaded from .env
│   ├── database.py             Supabase client initialisation
│   ├── schemas.py              Pydantic request/response models
│   ├── tax_service.py          PAYE progressive band engine
│   ├── ocr_service.py          Tesseract OCR + payslip analysis
│   ├── test_tax_service.py     Unit tests
│   ├── requirements.txt        Python dependencies (no SQLAlchemy)
│   ├── build.sh                Render build script
│   ├── render.yaml             Render deployment config
│   ├── .env.example            Environment variable template
│   └── .gitignore
│
├── frontend/                   ← HTML templates + static assets
│   ├── templates/
│   │   ├── base.html           Shared layout, navbar, footer
│   │   ├── index.html          Home page
│   │   ├── calculator.html     Manual PAYE calculator
│   │   └── analyzer.html       Payslip upload and analysis
│   └── static/
│       └── style.css           All custom CSS (loaded after Bootstrap)
│
├── supabase_schema.sql         Run once in Supabase SQL Editor
└── README.md                   This file
```

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.115, Python 3.12 |
| Database | Supabase (PostgreSQL) via `supabase-py` 2.10 |
| Frontend | Jinja2 templates + Bootstrap 5 (no React, no Tailwind) |
| OCR | Tesseract 5 via `pytesseract` |
| Hosting | Render.com |

**No SQLAlchemy. No ORM. No Docker.**

---

## Privacy Design

| What | Stored? |
|---|---|
| Salary you type | ❌ Never stored |
| Payslip file | ❌ Processed in memory, immediately discarded |
| Your name / email | ❌ Never collected |
| Anonymised tax numbers | ✅ Only if you provide a session token |
| Session token | ✅ Stored as a hash key — you can delete by it |

---

# ── PART 1: DATABASE (Supabase) ────────────────────────────────────────────────

## Step 1 — Create a Supabase project

1. Go to [supabase.com](https://supabase.com) → **New project**
2. Name it `taxlens-zw`, set a strong DB password, choose a region:
   - Closest to Zimbabwe: **ap-southeast-1 (Singapore)** or **eu-west-2 (London)**
3. Wait ~90 seconds for provisioning

## Step 2 — Run the schema SQL

1. In Supabase dashboard → left sidebar → **SQL Editor** → **New query**
2. Paste the entire contents of `supabase_schema.sql`
3. Click **Run ▶**
4. You should see `Success. No rows returned`
5. The verification `SELECT` at the bottom of the file will print the 10 expected columns

## Step 3 — Copy your API credentials

Go to **Project Settings → API** and note:

| Value | Where to find it |
|---|---|
| **Project URL** | Settings → API → Project URL |
| **Service role key** | Settings → API → `service_role` (click reveal) |

> Use the **service role key** (not the anon key) for the backend — it bypasses RLS.

---

# ── PART 2: LOCAL DEVELOPMENT ──────────────────────────────────────────────────

## Step 4 — Install Tesseract

```bash
# Ubuntu / Debian / WSL
sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-eng

# macOS
brew install tesseract

# Windows
# Download installer: https://github.com/UB-Mannheim/tesseract/wiki
# Then set TESSERACT_CMD in backend/.env (see Step 5)
```

Verify:
```bash
tesseract --version
# tesseract 5.x.x
```

## Step 5 — Python environment

```bash
# Clone the repo
git clone https://github.com/YOUR-USERNAME/taxlens-zw.git
cd taxlens-zw/backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Step 6 — Configure environment

```bash
cp .env.example .env
```

Edit `backend/.env`:

```env
SUPABASE_URL=https://rzeaagwdaqqgnodtwyco.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGci...your-service-role-key...

APP_ENV=development
PORT=8000

# Windows only — uncomment and set path to tesseract.exe:
# TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

## Step 7 — Run the app

```bash
# Run from the backend/ folder
cd backend
uvicorn main:app --reload --port 8000
```

Expected output:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Open: **http://localhost:8000**

---

# ── PART 3: TESTING ────────────────────────────────────────────────────────────

## Step 8 — Run unit tests

```bash
# From backend/ folder (venv active)
pytest test_tax_service.py -v
```

Expected (all 14 pass):
```
PASSED test_tax_service.py::TestPayeCalculation::test_zero_tax_band
PASSED test_tax_service.py::TestPayeCalculation::test_second_band_only
PASSED test_tax_service.py::TestPayeCalculation::test_spans_two_bands
PASSED test_tax_service.py::TestPayeCalculation::test_top_band
PASSED test_tax_service.py::TestPayeCalculation::test_aids_levy_always_3_pct
PASSED test_tax_service.py::TestPayeCalculation::test_net_equals_gross_minus_total
PASSED test_tax_service.py::TestPayeCalculation::test_total_equals_paye_plus_levy
PASSED test_tax_service.py::TestPayeCalculation::test_zig_currency
PASSED test_tax_service.py::TestPayeCalculation::test_effective_rate_range
PASSED test_tax_service.py::test_known_values[300-0]
PASSED test_tax_service.py::test_known_values[500-40]
PASSED test_tax_service.py::test_known_values[700-80]
PASSED test_tax_service.py::test_known_values[1000-155]
PASSED test_tax_service.py::test_known_values[1500-280]
14 passed
```

## Step 9 — Test the PAYE Calculator (browser)

1. Open http://localhost:8000/calculator
2. Enter `1500`, currency `USD`
3. Click **Calculate PAYE**

Expected result:

| Field | Value |
|---|---|
| PAYE Tax | $280.00 |
| AIDS Levy | $8.40 |
| Total Deductions | $288.40 |
| Net Monthly Pay | $1,211.60 |
| Effective Rate | 19.23% |

## Step 10 — Test the privacy token + scrub flow

1. On the calculator page, click **Generate** next to Privacy Token
2. Note the token shown (e.g. `a1b2c3...`)
3. Enter a salary and click **Calculate PAYE**
4. The **Your Session Token** box appears in the results
5. Scroll down to **Delete My Data**, paste the token, click **Delete**
6. Expected: `1 record(s) permanently deleted. Your data is gone.`
7. Verify in Supabase: **Table Editor → analyses** — the row should be gone

## Step 11 — Test the API directly with curl

```bash
# Calculate PAYE
curl -X POST http://localhost:8000/api/calculate-tax \
  -H "Content-Type: application/json" \
  -d '{"salary": 1500, "currency": "USD"}'

# With a session token (saves to Supabase)
curl -X POST http://localhost:8000/api/calculate-tax \
  -H "Content-Type: application/json" \
  -d '{"salary": 2000, "currency": "USD", "session_token": "testtoken123"}'

# Delete that record
curl -X DELETE http://localhost:8000/api/scrub \
  -H "Content-Type: application/json" \
  -d '{"session_token": "testtoken123"}'
# Expected: {"deleted_count":1,"message":"1 record(s) permanently deleted..."}

# Test payslip upload (using any clear payslip image)
curl -X POST http://localhost:8000/api/analyze-payslip \
  -F "file=@/path/to/payslip.jpg" \
  -F "session_token=mytoken456"
```

## Step 12 — Test the Payslip Analyzer (browser)

1. Open http://localhost:8000/analyzer
2. Upload a clear payslip image (JPG or PDF)
3. Optionally click **Generate** for a privacy token
4. Click **Analyze Payslip**
5. Results show extracted values vs our estimate, with a flag badge

---

# ── PART 4: DEPLOY TO RENDER.COM ───────────────────────────────────────────────

## Step 13 — Push to GitHub

```bash
# From the project root (taxlens-zw/)
git init
git add .
git commit -m "TaxLens Zimbabwe MVP"

# Create repo on github.com, then:
git remote add origin https://github.com/YOUR-USERNAME/taxlens-zw.git
git push -u origin main
```

## Step 14 — Create a Render Web Service

1. Go to [render.com](https://render.com) → **New → Web Service**
2. Connect your GitHub account and select `taxlens-zw`
3. Render detects `backend/render.yaml` automatically

If configuring manually, use these settings:

| Setting | Value |
|---|---|
| **Root Directory** | `backend` |
| **Runtime** | Python 3 |
| **Build Command** | `bash build.sh` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Plan** | Free (spins down after inactivity) or Starter $7/mo (always-on) |

## Step 15 — Set environment variables in Render

Go to your service → **Environment** tab → add:

| Key | Value | Secret? |
|---|---|---|
| `SUPABASE_URL` | `https://rzeaagwdaqqgnodtwyco.supabase.co` | No |
| `SUPABASE_SERVICE_KEY` | `eyJhbGci...your-key` | **Yes** (mark as secret) |
| `APP_ENV` | `production` | No |

Click **Save Changes** — Render triggers a redeploy automatically.

## Step 16 — Watch the build log

```
━━━ Installing Tesseract OCR ━━━
...
━━━ Installing Python packages ━━━
...
━━━ Build complete ✓ ━━━
INFO:     Application startup complete.
```

Your app is live at `https://taxlens-zw-xxxx.onrender.com`

## Step 17 — Verify the live deployment

Repeat Steps 9–12 using your Render URL instead of `localhost:8000`.

---

# ── PART 5: MAINTAINING TAX BANDS ──────────────────────────────────────────────

When ZIMRA updates PAYE tables, edit `backend/tax_service.py`:

```python
USD_BANDS = [
    (300.00,   0.00,  "0% — Up to $300"),
    (700.00,   0.20,  "20% — $301 to $700"),
    # ... update here
]
```

Push to GitHub → Render auto-deploys within ~2 minutes.

---

## Known Tax Bands (USD Monthly — Illustrative)

| Income Range | Marginal Rate |
|---|---|
| Up to $300 | 0% |
| $301 – $700 | 20% |
| $701 – $1,500 | 25% |
| $1,501 – $3,000 | 30% |
| Above $3,000 | 35% |

AIDS Levy = 3% of PAYE (all bands)

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Home page |
| `GET` | `/calculator` | PAYE calculator UI |
| `GET` | `/analyzer` | Payslip analyzer UI |
| `GET` | `/docs` | Swagger API docs |
| `POST` | `/api/calculate-tax` | JSON PAYE calculation |
| `POST` | `/api/analyze-payslip` | Multipart payslip upload |
| `DELETE` | `/api/scrub` | Delete data by session token |

---

## Discrepancy Flags

| Flag | Meaning | Recommended Action |
|---|---|---|
| ✅ OK | Difference ≤ $5 | Deductions look correct |
| 🔴 Possible over-deduction | Payslip PAYE > estimate by >$5 | Confirm with payroll — may be benefits, arrears, etc. |
| 🟡 Possible under-deduction | Payslip PAYE < estimate by >$5 | Check for credits or different gross figure |

> A flag is **not an accusation**. Many legitimate reasons cause discrepancies.
