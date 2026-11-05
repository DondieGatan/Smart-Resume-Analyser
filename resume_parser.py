"""Finds the structured facts in resume text: name, email, phone, skills, education and work experience
(plus the years of experience the dated roles cover). Scoring and recommendations live in analyzer.py."""
import re
import os

import nltk
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.corpus import stopwords

from analyzer_data import SKILLS_DB, DEGREE_KEYWORDS, JOB_TITLES

MAX_NAME_SEARCH_CHARS = 20000   # the name is near the top; nothing deeper is read
MAX_NAME_LINE_CHARS = 500


def extract_name(text):
    """Extract candidate name from the resume using multiple strategies.

    Uses a layered approach:
    1. Filter out section headers and common resume vocabulary
    2. Identify lines that look like human names (not English words)
    3. Handle multi-line names split across PDF lines
    4. Use NLTK NER as a fallback
    """
    # A name is at the top of a resume, on a short line. Looking only there keeps this function fast on a file
    # that is one enormous line (some PDFs extract that way), where the per-character checks below would take
    # minutes.
    lines = [line[:MAX_NAME_LINE_CHARS] for line in text[:MAX_NAME_SEARCH_CHARS].strip().split('\n')]

    # ── Section headers that are NEVER names ──
    SECTION_HEADERS = {
        'education', 'experience', 'skills', 'projects', 'summary', 'objective',
        'certifications', 'achievements', 'references', 'profile', 'contact',
        'interests', 'hobbies', 'languages', 'awards', 'training', 'volunteer',
        'publications', 'activities', 'qualifications', 'technical skills',
        'work experience', 'professional experience', 'personal information',
        'curriculum vitae', 'resume', 'cv', 'portfolio', 'about me', 'about',
        'personal details', 'career objective', 'professional summary',
        'profile summary', 'work history', 'key skills', 'core competencies',
        'soft skills', 'hard skills', 'relevant coursework', 'coursework',
        'extracurricular', 'extracurricular activities', 'leadership',
        'professional skills', 'additional information', 'declaration',
    }

    # ── Common English words found in resumes that are NOT names ──
    # If ALL words in a line are common English words, it's NOT a name
    NOT_NAME_WORDS = {
        # Resume section/descriptor words
        'adaptability', 'leadership', 'problem', 'solving', 'skills', 'communication',
        'fast', 'learner', 'ability', 'multi', 'task', 'hard', 'working', 'social',
        'media', 'time', 'management', 'motivated', 'eager', 'learn', 'seeking',
        'entry', 'level', 'opportunity', 'strong', 'work', 'ethic', 'passion',
        'continuous', 'growth', 'committed', 'contributing', 'team', 'success',
        'gaining', 'valuable', 'professional', 'environment', 'detail', 'oriented',
        'creative', 'analytical', 'critical', 'thinking', 'interpersonal',
        'organizational', 'self', 'driven', 'proactive', 'flexible', 'reliable',
        'dedicated', 'enthusiastic', 'innovative', 'strategic', 'collaborative',
        # Job/activity description words
        'performed', 'demonstrated', 'applied', 'conducted', 'maintained',
        'developed', 'designed', 'managed', 'organized', 'implemented',
        'achieved', 'hands', 'practical', 'experience', 'proficiency',
        'workshop', 'training', 'inspection', 'component', 'protocols',
        'free', 'strict', 'accordance', 'relevant', 'technical', 'compliance',
        'ensuring', 'support', 'provided', 'assisted', 'coordinated',
        # Job titles
        'student', 'engineer', 'developer', 'designer', 'manager', 'analyst',
        'consultant', 'specialist', 'coordinator', 'assistant', 'associate',
        'director', 'officer', 'administrator', 'technician', 'supervisor',
        'intern', 'freelancer', 'graduate', 'undergraduate', 'senior', 'junior',
        'lead', 'head', 'chief', 'executive', 'president', 'vice',
        'college', 'university', 'school', 'institute', 'academy',
        'software', 'hardware', 'network', 'system', 'database', 'web', 'mobile',
        'full', 'stack', 'front', 'end', 'back', 'data', 'science', 'information',
        'technology', 'computer', 'business', 'marketing', 'sales', 'finance',
        'accounting', 'human', 'resources', 'operations', 'project',
        # Common filler
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was', 'were',
        'been', 'being', 'have', 'has', 'had', 'having', 'will', 'would', 'could',
        'should', 'may', 'might', 'can', 'shall', 'must', 'need', 'want',
        'new', 'old', 'good', 'best', 'more', 'most', 'very', 'well', 'also',
        'who', 'where', 'when', 'what', 'how', 'why', 'which',
        # Address/location words
        'street', 'road', 'avenue', 'boulevard', 'city', 'state', 'country',
        'floor', 'building', 'tower', 'block', 'unit', 'apartment',
    }

    def is_section_header(line_text):
        """Check if a line is a section header."""
        cleaned = line_text.lower().strip()
        if cleaned in SECTION_HEADERS:
            return True
        # Spaced-out headers: "S K I L L S" -> "skills"
        collapsed = re.sub(r'\s+', '', cleaned)
        if collapsed in SECTION_HEADERS:
            return True
        # Headers with decorators: "--- SKILLS ---" or "| EDUCATION |"
        stripped = re.sub(r'^[\s\-–—=_|*#]+|[\s\-–—=_|*#]+$', '', cleaned)
        if stripped in SECTION_HEADERS:
            return True
        return False

    def is_noise_line(line_text):
        """Check if a line is contact info, URL, date, or other non-name content."""
        line_text = line_text.strip()
        if not line_text or len(line_text) < 2:
            return True
        # Email
        if re.search(r'[\w.+-]{1,64}@[\w-]{1,63}\.[\w.-]{1,190}', line_text):
            return True
        # URL
        if re.search(r'(http|www\.|\.com|\.org|\.net|\.edu|linkedin|github|portfolio)', line_text, re.IGNORECASE):
            return True
        # Phone number (digits with separators dominate the line)
        digits_only = re.sub(r'[^\d]', '', line_text)
        if len(digits_only) >= 7 and len(digits_only) / max(len(line_text.replace(' ', '')), 1) > 0.5:
            return True
        # Starts with phone-like pattern
        if re.match(r'^[\s?]*[\+\(]?\d', line_text) and len(digits_only) >= 7:
            return True
        # Address-like
        if re.search(r'\b\d{4,6}\b', line_text) and re.search(
            r'(street|road|ave|blvd|city|state|zip|uae|usa|uk|country|sharjah|dubai|abu dhabi|deira|cavite|imus)',
            line_text, re.IGNORECASE
        ):
            return True
        # Job title lines
        if re.match(
            r'^(college student|student|software engineer|developer|intern|freelancer|'
            r'graduate|undergraduate|full[- ]?stack|front[- ]?end|back[- ]?end|'
            r'data scientist|data analyst|project manager|web developer|'
            r'graphic designer|ui.?ux designer|accountant|teacher|nurse)s?$',
            line_text.strip(), re.IGNORECASE
        ):
            return True
        # Lines containing institutional keywords (universities, schools, companies)
        if re.search(
            r'\b(university|college|school|institute|academy|corporation|company|'
            r'inc\b|ltd\b|llc\b|group|foundation|center|centre|department|faculty|'
            r'hospital|clinic|organization|organisation)\b',
            line_text, re.IGNORECASE
        ):
            return True
        # Degree/certification lines (BSc, MSc, BA, PhD, etc.)
        if re.search(
            r'\b(bsc|msc|ba\b|ma\b|phd|bachelor|master|doctorate|diploma|certificate|'
            r'b\.?s\.?c|m\.?s\.?c|b\.?a\b|m\.?a\b|b\.?eng|m\.?eng|btec|'
            r'engineering|accountancy|management|nursing|medicine|computing|'
            r'expected to graduate|graduated|graduating)\b',
            line_text, re.IGNORECASE
        ):
            return True
        # Lines that look like tech skill lists
        tech_words = {
            'cisco', 'java', 'html', 'python', 'php', 'xampp', 'css', 'javascript',
            'sql', 'power', 'bi', 'jupyter', 'notebook', 'react', 'angular', 'vue',
            'node', 'express', 'django', 'flask', 'typescript', 'mongodb', 'mysql',
            'postgresql', 'docker', 'kubernetes', 'aws', 'azure', 'git', 'linux',
            'windows', 'macos', 'figma', 'photoshop', 'excel', 'word', 'tableau',
            'tensorflow', 'pytorch', 'numpy', 'pandas', 'matplotlib', 'seaborn',
            'spring', 'boot', 'laravel', 'ruby', 'rails', 'swift', 'kotlin',
            'flutter', 'dart', 'rust', 'go', 'scala', 'redis', 'firebase',
            'supabase', 'vercel', 'heroku', 'jira', 'trello', 'agile', 'scrum',
        }
        line_words_lower = [w.lower() for w in line_text.split()]
        if len(line_words_lower) >= 2 and any(w in tech_words for w in line_words_lower):
            if sum(1 for w in line_words_lower if w in tech_words) >= len(line_words_lower) * 0.5:
                return True
        # Lines that are entirely common English words (descriptions, not names)
        if len(line_words_lower) >= 2 and all(w in NOT_NAME_WORDS for w in line_words_lower):
            return True
        return False

    def is_name_like(line_text, allow_single_word=False):
        """Check if a line looks like a person's name.

        A name must:
        - Be 1-5 alphabetic words (2-5 by default)
        - NOT have all words be common English / resume vocabulary
        - Each word starts with a letter (unicode-aware)
        """
        clean = re.sub(r'^[\s\-–—|:?•·]+|[\s\-–—|:?•·]+$', '', line_text).strip()
        if not clean or len(clean) < 2:
            return False, ""
        # Remove pipe separators
        if '|' in clean:
            parts = clean.split('|')
            clean = parts[0].strip()
        words = clean.split()
        min_words = 1 if allow_single_word else 2
        if len(words) < min_words or len(words) > 5:
            return False, ""

        # All words must be alphabetic
        name_word_re = re.compile(r"^[A-Za-z\u00C0-\u024F\u0600-\u06FF][A-Za-z\u00C0-\u024F\u0600-\u06FF'\-\.]*$")
        if not all(name_word_re.match(w) for w in words):
            return False, ""

        # Key filter: if ALL words are common English/resume words, it's NOT a name
        words_lower = [w.lower().rstrip('.') for w in words]
        if all(w in NOT_NAME_WORDS for w in words_lower):
            return False, ""

        # Single common words alone are not names (e.g., "Adaptability", "Leadership")
        if len(words) == 1 and words_lower[0] in NOT_NAME_WORDS:
            return False, ""

        return True, clean

    candidates = []

    # ── Strategy 1: Scan first 25 lines for name-like lines ──
    # Some resumes have descriptions/experience before the name (creative PDF layouts)
    for idx, raw_line in enumerate(lines[:25]):
        line = raw_line.strip()
        if is_section_header(line):
            continue
        if is_noise_line(line):
            continue

        is_name, clean_name = is_name_like(line)
        if is_name:
            position_score = 25 - min(idx, 24)
            word_count = len(clean_name.split())
            length_score = 5 if 2 <= word_count <= 3 else (3 if word_count == 4 else 1)
            # Bonus: ALL CAPS names are very likely the candidate name
            if clean_name.isupper() and word_count >= 2:
                length_score += 3
            candidates.append((clean_name.title(), position_score + length_score))

    # ── Strategy 2: Multi-line names ──
    # e.g., "ADNAN ESAM MOHAMMED" line 0, "AHMED GHALEB" line 1
    # or "ROBIN" line 0, "PADUA" line 1, blank, "VILLAREAL" line 3
    for idx in range(min(len(lines), 25)):
        line1 = lines[idx].strip()
        if not line1 or is_section_header(line1) or is_noise_line(line1):
            continue
        is_name1, clean1 = is_name_like(line1, allow_single_word=True)
        if not is_name1:
            continue

        name_parts = [clean1]
        blanks_seen = 0
        look_ahead = min(idx + 6, len(lines))
        for j in range(idx + 1, look_ahead):
            next_line = lines[j].strip()
            if not next_line:
                blanks_seen += 1
                if blanks_seen > 2:
                    break
                continue
            if is_section_header(next_line) or is_noise_line(next_line):
                break
            is_name_j, clean_j = is_name_like(next_line, allow_single_word=True)
            if is_name_j:
                name_parts.append(clean_j)
                blanks_seen = 0
            else:
                break

        if len(name_parts) >= 2:
            combined = ' '.join(name_parts)
            combined_words = combined.split()
            if 2 <= len(combined_words) <= 5:
                position_score = 15 - min(idx, 14)
                # Bonus for ALL CAPS multi-line
                caps_bonus = 3 if all(p.isupper() for p in name_parts) else 0
                candidates.append((combined.title(), position_score + 8 + caps_bonus))

    # ── Strategy 3: Explicit "Name:" label ──
    name_label_match = re.search(r'(?:name|full name)\s*[:\-–]\s*(.+)', text, re.IGNORECASE)
    if name_label_match:
        label_name = name_label_match.group(1).strip()
        label_name = re.sub(r'\s*[|].*$', '', label_name)
        words = label_name.split()
        if 2 <= len(words) <= 4:
            name_word_re = re.compile(r"^[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F'\-\.]*$")
            if all(name_word_re.match(w) for w in words):
                candidates.append((label_name.title(), 25))

    # ── Strategy 4: NLTK Named Entity Recognition ──
    try:
        usable_lines = []
        for line in lines[:12]:
            stripped = line.strip()
            if stripped and not is_section_header(stripped) and not is_noise_line(stripped):
                usable_lines.append(stripped)
        if usable_lines:
            first_chunk = ' '.join(usable_lines[:6])
            tokens = word_tokenize(first_chunk)
            tagged = nltk.pos_tag(tokens)
            chunks = nltk.ne_chunk(tagged)
            for chunk in chunks:
                if hasattr(chunk, 'label') and chunk.label() == 'PERSON':
                    person_name = ' '.join(c[0] for c in chunk)
                    words = person_name.split()
                    if 2 <= len(words) <= 4:
                        # Verify it's not all common words
                        words_lower = [w.lower() for w in words]
                        if not all(w in NOT_NAME_WORDS for w in words_lower):
                            candidates.append((person_name.title(), 15))
    except Exception:
        pass

    # ── Strategy 5: Spaced-out name lines ──
    # Some PDFs render names as "K I TH  RAI LEY  G." or "M ARAMAG"
    # Scan entire document for spaced-out text that matches the email
    email_for_check = extract_email(text)
    email_local = email_for_check.split('@')[0].lower() if email_for_check else ""

    def collapse_spaced(line_text):
        """Collapse spaced-out text: 'K I TH  RAI LEY  G.' -> 'KITH RAILEY G.'"""
        text_s = line_text.strip()
        tokens = text_s.split()
        single_char_count = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
        if single_char_count >= len(tokens) * 0.3 and single_char_count >= 2:
            groups = re.split(r'\s{2,}', text_s)
            words = []
            for group in groups:
                word = group.replace(' ', '')
                if word:
                    words.append(word)
            if not words:
                words = [text_s.replace(' ', '')]
            return ' '.join(words), True
        return text_s, False

    def try_finalize_spaced_parts(parts):
        """Check if accumulated spaced-out parts form a valid name."""
        if not parts:
            return
        combined = ' '.join(parts)
        words = combined.split()
        if 2 <= len(words) <= 5:
            name_word_re = re.compile(r"^[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F'\-\.]*$")
            words_lower = [w.lower().rstrip('.') for w in words]
            if all(name_word_re.match(w) for w in words):
                if email_local:
                    match_count = sum(1 for w in words_lower if len(w) > 2 and w in email_local)
                    if match_count >= 1:
                        candidates.append((combined.title(), 18))

    spaced_name_parts = []
    for idx in range(len(lines)):
        line = lines[idx].strip()
        if not line or len(line) < 3:
            try_finalize_spaced_parts(spaced_name_parts)
            spaced_name_parts = []
            continue

        collapsed, is_spaced = collapse_spaced(line)
        collapsed_clean = re.sub(r'^[\s\-–—|:?•·]+|[\s\-–—|:?•·]+$', '', collapsed)

        if is_spaced:
            # Check if it's a section header
            collapsed_lower = collapsed_clean.lower()
            collapsed_no_space = re.sub(r'\s+', '', collapsed_lower)
            if collapsed_lower in SECTION_HEADERS or collapsed_no_space in SECTION_HEADERS:
                try_finalize_spaced_parts(spaced_name_parts)
                spaced_name_parts = []
                continue
            spaced_name_parts.append(collapsed_clean)
        else:
            # Non-spaced line adjacent to spaced parts — might be part of name
            # e.g., "M ARAMAG" (not detected as spaced) after "K I TH  RAI LEY  G." (spaced)
            if spaced_name_parts and len(line.split()) <= 2:
                clean_word = re.sub(r'^[\s\-–—|:?•·]+|[\s\-–—|:?•·]+$', '', line)
                # Also try collapsing spaces in this adjacent line
                clean_collapsed = clean_word.replace(' ', '') if len(clean_word.split()) <= 2 else clean_word
                name_word_re = re.compile(r"^[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F'\-\.]*$")
                coll_words = clean_collapsed.split()
                if coll_words and all(name_word_re.match(w) for w in coll_words):
                    # Try with collapsed continuation
                    try_finalize_spaced_parts(spaced_name_parts + [clean_collapsed])
                    try_finalize_spaced_parts(spaced_name_parts)
                    spaced_name_parts = []
                    continue
            try_finalize_spaced_parts(spaced_name_parts)
            spaced_name_parts = []
    # Flush remaining
    try_finalize_spaced_parts(spaced_name_parts)

    # ── Strategy 6: Extract name from email as last resort ──
    # Email like "maramagkithrailey@gmail.com" or "john.doe@gmail.com"
    if not candidates:
        email = extract_email(text)
        if email:
            local_part = email.split('@')[0].lower()
            # Handle dot-separated: john.doe -> John Doe
            if '.' in local_part:
                parts = local_part.replace('_', '.').split('.')
                if 2 <= len(parts) <= 3 and all(p.isalpha() and len(p) >= 2 for p in parts):
                    name_from_email = ' '.join(p.capitalize() for p in parts)
                    candidates.append((name_from_email, 5))

    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    return "Unknown Candidate"


