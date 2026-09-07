import os
import csv
import io
import json
import secrets
import requests
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, Response, send_from_directory, session)
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from config import Config
from analyzer import (analyse_resume, IMAGE_EXTENSIONS, generate_personalized_feedback,
                      match_job_description, RESUME_TEMPLATES, SKILLS_DB, highlight_matches)
from models import (save_resume, save_skills, save_education, save_experience,
                    save_analysis_results, get_resume_by_id, get_all_resumes,
                    get_dashboard_data, init_users_table, register_user,
                    authenticate_user, get_user_by_id, get_user_by_email,
                    create_reset_code, verify_reset_code, reset_user_password,
                    reset_token_still_valid,
                    create_email_verification_code, verify_email_code,
                    ensure_schema_migrations, delete_resume, delete_account,
                    get_resume_filenames_for_user, user_owns_file)

app = Flask(__name__)
app.config.from_object(Config)

# Display order for grouping extracted skills on the result page — mirrors
# SKILLS_DB's own category order rather than an alphabetical/arbitrary one.
SKILLS_CATEGORY_ORDER = list(SKILLS_DB.keys())

# Initialize Flask-Mail
mail = Mail(app)

# Rate limiting — keyed by IP, in-memory (fine for this app's single-process
# scale; see README's "Scaling this further" if that ever changes). Only
# applied to the auth endpoints that are actually worth throttling
# (credential guessing on /login, mass account creation on /register);
# everything else uses the default (no limit).
limiter = Limiter(get_remote_address, app=app, default_limits=[])

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Create users table if it doesn't exist
try:
    init_users_table()
except Exception:
    # Table may already exist, or the DB isn't reachable yet at import time
    # (e.g. multiple gunicorn workers racing on startup). Logged rather than
    # silently swallowed — a previous silent failure here meant a schema
    # migration never applied on the first Render boot, and the only sign
    # was /register crashing with "Invalid column name" once real traffic hit.
    app.logger.exception('init_users_table() failed at startup')

# Idempotent schema migrations (adds resumes.user_id for per-user data
# isolation, backfills existing rows, recreates the dashboard view)
try:
    ensure_schema_migrations()
except Exception:
    app.logger.exception('ensure_schema_migrations() failed at startup')


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def validate_file_content(filepath, extension):
    """Cheap content sniff on top of the extension check — a renamed file
    (e.g. a script saved as photo.jpg) shouldn't make it past upload just
    because the extension looks right. Returns True if the content matches
    what the extension claims."""
    if extension in IMAGE_EXTENSIONS:
        try:
            from PIL import Image
            with Image.open(filepath) as img:
                img.verify()
            return True
        except Exception:
            return False
    if extension == 'pdf':
        try:
            with open(filepath, 'rb') as f:
                return f.read(5) == b'%PDF-'
        except OSError:
            return False
    # .docx is a zip container — python-docx will raise on a bad one at
    # parse time, which analyse_resume() already surfaces as an error.
    return True


