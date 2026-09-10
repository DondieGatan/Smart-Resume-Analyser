import psycopg
import hashlib
import secrets
import random
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config


def get_db_connection():
    """Create and return a Postgres (Neon) database connection, scoped to
    Config.DB_SCHEMA via search_path so every unqualified table name in
    this file resolves to that schema without needing per-query prefixes."""
    dsn = Config.DATABASE_URL
    if dsn.startswith('postgres://'):
        dsn = dsn.replace('postgres://', 'postgresql://', 1)
    connection = psycopg.connect(dsn, options=f"-c search_path={Config.DB_SCHEMA}")
    return connection


def ensure_schema_migrations():
    """Idempotent schema migrations, safe to run on every startup.

    Adds resumes.user_id (the app originally had no per-user data isolation
    — every logged-in user could see every other user's resumes via History,
    Dashboard, and /result/<id>) and backfills existing ownerless resumes to
    whichever registered account shares their stored email, where one
    exists. Resumes with no matching account stay ownerless and become
    invisible to everyone, which is the safe default for leftover test data.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS user_id INT NULL")
    conn.commit()

    cursor.execute("""
        UPDATE resumes r SET user_id = u.id
        FROM users u
        WHERE u.email = r.email AND r.user_id IS NULL AND r.email IS NOT NULL
    """)
    conn.commit()

    cursor.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified INTEGER NOT NULL DEFAULT 0
    """)
    conn.commit()
    # Email verification is no longer a feature at all — login() doesn't
    # gate on this column anymore — but accounts registered while it still
    # was (before that change shipped) can be stuck with email_verified=0
    # forever, since nothing ever flips it back. Idempotent: matches zero
    # rows, and is a no-op, once every account has already been backfilled.
    cursor.execute("UPDATE users SET email_verified = 1 WHERE email_verified = 0")
    conn.commit()

    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_code VARCHAR(10) NULL")
    conn.commit()
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_code_expiry TIMESTAMP NULL")
    conn.commit()

    cursor.execute("DROP VIEW IF EXISTS resume_dashboard")
    conn.commit()
    cursor.execute("""
        CREATE VIEW resume_dashboard AS
        SELECT
            r.id,
            r.user_id,
            r.candidate_name,
            r.email,
            r.upload_date,
            ar.overall_score,
            ar.skills_score,
            ar.education_score,
            ar.experience_score,
            ar.formatting_score,
            ar.recommended_field,
            (SELECT COUNT(*) FROM skills s WHERE s.resume_id = r.id) AS total_skills
        FROM resumes r
        LEFT JOIN analysis_results ar ON ar.resume_id = r.id
    """)
    conn.commit()

    cursor.close()
    conn.close()


def save_resume(candidate_name, email, phone, filename, raw_text, user_id):
    """Save resume metadata and return the inserted ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO resumes (candidate_name, email, phone, filename, raw_text, user_id) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (candidate_name, email, phone, filename, raw_text, user_id)
    )
    resume_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return resume_id


def save_skills(resume_id, skills):
    """Save extracted skills for a resume."""
    conn = get_db_connection()
    cursor = conn.cursor()
    for skill_name, category in skills:
        cursor.execute(
            "INSERT INTO skills (resume_id, skill_name, category) VALUES (%s, %s, %s)",
            (resume_id, skill_name, category)
        )
    conn.commit()
    cursor.close()
    conn.close()


def save_education(resume_id, education_list):
    """Save education details for a resume."""
    conn = get_db_connection()
    cursor = conn.cursor()
    for entry in education_list:
        degree = entry.get('degree', '') if isinstance(entry, dict) else entry[0]
        institution = entry.get('institution', '') if isinstance(entry, dict) else entry[1]
        cursor.execute(
            "INSERT INTO education (resume_id, degree, institution) VALUES (%s, %s, %s)",
            (resume_id, degree, institution)
        )
    conn.commit()
    cursor.close()
    conn.close()


def save_experience(resume_id, experience_list):
    """Save work experience for a resume."""
    conn = get_db_connection()
    cursor = conn.cursor()
    for title, company, description in experience_list:
        cursor.execute(
            "INSERT INTO experience (resume_id, title, company, description) VALUES (%s, %s, %s, %s)",
            (resume_id, title, company, description)
        )
    conn.commit()
    cursor.close()
    conn.close()


def save_analysis_results(resume_id, overall_score, skills_score, education_score,
                          experience_score, formatting_score, recommended_field, recommendations):
    """Save the analysis results for a resume."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO analysis_results "
        "(resume_id, overall_score, skills_score, education_score, experience_score, "
        "formatting_score, recommended_field, recommendations) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (resume_id, overall_score, skills_score, education_score,
         experience_score, formatting_score, recommended_field, recommendations)
    )
    conn.commit()
    cursor.close()
    conn.close()