def extract_email(text):
    """Extract email address from resume text.

    Searches the entire document, handles OCR noise, and picks the best match.
    """
    # Pre-clean OCR artifacts around email patterns
    # Handle cases like "&@ robinvillareal? @gmail.com" or "email : user @gmail.com"
    cleaned_text = text
    # Remove stray spaces around @ sign (bounded: an unbounded \s* is quadratic on a long run of spaces)
    cleaned_text = re.sub(r'\s{0,5}@\s{0,5}', '@', cleaned_text)
    # Remove common OCR noise characters adjacent to email
    cleaned_text = re.sub(r'[&?!#|\\]', '', cleaned_text)

    # Find all email addresses
    emails = re.findall(r'[\w.+-]{1,64}@[\w-]{1,63}\.[\w.-]{1,190}', cleaned_text)

    if not emails:
        # Also try the original text in case cleaning was too aggressive
        emails = re.findall(r'[\w.+-]{1,64}@[\w-]{1,63}\.[\w.-]{1,190}', text)

    if not emails:
        return ""

    # Clean up any remaining noise from found emails
    cleaned_emails = []
    for email in emails:
        # Remove leading/trailing dots or hyphens
        email = email.strip('.-')
        # Validate basic structure
        if re.match(r'^[\w.+-]{1,64}@[\w-]{1,63}\.\w{2,}', email):
            cleaned_emails.append(email)

    if not cleaned_emails:
        return emails[0] if emails else ""

    if len(cleaned_emails) == 1:
        return cleaned_emails[0]

    # If multiple emails, prefer personal email providers
    personal_domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com',
                        'icloud.com', 'mail.com', 'protonmail.com', 'live.com',
                        'aol.com', 'zoho.com', 'ymail.com', 'me.com']

    for email in cleaned_emails:
        domain = email.split('@')[1].lower()
        if domain in personal_domains:
            return email

    return cleaned_emails[0]