# --------------------------------------------------------------------------
# Authentication decorator
# --------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# --------------------------------------------------------------------------
# Authentication Routes
# --------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'])
def login():
    """Login page."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('login.html')

        user = authenticate_user(email, password)
        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['user_email'] = user['email']
            flash(f'Welcome back, {user["full_name"]}!', 'success')
            next_page = request.args.get('next') or request.form.get('next')
            # Must be a same-site path, not a protocol-relative URL like
            # "//evil.com" (browsers resolve that to an external host even
            # though it "starts with /") or a backslash variant some
            # browsers treat the same way.
            if next_page and next_page.startswith('/') and not next_page.startswith(('//', '/\\')):
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password.', 'error')
            return render_template('login.html', email=email)

    return render_template('login.html')


def _send_email(to, subject, html):
    """Send an email via SendGrid or Resend's HTTP API if configured
    (production, where outbound SMTP is commonly blocked), otherwise via
    Flask-Mail/SMTP (local dev). SendGrid is tried first — its free tier
    delivers to any recipient once a single sender email is verified,
    unlike Resend's free tier, which can only deliver to the email address
    the Resend account itself was signed up with until a full domain is
    verified. Raises on failure — callers decide how to report it."""
    if Config.SENDGRID_API_KEY:
        resp = requests.post(
            'https://api.sendgrid.com/v3/mail/send',
            headers={'Authorization': f'Bearer {Config.SENDGRID_API_KEY}'},
            json={
                'personalizations': [{'to': [{'email': to}]}],
                'from': {'email': Config.SENDGRID_FROM},
                'subject': subject,
                'content': [{'type': 'text/html', 'value': html}],
            },
            timeout=10,
        )
        resp.raise_for_status()
    elif Config.RESEND_API_KEY:
        resp = requests.post(
            'https://api.resend.com/emails',
            headers={'Authorization': f'Bearer {Config.RESEND_API_KEY}'},
            json={'from': Config.RESEND_FROM, 'to': [to], 'subject': subject, 'html': html},
            timeout=10,
        )
        resp.raise_for_status()
    else:
        mail.send(Message(subject=subject, recipients=[to], html=html))


def _send_verification_email(email):
    """Generate and email a fresh 6-digit verification code."""
    code = create_email_verification_code(email)
    if not code:
        return False
    try:
        _send_email(
            email,
            'Verify Your Email - Smart Resume Analyser',
            render_template('email_verification.html', verification_code=code, user_email=email)
        )
        flash('A 6-digit verification code has been sent to your email.', 'success')
    except Exception:
        app.logger.exception('Failed to send verification email to %s', email)
        flash('We could not send the verification email right now. Please try Resend Code in a moment.', 'error')
    return True


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def register():
    """Registration page."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validation
        errors = []
        if not full_name:
            errors.append('Full name is required.')
        if not email:
            errors.append('Email is required.')
        if not password:
            errors.append('Password is required.')
        elif len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm_password:
            errors.append('Passwords do not match.')

        if errors:
            for err in errors:
                flash(err, 'error')
            return render_template('register.html', full_name=full_name, email=email)

        success, message = register_user(full_name, email, password)
        if success:
            # No email-verification step — log the new account straight in,
            # the same way login() does.
            user = authenticate_user(email, password)
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['user_email'] = user['email']
            flash(f'Welcome, {user["full_name"]}!', 'success')
            return redirect(url_for('index'))
        else:
            flash(message, 'error')
            return render_template('register.html', full_name=full_name, email=email)

    return render_template('register.html')


@app.route('/logout')
def logout():
    """Log the user out."""
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