def _row_to_dict(cursor, row):
    """Convert a psycopg row (tuple) to a dictionary."""
    if row is None:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def _rows_to_dicts(cursor, rows):
    """Convert multiple psycopg rows to a list of dictionaries."""
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def get_resume_by_id(resume_id, user_id):
    """Retrieve a resume and its analysis results by ID, scoped to the
    requesting user — returns None if the resume doesn't exist OR belongs
    to someone else, so callers can't tell the two cases apart."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM resumes WHERE id = %s AND user_id = %s", (resume_id, user_id))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        return None
    resume = _row_to_dict(cursor, row)

    cursor.execute("SELECT * FROM skills WHERE resume_id = %s", (resume_id,))
    resume['skills'] = _rows_to_dicts(cursor, cursor.fetchall())

    cursor.execute("SELECT * FROM education WHERE resume_id = %s", (resume_id,))
    resume['education'] = _rows_to_dicts(cursor, cursor.fetchall())

    cursor.execute("SELECT * FROM experience WHERE resume_id = %s", (resume_id,))
    resume['experience'] = _rows_to_dicts(cursor, cursor.fetchall())

    cursor.execute("SELECT * FROM analysis_results WHERE resume_id = %s", (resume_id,))
    resume['analysis'] = _row_to_dict(cursor, cursor.fetchone())

    cursor.close()
    conn.close()
    return resume


def get_all_resumes(user_id):
    """Retrieve the requesting user's own resumes with their scores."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, r.candidate_name, r.email, r.upload_date,
               ar.overall_score, ar.recommended_field
        FROM resumes r
        LEFT JOIN analysis_results ar ON ar.resume_id = r.id
        WHERE r.user_id = %s
        ORDER BY r.upload_date DESC
    """, (user_id,))
    resumes = _rows_to_dicts(cursor, cursor.fetchall())
    cursor.close()
    conn.close()
    return resumes


def get_dashboard_data(user_id):
    """Get aggregated data for the dashboard / Power BI export, scoped to
    the requesting user's own resumes only."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Overall statistics
    cursor.execute("SELECT COUNT(*) AS total_resumes FROM resumes WHERE user_id = %s", (user_id,))
    stats = _row_to_dict(cursor, cursor.fetchone())

    cursor.execute("""
        SELECT AVG(CAST(ar.overall_score AS FLOAT)) AS avg_score
        FROM analysis_results ar
        JOIN resumes r ON r.id = ar.resume_id
        WHERE r.user_id = %s
    """, (user_id,))
    avg_row = _row_to_dict(cursor, cursor.fetchone())
    stats['avg_score'] = round(avg_row['avg_score'], 1) if avg_row['avg_score'] else 0

    # Score distribution
    cursor.execute("""
        SELECT
            CASE
                WHEN ar.overall_score >= 80 THEN 'Excellent'
                WHEN ar.overall_score >= 60 THEN 'Good'
                WHEN ar.overall_score >= 40 THEN 'Average'
                ELSE 'Needs Improvement'
            END AS rating,
            COUNT(*) AS count
        FROM analysis_results ar
        JOIN resumes r ON r.id = ar.resume_id
        WHERE r.user_id = %s
        GROUP BY
            CASE
                WHEN ar.overall_score >= 80 THEN 'Excellent'
                WHEN ar.overall_score >= 60 THEN 'Good'
                WHEN ar.overall_score >= 40 THEN 'Average'
                ELSE 'Needs Improvement'
            END
    """, (user_id,))
    stats['score_distribution'] = _rows_to_dicts(cursor, cursor.fetchall())

    # Top skills
    cursor.execute("""
        SELECT s.skill_name, s.category, COUNT(*) AS frequency
        FROM skills s
        JOIN resumes r ON r.id = s.resume_id
        WHERE r.user_id = %s
        GROUP BY s.skill_name, s.category
        ORDER BY frequency DESC
        LIMIT 20
    """, (user_id,))
    stats['top_skills'] = _rows_to_dicts(cursor, cursor.fetchall())

    # Recommended fields distribution
    cursor.execute("""
        SELECT ar.recommended_field, COUNT(*) AS count
        FROM analysis_results ar
        JOIN resumes r ON r.id = ar.resume_id
        WHERE r.user_id = %s AND ar.recommended_field IS NOT NULL
        GROUP BY ar.recommended_field
        ORDER BY count DESC
    """, (user_id,))
    stats['field_distribution'] = _rows_to_dicts(cursor, cursor.fetchall())

    # Score over time (monthly averages)
    cursor.execute("""
        SELECT
            TO_CHAR(r.upload_date, 'YYYY-MM') AS month_label,
            ROUND(CAST(AVG(ar.overall_score) AS NUMERIC), 1) AS avg_score,
            COUNT(*) AS resume_count
        FROM resumes r
        JOIN analysis_results ar ON ar.resume_id = r.id
        WHERE r.upload_date IS NOT NULL AND r.user_id = %s
        GROUP BY TO_CHAR(r.upload_date, 'YYYY-MM')
        ORDER BY month_label
    """, (user_id,))
    stats['score_over_time'] = _rows_to_dicts(cursor, cursor.fetchall())

    # ATS breakdown averages (skills, education, experience, formatting)
    cursor.execute("""
        SELECT
            ROUND(CAST(AVG(ar.skills_score) AS NUMERIC), 1) AS avg_skills,
            ROUND(CAST(AVG(ar.education_score) AS NUMERIC), 1) AS avg_education,
            ROUND(CAST(AVG(ar.experience_score) AS NUMERIC), 1) AS avg_experience,
            ROUND(CAST(AVG(ar.formatting_score) AS NUMERIC), 1) AS avg_formatting,
            ROUND(CAST(AVG(ar.overall_score) AS NUMERIC), 1) AS avg_overall
        FROM analysis_results ar
        JOIN resumes r ON r.id = ar.resume_id
        WHERE r.user_id = %s
    """, (user_id,))
    ats_row = _row_to_dict(cursor, cursor.fetchone())
    stats['ats_breakdown'] = {
        'skills': ats_row.get('avg_skills') or 0,
        'education': ats_row.get('avg_education') or 0,
        'experience': ats_row.get('avg_experience') or 0,
        'formatting': ats_row.get('avg_formatting') or 0,
        'overall': ats_row.get('avg_overall') or 0
    }

    # Quality categories
    cursor.execute("""
        SELECT
            SUM(CASE WHEN ar.overall_score >= 80 THEN 1 ELSE 0 END) AS high_quality,
            SUM(CASE WHEN ar.overall_score >= 60 AND ar.overall_score < 80 THEN 1 ELSE 0 END) AS medium_quality,
            SUM(CASE WHEN ar.overall_score < 60 THEN 1 ELSE 0 END) AS low_quality
        FROM analysis_results ar
        JOIN resumes r ON r.id = ar.resume_id
        WHERE r.user_id = %s
    """, (user_id,))
    quality_row = _row_to_dict(cursor, cursor.fetchone())
    stats['quality_categories'] = {
        'high': quality_row.get('high_quality') or 0,
        'medium': quality_row.get('medium_quality') or 0,
        'low': quality_row.get('low_quality') or 0
    }

    # All resume data for Power BI export
    cursor.execute("SELECT * FROM resume_dashboard WHERE user_id = %s", (user_id,))
    stats['all_data'] = _rows_to_dicts(cursor, cursor.fetchall())

    cursor.close()
    conn.close()
    return stats