def extract_phone(text):
    """Extract phone number from resume text.

    Handles international formats, parentheses, separators, and unicode prefixes.
    Searches the entire document.
    """
    # Clean common unicode symbols that PDFs insert (phone icons, etc.)
    cleaned = re.sub(r'[?\uf0e0\uf095\u260e\u2706\U0001f4de\U0001f4f1\U0001f4f2\\]', '', text)
    # Normalize various dash types to standard hyphen
    cleaned = re.sub(r'[–—−]', '-', cleaned)

    # Comprehensive phone patterns, ordered from most specific to least
    patterns = [
        # International with parens: (+971) 544758408 or (+971) 54-475-8408
        r'\(\+?\d{1,4}\)[\s\-.]?\d[\d\s\-.]{5,12}\d',
        # International: +971 52 161 1925 or +971-52-161-1925 or +971521611925
        r'\+\d{1,4}[\s\-.]?\d[\d\s\-.]{5,14}\d',
        # Standard with leading zero: 054-358-2924 or 09369364322
        r'\b0\d[\d\s\-.]{6,13}\d\b',
        # Generic: 3+ digits, separators, 7+ total digits
        r'\b\d{3,4}[\s\-.]?\d{3,4}[\s\-.]?\d{3,4}\b',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, cleaned)
        for match in matches:
            digits = re.sub(r'[^\d]', '', match)
            if 7 <= len(digits) <= 15:
                return match.strip()

    return ""