@app.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def forgot_password():
    """Forgot password page — sends a 6-digit code to email."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            flash('Please enter your email address.', 'error')
            return render_template('forgot_password.html')

        code = create_reset_code(email)
        if code:
            try:
                _send_email(
                    email,
                    'Your Reset Code - Smart Resume Analyser',
                    render_template('email_reset.html', reset_code=code, user_email=email)
                )
                flash('A 6-digit code has been sent to your email.', 'success')
            except Exception:
                app.logger.exception('Failed to send password-reset email to %s', email)
                flash('We could not send the reset email right now. Please try Resend Code in a moment.', 'error')
            return redirect(url_for('verify_code', email=email))
        else:
            # Don't reveal whether the email exists
            flash('If an account with that email exists, a code has been sent.', 'success')
            return redirect(url_for('forgot_password'))

    return render_template('forgot_password.html')


@app.route('/verify-code', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'])
def verify_code():
    """Verify the 6-digit reset code."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    email = request.args.get('email', '') or request.form.get('email', '')

    if not email:
        flash('Please start the password reset process again.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        code = request.form.get('code', '').strip()

        if not code or len(code) != 6:
            flash('Please enter the 6-digit code.', 'error')
            return render_template('verify_code.html', email=email)

        if verify_reset_code(email, code):
            # Code is valid — store email in session for reset page
            session['reset_email'] = email
            flash('Code verified! Set your new password.', 'success')
            return redirect(url_for('reset_password'))
        else:
            flash('Invalid or expired code. Please try again.', 'error')
            return render_template('verify_code.html', email=email)

    return render_template('verify_code.html', email=email)


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Reset password after code verification."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    email = session.get('reset_email')
    if not email:
        flash('Please verify your code first.', 'error')
        return redirect(url_for('forgot_password'))

    if not reset_token_still_valid(email):
        session.pop('reset_email', None)
        flash('Your reset code has expired. Please start again.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not password or len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('reset_password.html')
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html')

        success, message = reset_user_password(email, password)
        if success:
            session.pop('reset_email', None)
            flash('Password reset successfully! Please log in with your new password.', 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')
            return redirect(url_for('forgot_password'))

    return render_template('reset_password.html')


@app.route('/verify-email', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'])
def verify_email():
    """Verify the 6-digit email-verification code, then log the user in —
    they already proved their password at registration, so a second login
    step here would just be friction."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    email = request.args.get('email', '') or request.form.get('email', '')

    if not email:
        flash('Please register or log in first.', 'error')
        return redirect(url_for('register'))

    if request.method == 'POST':
        code = request.form.get('code', '').strip()

        if not code or len(code) != 6:
            flash('Please enter the 6-digit code.', 'error')
            return render_template('verify_email.html', email=email)

        if verify_email_code(email, code):
            user = get_user_by_email(email)
            if user:
                session['user_id'] = user['id']
                session['user_name'] = user['full_name']
                session['user_email'] = user['email']
            flash('Email verified! Welcome.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid or expired code. Please try again.', 'error')
            return render_template('verify_email.html', email=email)

    return render_template('verify_email.html', email=email)


@app.route('/resend-verification', methods=['GET', 'POST'])
@limiter.limit('5 per hour')
def resend_verification():
    """Resend a fresh verification code to an unverified account."""
    email = request.args.get('email', '') or request.form.get('email', '')
    if not email:
        flash('Please register or log in first.', 'error')
        return redirect(url_for('register'))

    _send_verification_email(email)
    return redirect(url_for('verify_email', email=email))


# --------------------------------------------------------------------------
# Routes (all protected with login_required)
# --------------------------------------------------------------------------

@app.route('/')
@login_required
def index():
    """Home page with resume upload form."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
@login_required
def upload_resume():
    """Handle resume upload and analysis."""
    if 'resume' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('index'))

    file = request.files['resume']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('index'))

    if not allowed_file(file.filename):
        flash('Only PDF, Word (.docx), and image files (PNG, JPG, BMP, TIFF) are allowed.', 'error')
        return redirect(url_for('index'))

    original_filename = secure_filename(file.filename)
    extension = original_filename.rsplit('.', 1)[1].lower()
    # Prefix with a random token — two users uploading a file with the same
    # original name (e.g. "resume.pdf") would otherwise overwrite each
    # other's file on disk since storage isn't namespaced per user.
    filename = f"{secrets.token_hex(8)}_{original_filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    if not validate_file_content(filepath, extension):
        os.remove(filepath)
        flash("That file's content doesn't match its extension — please upload a genuine PDF, Word, or image file.", 'error')
        return redirect(url_for('index'))

    try:
        # Analyse the resume
        result = analyse_resume(filepath, original_filename=original_filename)

        if 'error' in result:
            try:
                os.remove(filepath)
            except OSError:
                pass
            flash(result['error'], 'error')
            return redirect(url_for('index'))

        # Save to database
        resume_id = save_resume(
            result['name'], result['email'], result['phone'],
            filename, result['raw_text'], session['user_id']
        )

        save_skills(resume_id, result['skills'])
        save_education(resume_id, result['education'])
        save_experience(resume_id, result['experience'])

        scores = result['scores']
        # Pack all extra data into a single JSON payload
        extra_data = {
            'explanations': result.get('explanations', {}),
            'field_recommendations': [
                {'field': f, 'confidence': c, 'details': d}
                for f, c, d in result.get('field_recommendations', [])
            ],
            'recommendations': result['recommendations'],
            'ats_results': result.get('ats_results', {}),
            'career_roles': result.get('career_roles', []),
            'employer_summary': result.get('employer_summary', {}),
        }
        save_analysis_results(
            resume_id,
            scores['overall'], scores['skills'], scores['education'],
            scores['experience'], scores['formatting'],
            result['recommended_field'],
            json.dumps(extra_data)
        )

        return redirect(url_for('result', resume_id=resume_id))

    except Exception as e:
        # Nothing references this file on disk if analysis failed before
        # save_resume() ran (no DB row was created), so it would otherwise
        # sit in the uploads folder forever with no way to clean it up.
        try:
            os.remove(filepath)
        except OSError:
            pass
        flash(f'An error occurred during analysis: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/result/<int:resume_id>')
@login_required
def result(resume_id):
    """Display analysis results for a specific resume."""
    resume = get_resume_by_id(resume_id, session['user_id'])
    if not resume:
        flash('Resume not found.', 'error')
        return redirect(url_for('index'))

    # Parse the stored JSON
    if resume['analysis'] and resume['analysis']['recommendations']:
        try:
            parsed = json.loads(resume['analysis']['recommendations'])
            if isinstance(parsed, dict):
                resume['analysis']['explanations'] = parsed.get('explanations', {})
                resume['analysis']['field_recommendations'] = parsed.get('field_recommendations', [])
                resume['analysis']['recommendations'] = parsed.get('recommendations', [])
                resume['analysis']['ats_results'] = parsed.get('ats_results', {})
                resume['analysis']['career_roles'] = parsed.get('career_roles', [])
                resume['analysis']['employer_summary'] = parsed.get('employer_summary', {})
            elif isinstance(parsed, list):
                resume['analysis']['recommendations'] = parsed
                resume['analysis']['explanations'] = {}
                resume['analysis']['field_recommendations'] = []
                resume['analysis']['ats_results'] = {}
                resume['analysis']['career_roles'] = []
                resume['analysis']['employer_summary'] = {}
        except (json.JSONDecodeError, TypeError):
            resume['analysis']['recommendations'] = []
            resume['analysis']['explanations'] = {}
            resume['analysis']['field_recommendations'] = []
            resume['analysis']['ats_results'] = {}
            resume['analysis']['career_roles'] = []
            resume['analysis']['employer_summary'] = {}

    # Group skills by category (in SKILLS_DB's category order) instead of
    # rendering one flat list, so the result page reads by skill type.
    skills_by_category = []
    if resume.get('skills'):
        by_cat = {}
        for skill in resume['skills']:
            by_cat.setdefault(skill['category'], []).append(skill)
        for category in SKILLS_CATEGORY_ORDER:
            if category in by_cat:
                skills_by_category.append((category, by_cat.pop(category)))
        # Any category not in the known order (shouldn't normally happen) still shows up
        for category, skills in by_cat.items():
            skills_by_category.append((category, skills))

    highlighted_text = highlight_matches(
        resume.get('raw_text', ''),
        [s['skill_name'] for s in resume.get('skills', [])]
    )

    return render_template('result.html', resume=resume, skills_by_category=skills_by_category,
                           highlighted_text=highlighted_text)


# --------------------------------------------------------------------------
# Feature 1 & 7: Personalized Feedback / Resume Personalization
# --------------------------------------------------------------------------

@app.route('/personalize/<int:resume_id>', methods=['GET', 'POST'])
@login_required
def personalize(resume_id):
    """Context-aware personalized feedback page."""
    resume = get_resume_by_id(resume_id, session['user_id'])
    if not resume:
        flash('Resume not found.', 'error')
        return redirect(url_for('index'))

    # Parse stored JSON for full analysis data
    parsed_data = {}
    if resume['analysis'] and resume['analysis']['recommendations']:
        try:
            parsed_data = json.loads(resume['analysis']['recommendations'])
            if not isinstance(parsed_data, dict):
                parsed_data = {}
        except (json.JSONDecodeError, TypeError):
            parsed_data = {}

    feedback = None
    career_goal = ''
    experience_level = ''
    target_role = ''

    if request.method == 'POST':
        career_goal = request.form.get('career_goal', '')
        experience_level = request.form.get('experience_level', '')
        target_role = request.form.get('target_role', '')

        # Build resume_data dict from DB data
        resume_data = {
            'skills': [(s['skill_name'], s.get('category', '')) for s in resume.get('skills', [])],
            'education': resume.get('education', []),
            'experience': [(e.get('title', ''), e.get('company', ''), e.get('description', ''))
                          for e in resume.get('experience', [])],
            'scores': {
                'skills': resume['analysis'].get('skills_score', 0) if resume['analysis'] else 0,
                'education': resume['analysis'].get('education_score', 0) if resume['analysis'] else 0,
                'experience': resume['analysis'].get('experience_score', 0) if resume['analysis'] else 0,
                'formatting': resume['analysis'].get('formatting_score', 0) if resume['analysis'] else 0,
            },
            'raw_text': resume.get('raw_text', ''),
        }
        feedback = generate_personalized_feedback(
            resume_data, career_goal, experience_level, target_role
        )

    return render_template('personalize.html',
                           resume=resume,
                           feedback=feedback,
                           career_goal=career_goal,
                           experience_level=experience_level,
                           target_role=target_role)


# --------------------------------------------------------------------------
# Feature 3: Smart Job-Match Analysis
# --------------------------------------------------------------------------

@app.route('/job-match/<int:resume_id>', methods=['GET', 'POST'])
@login_required
def job_match(resume_id):
    """Compare resume against a job description."""
    resume = get_resume_by_id(resume_id, session['user_id'])
    if not resume:
        flash('Resume not found.', 'error')
        return redirect(url_for('index'))

    match_result = None
    job_description = ''

    if request.method == 'POST':
        job_description = request.form.get('job_description', '')
        if job_description.strip():
            match_result = match_job_description(
                resume.get('raw_text', ''),
                job_description
            )

    return render_template('job_match.html',
                           resume=resume,
                           match_result=match_result,
                           job_description=job_description)


# --------------------------------------------------------------------------
# Feature 4: Resume Builder
# --------------------------------------------------------------------------

@app.route('/builder')
@login_required
def builder():
    """Guided, step-by-step resume builder — one flexible template that
    covers students working while studying, online-education graduates, and
    experienced professionals alike, so there's no template picker to choose
    between."""
    return render_template('builder_template.html',
                           template=RESUME_TEMPLATES['universal'],
                           template_id='universal')


@app.route('/builder/<template_id>')
@login_required
def builder_template(template_id):
    """Old per-template URLs (from before the builder was consolidated to a
    single template) still resolve here instead of 404ing."""
    return redirect(url_for('builder'))


def _builder_section_legend():
    """Numbered list of the builder's sections plus whether each is a single
    text block (safe for the AI to directly rewrite) or a repeatable
    structured section like Work Experience (multiple entries with separate
    fields — a single block of replacement text doesn't map onto that)."""
    sections = RESUME_TEMPLATES['universal']['sections']
    lines = []
    for i, s in enumerate(sections, start=1):
        kind = ('repeatable — holds multiple structured entries; never use a SUGGEST '
                'marker for this one' if s.get('type') == 'repeatable'
                else 'a single text block — safe to suggest a direct replacement for')
        lines.append(f'{i}. {s["name"]} ({kind})')
    return '\n'.join(lines)


def _resume_chat_reply(message, history, resume_context):
    """Call Google's Gemini API for the Resume Builder's AI assistant.
    Raises on failure — the caller decides how to report it."""
    system_prompt = (
        'You are a friendly, encouraging resume-writing assistant embedded in a '
        'resume builder tool. Help the user strengthen their resume: sharpen '
        'wording, suggest strong action verbs, quantify achievements, fix clarity '
        'issues, and keep advice ATS-friendly (simple formatting, no tables or '
        'graphics). Keep replies concise and grounded in the user\'s actual resume '
        "content below — don't ask them to repeat information that's already there. "
        'Reply in plain text only — no markdown (no **bold**, no # headings, no '
        'backticks); use plain dashes or numbers for lists instead.\n\n'
        'The resume has these sections, in order:\n' + _builder_section_legend() + '\n\n'
        'When you have a concrete, ready-to-use replacement for one of the single-'
        'text-block sections above, wrap ONLY that replacement text in a marker on '
        'its own lines, using the section\'s number from the list, like this:\n'
        '[[SUGGEST:3]]\nThe improved text goes here.\n[[/SUGGEST]]\n'
        'Never wrap a repeatable section (Work Experience, Education) in a SUGGEST '
        "marker — describe what to change there in plain sentences instead, since "
        "those hold several separate fields you can't replace with one block of "
        'text. Only use a SUGGEST marker when confidently rewriting that whole '
        "section's content; for general advice, questions, or lists of ideas, just "
        'reply normally with no marker.\n\n'
        'Current resume draft:\n' + (resume_context or '(nothing written yet)')
    )
    contents = []
    for turn in history[-10:]:
        if not isinstance(turn, dict):
            continue
        role = turn.get('role')
        content = (turn.get('content') or '').strip()[:2000]
        if role in ('user', 'assistant') and content:
            contents.append({'role': 'model' if role == 'assistant' else 'user', 'parts': [{'text': content}]})
    contents.append({'role': 'user', 'parts': [{'text': message}]})

    resp = requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/{Config.GEMINI_MODEL}:generateContent',
        headers={'x-goog-api-key': Config.GEMINI_API_KEY},
        json={
            'system_instruction': {'parts': [{'text': system_prompt}]},
            'contents': contents,
            'generationConfig': {'maxOutputTokens': 2048, 'temperature': 0.7},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()


@app.route('/api/resume-chat', methods=['POST'])
@login_required
@limiter.limit('20 per hour')
def api_resume_chat():
    """AI assistant chat for the Resume Builder. Sends the user's message plus
    their current draft as context to an LLM and returns a reply. Free tier,
    but still rate-limited since it shares one project-wide quota."""
    if not Config.GEMINI_API_KEY:
        return jsonify({'error': 'The AI assistant is not configured on this server yet.'}), 503

    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()[:2000]
    if not message:
        return jsonify({'error': 'Please enter a message.'}), 400

    history = data.get('history') if isinstance(data.get('history'), list) else []
    resume_context = (data.get('resume_context') or '').strip()[:6000]

    try:
        reply = _resume_chat_reply(message, history, resume_context)
        return jsonify({'reply': reply})
    except requests.exceptions.RequestException:
        app.logger.exception('Resume chat: Gemini request failed')
        return jsonify({'error': 'The AI assistant is temporarily unavailable. Please try again shortly.'}), 502
    except Exception:
        app.logger.exception('Resume chat: unexpected error')
        return jsonify({'error': 'Something went wrong. Please try again.'}), 500


# --------------------------------------------------------------------------
# Existing routes
# --------------------------------------------------------------------------

@app.route('/history')
@login_required
def history():
    """Show the current user's previously analysed resumes."""
    resumes = get_all_resumes(session['user_id'])
    return render_template('history.html', resumes=resumes)


@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard page with analytics and Power BI integration."""
    try:
        data = get_dashboard_data(session['user_id'])
    except Exception:
        data = {
            'total_resumes': 0,
            'avg_score': 0,
            'score_distribution': [],
            'top_skills': [],
            'field_distribution': [],
            'all_data': [],
            'score_over_time': [],
            'ats_breakdown': {'skills': 0, 'education': 0, 'experience': 0, 'formatting': 0, 'overall': 0},
            'quality_categories': {'high': 0, 'medium': 0, 'low': 0}
        }
    return render_template('dashboard.html', data=data)


@app.route('/api/dashboard-data')
@login_required
def api_dashboard_data():
    """API endpoint returning dashboard data as JSON (for Power BI)."""
    try:
        data = get_dashboard_data(session['user_id'])
        for item in data.get('all_data', []):
            if 'upload_date' in item and item['upload_date']:
                item['upload_date'] = str(item['upload_date'])
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/export/csv')
@login_required
def export_csv():
    """Export all resume data as CSV for Power BI import."""
    try:
        data = get_dashboard_data(session['user_id'])
    except Exception:
        flash('No data available to export.', 'error')
        return redirect(url_for('dashboard'))

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'ID', 'Candidate Name', 'Email', 'Upload Date',
        'Overall Score', 'Skills Score', 'Education Score',
        'Experience Score', 'Formatting Score',
        'Recommended Field', 'Total Skills'
    ])

    for row in data.get('all_data', []):
        writer.writerow([
            row.get('id', ''),
            row.get('candidate_name', ''),
            row.get('email', ''),
            str(row.get('upload_date', '')),
            row.get('overall_score', ''),
            row.get('skills_score', ''),
            row.get('education_score', ''),
            row.get('experience_score', ''),
            row.get('formatting_score', ''),
            row.get('recommended_field', ''),
            row.get('total_skills', '')
        ])

    response = Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=resume_analytics.csv'}
    )
    return response


@app.route('/api/resume/<int:resume_id>')
@login_required
def api_resume(resume_id):
    """API endpoint to get resume data as JSON."""
    resume = get_resume_by_id(resume_id, session['user_id'])
    if not resume:
        return jsonify({'error': 'Resume not found'}), 404

    if resume.get('upload_date'):
        resume['upload_date'] = str(resume['upload_date'])
    if resume.get('analysis') and resume['analysis'].get('analysed_date'):
        resume['analysis']['analysed_date'] = str(resume['analysis']['analysed_date'])

    return jsonify(resume)


@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    """Serve an uploaded resume file — only to the user who owns it. This
    used to be served straight from static/, which had no auth check at
    all (anyone who knew or guessed a filename could download someone
    else's resume)."""
    if not user_owns_file(filename, session['user_id']):
        flash('File not found.', 'error')
        return redirect(url_for('history'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/resume/<int:resume_id>/delete', methods=['POST'])
@login_required
def delete_resume_route(resume_id):
    """Permanently delete one of the current user's resumes, including its
    stored file and (via ON DELETE CASCADE) its skills/education/
    experience/analysis rows."""
    filename = delete_resume(resume_id, session['user_id'])
    if filename:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        except OSError:
            pass
        flash('Resume deleted.', 'success')
    else:
        flash('Resume not found.', 'error')
    return redirect(url_for('history'))


@app.route('/account/delete', methods=['POST'])
@login_required
def delete_account_route():
    """Permanently delete the current user's account and every resume they
    uploaded, including the files on disk."""
    user_id = session['user_id']
    for filename in get_resume_filenames_for_user(user_id):
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        except OSError:
            pass
    delete_account(user_id)
    session.clear()
    flash('Your account and all associated data have been permanently deleted.', 'success')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
