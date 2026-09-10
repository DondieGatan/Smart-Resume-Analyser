# Smart Resume Analyser

An AI-assisted resume scoring, feedback, and job-matching platform. Upload a
resume as a PDF or a scanned image and get back a scored, section-by-section
breakdown — skills, education, experience, and formatting — plus an
ATS-compatibility check and concrete suggestions for improvement.

## Features

- **OCR + PDF text extraction** (PyMuPDF for native PDFs, Tesseract for
  scanned images) so both formats work through the same pipeline
- **NLP-driven skill extraction and section scoring** — NLTK tokenisation,
  stopword filtering, and tagging against a curated skills taxonomy
- **ATS-compatibility simulation** with a transparent, explainable scoring
  breakdown rather than a single opaque number
- **Job-description matching** — paste a job description and see how well a
  given resume fits it
- **Personalised feedback generation** based on career goal, experience
  level, and target role
- **Guided resume builder** with multiple templates
- **Auth system** with email-based password reset (Flask-Mail) and a
  per-user resume history — every resume, and the dashboard's aggregate
  stats, are scoped to the account that uploaded them
- **Analytics dashboard** — score distribution, top skills, career-field
  breakdown across your own analysed resumes, with CSV/JSON export for
  further analysis (e.g. Power BI)
- **Explainable scoring** — the result page highlights exactly where each
  detected skill appears in your resume text, not just a bare number
- **Account and resume deletion** — delete a single analysis or your entire
  account (and every file it owns) at any time

## Stack

Python · Flask · Postgres (`psycopg`) · NLTK · PyMuPDF · Tesseract OCR
(`pytesseract`) · Flask-Mail · HTML/CSS/JS

## Project layout

```
app.py              Flask routes (auth, upload, dashboard, builder, job match)
analyzer.py         Resume parsing, scoring, ATS simulation, feedback generation
models.py           Database access layer (resumes, skills, users, auth)
config.py           App configuration (DB, mail, upload limits) via env vars
templates/          Jinja2 templates
static/             CSS, JS, images
uploads/            Uploaded resume files (gitignored — not under static/,
                    since resumes contain PII and static/ has no auth check;
                    served through the authenticated /uploads/<filename> route)
setup_db.sql        Core schema (resumes, skills, education, experience)
setup_users_table.sql   Auth-related schema (users, password reset codes)
scripts/run_sql_file.py  Runs a .sql file via psycopg (used by CI to build a
                    fresh schema against the test database)
tests/              pytest suite (scoring logic, auth/password hashing)
.github/workflows/  CI — runs the test suite against a real Postgres
                    service container on every push/PR
```

## Run it

Requires Python 3, a Postgres database (a free [Neon](https://neon.tech)
project works well), and Tesseract OCR installed locally (used for
scanned-image resumes).

```bash
python -m venv venv
venv\Scripts\activate        # or source venv/bin/activate on macOS/Linux
pip install -r requirements.txt      # or requirements-dev.txt to also get pytest
```

Set up the database:

```bash
python scripts/run_sql_file.py setup_db.sql setup_users_table.sql
```

Copy `.env.example` to `.env` and fill in real values — at minimum a
`SECRET_KEY` for anything beyond local dev (the app generates and persists
a random one locally if you skip this, purely for convenience) and
`DATABASE_URL` (your Postgres connection string). `DB_SCHEMA` lets one
Postgres database host separate schemas per environment — defaults to
`resume_analyser_dev`. (`MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD`,
`MAIL_DEFAULT_SENDER` for password-reset emails.)

```bash
python app.py
```

On first run the app automatically adds any missing schema pieces (e.g. the
`resumes.user_id` column used for per-account data isolation) — no manual
migration step needed beyond the two `.sql` files above.

### Tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

`tests/test_analyzer.py` is pure unit tests (no DB needed). `tests/test_auth.py`
is an integration suite against a real database — it needs the same DB setup
as running the app itself. CI (`.github/workflows/tests.yml`) runs both
against a disposable Postgres container on every push/PR.

## Routes

| Path | Description |
|---|---|
| `/register`, `/login`, `/logout` | Account creation and session auth |
| `/forgot-password`, `/verify-code`, `/reset-password` | Email-based password reset |
| `/` | Upload a resume |
| `/result/<id>` | Scored breakdown for a given resume |
| `/personalize/<id>` | Personalised feedback for a given resume |
| `/job-match/<id>` | Match a resume against a pasted job description |
| `/builder`, `/builder/<template>` | Guided resume builder |
| `/history` | A user's past resume analyses |
| `/dashboard`, `/api/dashboard-data` | Analytics dashboard |
| `/export/csv` | CSV export of dashboard data |
| `/uploads/<filename>` | Serves an uploaded resume file — only to its owner |
| `/resume/<id>/delete` (POST) | Permanently delete one resume and its file |
| `/account/delete` (POST) | Permanently delete the account and everything it owns |

## Scaling this further

At this project's current scale (a personal or small-team tool, single Flask
process, local disk storage), the setup above is appropriate. The two things
that would need to change before this could handle real production traffic:

- **Background job processing.** Resume parsing (`analyse_resume()`) runs
  synchronously inside the `/upload` request today, which will start timing
  out or queueing badly under concurrent load. The standard fix is a task
  queue (Celery or RQ with Redis) — upload the file, enqueue the analysis
  job, redirect to a "processing…" page that polls for completion.
- **Object storage instead of local disk.** `uploads/` works for a single
  server with persistent disk, but most PaaS hosts (Render, Heroku, etc.)
  have ephemeral filesystems — uploaded files would vanish on redeploy.
  Swapping `UPLOAD_FOLDER`'s file I/O for an S3-compatible bucket is a
  contained change (it's isolated to `app.py`'s upload/serve/delete routes).

Neither is implemented here since both need infrastructure (a Redis
instance, a cloud storage bucket) that has to be provisioned and paid for
separately — adding the code without that backing infrastructure running
would just be unused plumbing.