def extract_skills(text):
    """Extract skills from resume text using NLP and keyword matching.

    Uses context-aware matching to avoid false positives:
    - 'C#' won't match 'R' or 'C'
    - Short skills (R, Go, C) require stronger context
    - Skills found in the SKILLS section get priority
    """
    text_lower = text.lower()

    found_skills = []
    seen = set()

    # Skills that need special regex patterns to avoid false positives
    # These are too short or ambiguous for simple substring matching
    SPECIAL_PATTERNS = {
        'c#':   r'\bc\s*#',                    # "C#" or "C #"
        'c++':  r'\bc\s*\+\s*\+',              # "C++" or "C + +"
        'r':    r'(?<![a-z])\br\b(?:\s+(?:programming|language|studio|markdown|shiny)|\s*[,;|/])',
        'go':   r'(?<![a-z])\bgo(?:lang)?\b(?:\s*[,;|/]|\s+(?:programming|language))',
        'c':    r'(?<![a-z#\+])\bc\b(?:\s+(?:programming|language)|\s*[,;|/])',
        'ui':   r'\bui\b(?:\s*[/]\s*ux|\s+design)',
        'ux':   r'\bux\b(?:\s*[/]\s*ui|\s+design|\s+research)',
    }

    # Skills that are safe with word-boundary matching (not too ambiguous)
    WORD_BOUNDARY_SKILLS = {
        'lua', 'dart', 'rust', 'java', 'swift', 'kotlin', 'scala', 'perl',
        'ruby', 'php', 'bash', 'sql', 'html', 'css', 'sass', 'vba',
        'haskell', 'elixir', 'clojure', 'groovy', 'matlab',
    }

    for category, skills in SKILLS_DB.items():
        for skill in skills:
            if skill in seen:
                continue

            matched = False

            if skill in SPECIAL_PATTERNS:
                # Use special context-aware pattern
                pattern = SPECIAL_PATTERNS[skill]
                if re.search(pattern, text_lower):
                    matched = True
            elif skill in WORD_BOUNDARY_SKILLS:
                # Use word-boundary matching
                pattern = r'\b' + re.escape(skill) + r'\b'
                if re.search(pattern, text_lower):
                    matched = True
            else:
                # Standard substring matching for longer/unambiguous skills
                if skill in text_lower:
                    matched = True

            if matched and skill not in seen:
                found_skills.append((skill.title(), category))
                seen.add(skill)

    return found_skills