# ============================================================================
# User Authentication Functions
# ============================================================================

def _hash_password(password):
    """Hash a password using Werkzeug's default algorithm (scrypt)."""
    return generate_password_hash(password)


def _is_legacy_hash(stored_hash):
    """Accounts created before the hashing upgrade store '{salt}${sha256hex}'
    with no ':' — Werkzeug hashes always contain one (e.g.
    'scrypt:32768:8:1$salt$hash'), so this is a reliable discriminator."""
    return bool(stored_hash) and ':' not in stored_hash


def _verify_password_legacy(password, stored_hash):
    """Verify against the old salted-SHA-256 format."""
    try:
        salt, hashed = stored_hash.split('$', 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == hashed
    except (ValueError, AttributeError):
        return False


def _verify_password(password, stored_hash):
    """Verify a password against a stored hash, supporting both the current
    Werkzeug format and the legacy salted-SHA-256 format so accounts that
    haven't logged in since the upgrade still work."""
    if _is_legacy_hash(stored_hash):
        return _verify_password_legacy(password, stored_hash)
    try:
        return check_password_hash(stored_hash, password)
    except (ValueError, TypeError):
        return False


def init_users_table():
    """Create the users table if it doesn't exist. Also ensures DB_SCHEMA
    itself exists — the earliest DB touch point at app startup, so a
    completely fresh Neon database (no schema yet) still boots cleanly."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{Config.DB_SCHEMA}"')
    conn.commit()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(150) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            reset_token VARCHAR(255) NULL,
            reset_token_expiry TIMESTAMP NULL
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def register_user(full_name, email, password):
    """Register a new user. Returns (success, message)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Check if email already exists
    cursor.execute("SELECT id FROM users WHERE email = %s", (email.lower().strip(),))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return False, 'An account with this email already exists.'

    password_hash = _hash_password(password)
    # email_verified=1: registration no longer requires an email-verification
    # step, so new accounts are usable immediately.
    cursor.execute(
        "INSERT INTO users (full_name, email, password_hash, email_verified) VALUES (%s, %s, %s, 1)",
        (full_name.strip(), email.lower().strip(), password_hash)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return True, 'Account created successfully.'


def authenticate_user(email, password):
    """Authenticate a user by email and password. Returns user dict or None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, full_name, email, password_hash, is_active, email_verified FROM users WHERE email = %s",
        (email.lower().strip(),)
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        return None

    user = _row_to_dict(cursor, row)

    if not user.get('is_active'):
        cursor.close()
        conn.close()
        return None

    stored_hash = user.get('password_hash', '')
    if not _verify_password(password, stored_hash):
        cursor.close()
        conn.close()
        return None

    if _is_legacy_hash(stored_hash):
        # Transparently upgrade this account to the current hashing
        # algorithm now that we have the plaintext password in hand — no
        # forced password reset needed.
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (_hash_password(password), user['id'])
        )
        conn.commit()

    cursor.close()
    conn.close()
    return {
        'id': user['id'],
        'full_name': user['full_name'],
        'email': user['email'],
        'email_verified': bool(user.get('email_verified')),
    }


def get_user_by_id(user_id):
    """Get user by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, email FROM users WHERE id = %s AND is_active = 1", (user_id,))
    row = cursor.fetchone()
    user = _row_to_dict(cursor, row) if row else None
    cursor.close()
    conn.close()
    return user


def get_user_by_email(email):
    """Get user by email."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, email FROM users WHERE email = %s AND is_active = 1",
                   (email.lower().strip(),))
    row = cursor.fetchone()
    user = _row_to_dict(cursor, row) if row else None
    cursor.close()
    conn.close()
    return user


def create_reset_code(email):
    """Generate a 6-digit reset code for the given email. Returns code or None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = %s AND is_active = 1", (email.lower().strip(),))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        return None

    code = str(random.randint(100000, 999999))
    expiry = datetime.now() + timedelta(minutes=10)
    cursor.execute(
        "UPDATE users SET reset_token = %s, reset_token_expiry = %s WHERE email = %s",
        (code, expiry, email.lower().strip())
    )
    conn.commit()
    cursor.close()
    conn.close()
    return code


def verify_reset_code(email, code):
    """Verify a 6-digit reset code. Returns True if valid."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT reset_token, reset_token_expiry FROM users "
        "WHERE email = %s AND is_active = 1",
        (email.lower().strip(),)
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        return False

    user = _row_to_dict(cursor, row)
    cursor.close()
    conn.close()

    if (user['reset_token'] and user['reset_token'] == code.strip()
            and user['reset_token_expiry'] and user['reset_token_expiry'] >= datetime.now()):
        return True
    return False


def reset_token_still_valid(email):
    """Whether the reset window opened by a prior successful
    verify_reset_code() call for this email hasn't expired yet. The
    /reset-password route only gates on a Flask session flag with no
    expiry of its own, so without this second, time-based check here, a
    browser tab left open past the 10-minute code window could still set a
    new password with no live verification at all."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT reset_token, reset_token_expiry FROM users WHERE email = %s",
        (email.lower().strip(),)
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        return False

    user = _row_to_dict(cursor, row)
    cursor.close()
    conn.close()

    return bool(
        user['reset_token']
        and user['reset_token_expiry']
        and user['reset_token_expiry'] >= datetime.now()
    )


def create_email_verification_code(email):
    """Generate a 6-digit email-verification code. Returns code or None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = %s", (email.lower().strip(),))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        return None

    code = str(random.randint(100000, 999999))
    expiry = datetime.now() + timedelta(minutes=10)
    cursor.execute(
        "UPDATE users SET verification_code = %s, verification_code_expiry = %s WHERE email = %s",
        (code, expiry, email.lower().strip())
    )
    conn.commit()
    cursor.close()
    conn.close()
    return code


def verify_email_code(email, code):
    """Verify a 6-digit email-verification code and mark the account
    verified if it matches. Returns True if valid."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT verification_code, verification_code_expiry FROM users WHERE email = %s",
        (email.lower().strip(),)
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        return False

    user = _row_to_dict(cursor, row)

    if (user['verification_code'] and user['verification_code'] == code.strip()
            and user['verification_code_expiry'] and user['verification_code_expiry'] >= datetime.now()):
        cursor.execute(
            "UPDATE users SET email_verified = 1, verification_code = NULL, verification_code_expiry = NULL "
            "WHERE email = %s",
            (email.lower().strip(),)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True

    cursor.close()
    conn.close()
    return False


def reset_user_password(email, new_password):
    """Reset password for a verified email. Returns (success, message)."""
    password_hash = _hash_password(new_password)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expiry = NULL WHERE email = %s",
        (password_hash, email.lower().strip())
    )
    conn.commit()
    cursor.close()
    conn.close()
    return True, 'Password has been reset successfully.'


# ============================================================================
# Data Deletion (account / resume ownership cleanup)
# ============================================================================

def delete_resume(resume_id, user_id):
    """Delete a resume owned by user_id (cascades to its skills/education/
    experience/analysis_results at the DB level via the schema's ON DELETE
    CASCADE foreign keys). Returns the stored filename on success, so the
    caller can also remove the file from disk, or None if nothing matched
    (wrong owner or already gone)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM resumes WHERE id = %s AND user_id = %s", (resume_id, user_id))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        return None
    filename = row[0]
    cursor.execute("DELETE FROM resumes WHERE id = %s AND user_id = %s", (resume_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return filename


def user_owns_file(filename, user_id):
    """Whether the given stored filename belongs to a resume owned by
    user_id — used to gate access before serving an uploaded file."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM resumes WHERE filename = %s AND user_id = %s", (filename, user_id))
    owned = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return owned


def get_resume_filenames_for_user(user_id):
    """All stored filenames for a user's resumes — used by delete_account to
    clean up files on disk before removing the DB rows."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM resumes WHERE user_id = %s", (user_id,))
    filenames = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return filenames


def delete_account(user_id):
    """Permanently delete a user account and all of their resumes (cascades
    to skills/education/experience/analysis_results at the DB level)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM resumes WHERE user_id = %s", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return True, 'Account deleted successfully.'
