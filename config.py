import os
import secrets
import warnings
from dotenv import load_dotenv

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_APP_DIR, '.env'))


def _load_or_create_dev_secret_key():
    """Fallback used only when SECRET_KEY isn't set in the environment.
    Persists a random key to a gitignored local file so it survives the
    Flask debug reloader restarting the process on every code change —
    without this, every save would silently log everyone out."""
    key_path = os.path.join(_APP_DIR, '.flask_secret_key')
    if os.path.exists(key_path):
        with open(key_path, 'r') as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(key_path, 'w') as f:
        f.write(key)
    return key


_env_secret_key = os.environ.get('SECRET_KEY')
if not _env_secret_key:
    warnings.warn(
        'SECRET_KEY is not set in the environment — using a locally generated '
        'dev key (.flask_secret_key, gitignored). Set SECRET_KEY in your .env '
        'for a real deployment (see .env.example).',
        RuntimeWarning
    )

class Config:
    SECRET_KEY = _env_secret_key or _load_or_create_dev_secret_key()

    # Postgres (Neon, free tier) — the app's sole database since the Azure
    # SQL server it originally ran on was decommissioned. DATABASE_URL is
    # required; there is no more MSSQL/pyodbc fallback (see models.py).
    # DB_SCHEMA lets one Neon project host separate schemas per environment
    # (e.g. "resume_analyser" in production, "resume_analyser_dev" locally)
    # without needing separate free databases.
    DATABASE_URL = os.environ.get('DATABASE_URL', '')
    DB_SCHEMA = os.environ.get('DB_SCHEMA', 'resume_analyser')

    # Upload Configuration
    # Deliberately NOT under static/ — resumes contain PII (names, emails,
    # phone numbers) and static/ is served with no auth check. Uploaded
    # files are served through the authenticated /uploads/<filename> route
    # in app.py instead, which checks the requester owns the resume.
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'png', 'jpg', 'jpeg', 'bmp', 'tiff', 'tif', 'webp'}

    # Email Configuration (for password reset)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', '')

    # SendGrid (HTTP-based transactional email) — preferred over Resend when
    # set. Resend's free tier can only deliver to the email address the
    # Resend account itself was signed up with until a full domain is
    # verified; SendGrid's free tier only needs one sender EMAIL verified
    # (no domain/DNS) and can then deliver to any recipient.
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '')
    SENDGRID_FROM = os.environ.get('SENDGRID_FROM', '')

    # Resend (HTTP-based transactional email) — used instead of SMTP when
    # set, since some hosts (e.g. Render's free tier) block outbound SMTP
    # ports entirely but always allow outbound HTTPS.
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
    RESEND_FROM = os.environ.get('RESEND_FROM', 'onboarding@resend.dev')

    # AI Assistant (Resume Builder chat) — Google Gemini API (free tier, no
    # billing required). Without a key set, the chat panel in the builder
    # just shows a friendly "not configured" message instead of erroring.
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')

    # Password reset token expiry (seconds)
    RESET_TOKEN_EXPIRY = 3600  # 1 hour

    # Session cookie hardening. SAMESITE=Lax blocks the session cookie from
    # being sent on cross-site POST requests (e.g. a malicious page
    # auto-submitting a form to /account/delete while the victim is logged
    # in elsewhere) — classic CSRF via cookie riding, since this app has no
    # separate CSRF token. SECURE is tied to Render's own env var (Render
    # sets RENDER=true on every service) rather than hardcoded True, so it
    # doesn't break local dev, which runs over plain http://localhost.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = bool(os.environ.get('RENDER'))