def extract_education(text):
    """Extract education information from resume text.

    Returns a list of dicts with 'institution' and 'degree' keys.
    Only includes lines that are actual institution names and degree titles,
    not bullet points, coursework descriptions, or other noise.
    """
    education = []
    lines = text.split('\n')
    seen_institutions = set()

    # Keywords that identify institution lines
    INSTITUTION_KEYWORDS = [
        'university', 'college', 'institute', 'school', 'academy',
        'polytechnic', 'conservatory', 'seminary',
    ]

    # Splits a line into logical segments on '|', a run of 2+ spaces (shows
    # up where a PDF's tab/column layout collapses on extraction), or a
    # dash-style separator like "Degree — Institution" (an em/en dash with
    # single spaces around it survives OCR's word-gap detection even when a
    # wider run of literal space characters gets normalized down to one).
    # A plain hyphen with a space on each side ("BSc Computer Science - Example University") is the most
    # common ASCII form of that dash, but a hyphen between two years ("2021 - 2025") is a date range, not a
    # separator, so only a hyphen that has no digit right next to it splits the line.
    SEGMENT_SPLIT_RE = re.compile(r'\s*\|\s*|\s{2,}|\s+[–—]\s+|(?<!\d)\s+-\s+(?!\d)')

    # Patterns to SKIP — these are NOT institution/degree lines
    SKIP_PATTERNS = re.compile(
        r'(^\s*[\•\-\*\–\◦\▪\uf0d8\uf0b7\®]'  # bullet points
        r'|^relevant\s+coursework'               # coursework listings
        r'|^projects?\s*:'                        # project listings
        r'|^achievement'                          # achievement lines
        r'|^gpa|^grade'                           # GPA lines
        r'|^leader\b|^led\b|^managed\b'          # activity descriptions
        r'|^designed\b|^developed\b|^built\b'     # project descriptions
        r'|^collaborated\b|^implemented\b'        # work descriptions
        r'|^presented\b|^conducted\b'             # activity descriptions
        r'|@|\.com|\.org'                         # email/URL lines
        r'|^\d{4}\s*$'                            # just a year
        r')',
        re.IGNORECASE
    )

    def is_institution_line(line_text):
        """Check if a line is an institution name, not a sentence that mentions one.

        Handles pipe-separated formats like:
        'University of Manchester | BEng (Hons) Software Engineering | Location'
        """
        stripped = line_text.strip()
        line_lower = stripped.lower()

        # Must contain an institution keyword
        if not any(kw in line_lower for kw in INSTITUTION_KEYWORDS):
            return False

        # For pipe- or column-separated lines, check just the institution segment.
        # Runs of 2+ spaces show up where a PDF's tab/column layout collapses
        # during text extraction (e.g. "BEng ... Software Engineering   University of X"),
        # so treat those as segment breaks too, not just '|'.
        check_text = stripped
        segments = [s for s in SEGMENT_SPLIT_RE.split(stripped) if s]
        if len(segments) > 1:
            # Find the segment that contains the institution keyword
            for seg in segments:
                if any(kw in seg.lower() for kw in INSTITUTION_KEYWORDS):
                    check_text = seg
                    break

        check_lower = check_text.lower()
        word_count = len(check_text.split())

        # If the institution segment is very long (>12 words), it's likely a sentence
        if word_count > 12:
            return False

        # If line starts with common sentence starters, it's a description
        if re.match(r'^(a |an |the |i |my |our |we |to |in |at |is |am |was |were |has |had |'
                     r'motivated|detail|science|experienced|seeking|looking|'
                     r'participated|maintained|presented|designed|developed)',
                    check_lower):
            return False

        # Lines with too many lowercase words in sequence are sentences
        words = check_text.split()
        lowercase_words = sum(1 for w in words if w[0].islower() and w not in
                             ('of', 'the', 'and', 'in', 'for', 'at', 'de', 'la', 'al', 'el'))
        if word_count >= 5 and lowercase_words > word_count * 0.5:
            return False

        # Filter out lines that are clearly job titles, roles, or degree labels
        # "College Student", "High School Graduate" are NOT institution names
        if re.search(r'\b(student|engineer|developer|designer|manager|analyst|staff|assistant|intern|graduate|diploma|receptionist)\b',
                    check_lower):
            if word_count <= 3:
                return False

        # Filter out standalone degree labels like "HIGH SCHOOL GRADUATE", "Bachelor of Science"
        degree_only_patterns = [
            r'^high\s+school\s+graduate',
            r'^(bachelor|master|doctor|diploma|associate|btec)',
            r'^(bsc|msc|phd|mba|bca|mca)\b',
        ]
        for dp in degree_only_patterns:
            if re.match(dp, check_lower):
                return False

        return True

    # First pass: find all institution lines
    institution_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) < 5:
            continue
        if SKIP_PATTERNS.search(stripped):
            continue
        if not is_institution_line(stripped):
            continue

        # Clean the institution name
        # For pipe- or column-separated lines like "University of X | BEng Engineering | Location"
        # extract just the institution segment
        segments = [s for s in SEGMENT_SPLIT_RE.split(stripped) if s]
        if len(segments) > 1:
            inst_segment = None
            for seg in segments:
                if any(kw in seg.lower() for kw in INSTITUTION_KEYWORDS):
                    inst_segment = seg
                    break
            clean_inst = inst_segment or segments[0]
        else:
            clean_inst = stripped

        # Remove trailing dates
        clean_inst = re.sub(r'\s*[|,]\s*\d{4}\s*[-–]\s*\d{0,4}\s*$', '', clean_inst)
        clean_inst = re.sub(r'\s*\d{4}\s*[-–]\s*(present|\d{4})\s*$', '', clean_inst, flags=re.IGNORECASE)
        clean_inst = clean_inst.strip().rstrip('|,;: ')
        if clean_inst and clean_inst.lower() not in seen_institutions:
            institution_lines.append((i, clean_inst))
            seen_institutions.add(clean_inst.lower())

    # Degree keywords that need word-boundary matching (short/ambiguous)
    SHORT_DEGREE_KW = {'ba', 'be', 'ma', 'md', 'bsc', 'msc', 'beng', 'meng', 'hnd', 'hnc'}

    def line_has_degree(line_text):
        """Check if a line contains a degree keyword (word-boundary safe)."""
        lower = line_text.lower()
        for deg_kw in DEGREE_KEYWORDS:
            if deg_kw in SHORT_DEGREE_KW:
                # Use word-boundary match for short keywords
                if re.search(r'\b' + re.escape(deg_kw) + r'\b', lower):
                    return True
            else:
                if deg_kw in lower:
                    return True
        return False

    def is_degree_line(line_text):
        """Check if a line is a degree description, not a random sentence."""
        stripped = line_text.strip()
        if not stripped or len(stripped) < 5:
            return False
        if SKIP_PATTERNS.search(stripped):
            return False
        if not line_has_degree(stripped):
            return False
        # Must not be a long descriptive sentence
        if len(stripped.split()) > 15:
            return False
        # Must not start with sentence starters
        lower = stripped.lower()
        if re.match(r'^(a |an |the |i |my |our |we |to |motivated|detail|experienced|seeking|looking)',
                    lower):
            return False
        return True

    # Build index of all institution line positions for proximity checking
    inst_line_indices = set(idx for idx, _ in institution_lines)

    def is_closer_to_other_institution(degree_line_idx, current_inst_idx):
        """Check if a degree line is closer to a different institution than the current one."""
        current_dist = abs(degree_line_idx - current_inst_idx)
        for other_idx in inst_line_indices:
            if other_idx == current_inst_idx:
                continue
            if abs(degree_line_idx - other_idx) < current_dist:
                return True
        return False

    # Second pass: for each institution, find the associated degree
    for inst_idx, institution in institution_lines:
        degree = ""
        # Look within 2 lines above and 3 below for a degree keyword
        search_range = list(range(max(0, inst_idx - 2), min(len(lines), inst_idx + 4)))
        for j in search_range:
            candidate = lines[j].strip()
            if not is_degree_line(candidate):
                continue
            # Don't use the institution line itself as the degree
            if candidate.strip().lower() == institution.lower():
                continue
            # Skip if it's another institution
            if is_institution_line(candidate):
                continue
            # Skip if this degree line is closer to a different institution
            if is_closer_to_other_institution(j, inst_idx):
                continue
            # Clean the degree text
            clean_degree = re.sub(r'\s*[|,]\s*\d{4}\s*[-–]\s*\d{0,4}\s*$', '', candidate)
            clean_degree = re.sub(r'\s*\d{4}\s*[-–]\s*(present|\d{4})\s*$', '', clean_degree, flags=re.IGNORECASE)
            clean_degree = clean_degree.strip().rstrip('|,;: ')
            if clean_degree:
                degree = clean_degree
                break

        # Also check if the degree is embedded in the original line (pipe- or
        # column-separated), e.g. "University of Manchester | BEng (Hons) Software
        # Engineering | Location" or "BEng (Hons) Software Engineering   University of X"
        if not degree:
            original_line = lines[inst_idx].strip()
            segments = [s for s in SEGMENT_SPLIT_RE.split(original_line) if s]
            if len(segments) > 1:
                for seg in segments:
                    # Skip the institution segment itself and location segments
                    if seg.lower() == institution.lower():
                        continue
                    if line_has_degree(seg):
                        degree = seg
                        break

        education.append({
            'institution': institution,
            'degree': degree,
        })

    # Third pass: find degree lines that weren't near any institution
    # (some resumes list degree without mentioning an institution keyword)
    found_degree_lines = set()
    for entry in education:
        if entry['degree']:
            for i, line in enumerate(lines):
                if line.strip() == entry['degree']:
                    found_degree_lines.add(i)

    for i, line in enumerate(lines):
        if i in found_degree_lines:
            continue
        stripped = line.strip()
        if not is_degree_line(stripped):
            continue
        line_lower = stripped.lower()
        # Only standalone degree lines (not inside institution lines already found)
        if any(kw in line_lower for kw in INSTITUTION_KEYWORDS):
            continue
        # Only add if it's clearly a degree line (has specific format)
        if re.search(r'\b(bachelor|master|doctor|diploma|associate|bsc|msc|phd|b\.?eng|m\.?eng|btec)\b', line_lower):
            clean_degree = re.sub(r'\s*[|,]\s*\d{4}\s*[-–]\s*\d{0,4}\s*$', '', stripped)
            clean_degree = clean_degree.strip().rstrip('|,;: ')
            # Check nearby lines for institution
            nearby_inst = ""
            for j in range(max(0, i - 2), min(len(lines), i + 3)):
                if j != i:
                    cand = lines[j].strip()
                    if is_institution_line(cand):
                        nearby_inst = re.sub(r'\s*[|,]\s*\d{4}\s*[-–]\s*\d{0,4}\s*$', '', cand)
                        nearby_inst = nearby_inst.strip().rstrip('|,;: ')
                        break
            if nearby_inst and nearby_inst.lower() not in seen_institutions:
                education.append({
                    'institution': nearby_inst,
                    'degree': clean_degree,
                })
                seen_institutions.add(nearby_inst.lower())

    def tidy(value):
        """Drop dates left on an institution or degree: "(2016 - 2019)", ", 2018", ", 2015 - 2019"."""
        value = re.sub(r'\(\s*(?:19|20)\d{2}\s*(?:[-–—]|to)\s*(?:(?:19|20)\d{2}|present|current)\s*\)', '',
                       value, flags=re.IGNORECASE)
        value = re.sub(r'\s*[|,]?\s*(?:19|20)\d{2}\s*(?:[-–—]\s*(?:(?:19|20)\d{2}|present|current))?\s*$', '',
                       value, flags=re.IGNORECASE)
        return value.strip().rstrip('|,;:- ')

    for entry in education:
        entry['institution'] = tidy(entry['institution']) or entry['institution']
        entry['degree'] = tidy(entry['degree']) if entry['degree'] else ''

    return education


_EXPERIENCE_HEADINGS = {
    'experience', 'work experience', 'professional experience', 'employment history', 'work history',
    'employment', 'relevant experience', 'career history', 'professional background', 'internships',
    'internship experience',
}
_OTHER_HEADINGS = {
    'education', 'skills', 'technical skills', 'key skills', 'core skills', 'projects', 'personal projects',
    'academic projects', 'certifications', 'certificates', 'awards', 'languages', 'interests', 'references',
    'summary', 'professional summary', 'profile', 'objective', 'career objective', 'publications', 'volunteer',
    'volunteering', 'achievements', 'courses', 'training', 'education and certifications',
    'certifications and training', 'hobbies', 'activities',
}


def _heading_of(line):
    """The lowercase heading a line stands for ("Work Experience:" -> "work experience"), or ''."""
    stripped = line.strip()
    if not stripped or len(stripped) > 40 or '@' in stripped or re.search(r'\d', stripped):
        return ''
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z& ]', '', stripped.lower())).strip().replace('&', 'and')


def _experience_section(lines):
    """The lines under the Experience heading, up to the next section heading, or None if there is none."""
    start = None
    for i, line in enumerate(lines):
        if _heading_of(line) in _EXPERIENCE_HEADINGS:
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if _heading_of(lines[j]) in _OTHER_HEADINGS:
            end = j
            break
    section = lines[start:end]
    return section if any(l.strip() for l in section) else None


_MONTHS = {m: i + 1 for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}
_MONTH_RE = (r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|'
             r'sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?')
_DATE_RANGE = re.compile(
    r'(?:(?P<m1>' + _MONTH_RE + r')\s+|(?P<n1>\d{1,2})/)?(?P<y1>(?:19|20)\d{2})\s*(?:-|–|—|to)\s*'
    r'(?:(?:(?P<m2>' + _MONTH_RE + r')\s+|(?P<n2>\d{1,2})/)?(?P<y2>(?:19|20)\d{2})|(?P<now>present|current|now|today|ongoing))',
    re.IGNORECASE)


def _month_number(name, number, default):
    if name:
        return _MONTHS.get(name.lower()[:3], default)
    if number and 1 <= int(number) <= 12:
        return int(number)
    return default


def estimate_experience_years(text, today=None):
    """Total years covered by the dated jobs in the Experience section (overlaps counted once), or None when no
    dates can be read. Lines about education are ignored so a degree's years never count as work."""
    import datetime
    today = today or datetime.date.today()
    lines = text.split('\n')
    section = _experience_section(lines)
    if section is None:
        section = [l for l in lines if not re.search(
            r'universit|college|school|bachelor|master|degree|diploma|b\.?sc|m\.?sc|ph\.?d', l, re.I)]
    spans = []
    for line in section:
        for m in _DATE_RANGE.finditer(line):
            start = int(m.group('y1')) * 12 + _month_number(m.group('m1'), m.group('n1'), 6) - 1
            if m.group('now'):
                end = today.year * 12 + today.month - 1
            else:
                end = int(m.group('y2')) * 12 + _month_number(m.group('m2'), m.group('n2'), 6) - 1
            end = min(end, today.year * 12 + today.month - 1)
            if end > start:
                spans.append((start, end))
    if not spans:
        return None
    spans.sort()
    total, cur_start, cur_end = 0, spans[0][0], spans[0][1]
    for s, e in spans[1:]:
        if s <= cur_end:
            cur_end = max(cur_end, e)
        else:
            total += cur_end - cur_start
            cur_start, cur_end = s, e
    total += cur_end - cur_start
    return round(min(total / 12.0, 50.0), 1)


def _split_title_company(line):
    """"Software Engineering Intern - Northwind Digital, Dubai (Jun 2025 - Dec 2025)" -> (title, company)."""
    clean = re.sub(r'\([^)]*\d{4}[^)]*\)', '', line)
    clean = _DATE_RANGE.sub('', clean).strip(' ,|-–—')
    parts = re.split(r'\s+[-–—|@]\s+|\s+at\s+', clean, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        first, second = parts[0].strip(' ,'), parts[1].strip(' ,')
        first_is_title = any(t in first.lower() for t in JOB_TITLES)
        second_is_title = any(t in second.lower() for t in JOB_TITLES)
        if first_is_title and not second_is_title:
            return first, second
        if second_is_title and not first_is_title:
            return second, first
    # "Junior Developer, Acme Ltd" (title, company)
    comma = [p.strip() for p in clean.split(',', 1)]
    if len(comma) == 2 and comma[1] and any(t in comma[0].lower() for t in JOB_TITLES) \
            and not any(t in comma[1].lower() for t in JOB_TITLES):
        return comma[0], comma[1]
    return clean or line.strip(), ''


def extract_experience(text):
    """Extract work experience from resume text.

    When the resume has an Experience section, only that section is read, so a job-title word in the summary,
    the contact line, a project or the education block is not counted as a job. Without such a section the
    whole text is scanned, as before."""
    all_lines = text.split('\n')
    scoped = _experience_section(all_lines)
    result = _extract_experience_from(scoped, True) if scoped else []
    if result:
        return result
    return _extract_experience_from(all_lines, False)


def _extract_experience_from(lines, scoped):
    experience = []

    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        # a bullet, a line with an email address or a long sentence is not a job title line
        if line_lower.startswith(('•', '-', '*', '–')) or '@' in line_lower or len(line_lower) > 120:
            continue
        for title in JOB_TITLES:
            if title in line_lower:
                job_title, company = _split_title_company(line)
                description = ""
                if not company:
                    for j in range(max(0, i - 1), min(len(lines), i + 3)):
                        if j != i:
                            candidate = lines[j].strip()
                            if candidate and not any(t in candidate.lower() for t in JOB_TITLES):
                                if 3 < len(candidate) < 100 and not candidate.startswith(('•', '-', '*', '–')):
                                    company = candidate
                                    break
                desc_lines = []
                for j in range(i + 1, min(len(lines), i + 5)):
                    if lines[j].strip().startswith(('•', '-', '*', '–')):
                        desc_lines.append(lines[j].strip())
                description = ' '.join(desc_lines)
                experience.append((job_title, company, description))
                break

    return experience
