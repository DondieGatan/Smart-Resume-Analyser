import re
import os
import fitz  # PyMuPDF
import nltk
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.corpus import stopwords

# Download required NLTK data (only if not already present)
def _ensure_nltk_data():
    packages = ['punkt', 'punkt_tab', 'averaged_perceptron_tagger',
                'averaged_perceptron_tagger_eng', 'stopwords',
                'maxent_ne_chunker', 'maxent_ne_chunker_tab', 'words']
    for pkg in packages:
        try:
            nltk.data.find(f'tokenizers/{pkg}' if 'punkt' in pkg else
                          f'taggers/{pkg}' if 'tagger' in pkg else
                          f'chunkers/{pkg}' if 'chunker' in pkg else
                          f'corpora/{pkg}')
        except LookupError:
            nltk.download(pkg, quiet=True)

_ensure_nltk_data()

from analyzer_data import (  # noqa: E402,F401  (the tables moved to analyzer_data.py; re-exported here)
    SKILLS_DB, DEGREE_KEYWORDS, JOB_TITLES, FIELD_RECOMMENDATIONS)
from text_extraction import (  # noqa: E402,F401  (moved to text_extraction.py; re-exported here)
    IMAGE_EXTENSIONS, extract_text, extract_text_from_pdf, extract_text_from_image, extract_text_from_docx,
    _has_tesseract)
from resume_parser import (  # noqa: E402,F401  (moved to resume_parser.py; re-exported here)
    extract_name, extract_email, extract_phone, extract_skills, extract_education, extract_experience,
    estimate_experience_years)


def calculate_scores(text, skills, education, experience):
    """Calculate resume scores with detailed explanations for each dimension."""
    scores = {}
    explanations = {}

    # ===== Skills Score (0-100) =====
    skill_count = len(skills)
    categories = set(cat for _, cat in skills)
    skills_reasons = []
    skills_suggestions = []

    if skill_count >= 15:
        scores['skills'] = 100
        skills_reasons.append(f"Excellent: {skill_count} skills detected across your resume.")
    elif skill_count >= 10:
        scores['skills'] = 85
        skills_reasons.append(f"Very good: {skill_count} skills found. Adding {15 - skill_count} more would reach a perfect score.")
        skills_suggestions.append("List additional tools, frameworks, or certifications you have experience with.")
    elif skill_count >= 6:
        scores['skills'] = 70
        skills_reasons.append(f"Good: {skill_count} skills detected, but there is room for improvement.")
        skills_suggestions.append("Add more specific technical skills — e.g., programming languages, frameworks, or tools you use regularly.")
    elif skill_count >= 3:
        scores['skills'] = 50
        skills_reasons.append(f"Below average: only {skill_count} skills were found.")
        skills_suggestions.append("Create a dedicated 'Skills' section and list all relevant technical and soft skills.")
        skills_suggestions.append("Include programming languages, frameworks, databases, and tools you are proficient in.")
    else:
        scores['skills'] = max(20, skill_count * 15)
        skills_reasons.append(f"Low: only {skill_count} skill(s) detected. Your resume may be missing a skills section.")
        skills_suggestions.append("Add a clear 'Skills' or 'Technical Skills' section at the top of your resume.")
        skills_suggestions.append("Even non-technical roles benefit from listing tools (Excel, SQL, Tableau, etc.).")

    if len(categories) >= 4:
        scores['skills'] = min(100, scores['skills'] + 10)
        skills_reasons.append(f"Bonus: skills span {len(categories)} categories, showing a well-rounded profile.")
    elif len(categories) < 2 and skill_count > 0:
        skills_suggestions.append("Diversify your skills — include soft skills (leadership, communication) alongside technical ones.")

    explanations['skills'] = {'reasons': skills_reasons, 'suggestions': skills_suggestions}

    # ===== Education Score (0-100) =====
    edu_reasons = []
    edu_suggestions = []
    text_lower = text.lower()

    if not education:
        scores['education'] = 20
        edu_reasons.append("No education entries were detected in your resume.")
        edu_suggestions.append("Add an 'Education' section with your degree, institution name, and graduation year.")
        edu_suggestions.append("If you have certifications (AWS, Google, Coursera, etc.), list them too.")
    else:
        if any(kw in text_lower for kw in ['ph.d', 'phd', 'doctorate']):
            scores['education'] = 100
            edu_reasons.append("Doctorate/PhD detected — highest academic qualification.")
        elif any(kw in text_lower for kw in ['master', 'm.sc', 'msc', 'm.tech', 'mtech', 'm.eng', 'meng', 'm.com', 'mba', 'mca']):
            scores['education'] = 85
            edu_reasons.append("Master's degree detected — strong academic background.")
            edu_suggestions.append("Adding relevant certifications or publications can push this to a perfect score.")
        elif any(kw in text_lower for kw in ['bachelor', 'b.sc', 'bsc', 'b.tech', 'btech', 'b.e.', 'b.eng', 'beng', 'b.com', 'bca']):
            scores['education'] = 70
            edu_reasons.append("Bachelor's degree detected.")
            edu_suggestions.append("Consider pursuing certifications or a master's degree to strengthen this section.")
            edu_suggestions.append("Include relevant coursework, GPA (if strong), or academic projects.")
        elif any(kw in text_lower for kw in ['diploma', 'associate', 'btec', 'hnd', 'hnc']):
            scores['education'] = 50
            edu_reasons.append("Diploma or associate degree detected.")
            edu_suggestions.append("Highlight any additional certifications, bootcamps, or online courses you've completed.")
        else:
            scores['education'] = 40
            edu_reasons.append("Education found but degree level could not be clearly determined.")
            edu_suggestions.append("Clearly state your degree type (e.g., 'Bachelor of Science in Computer Science').")

        # Check for institution names
        has_institution = any(entry.get('institution') for entry in education)
        if not has_institution:
            edu_suggestions.append("Include the name of your university or institution for credibility.")

    explanations['education'] = {'reasons': edu_reasons, 'suggestions': edu_suggestions}

    # ===== Experience Score (0-100) =====
    exp_count = len(experience)
    exp_reasons = []
    exp_suggestions = []

    if exp_count >= 5:
        scores['experience'] = 100
        exp_reasons.append(f"Excellent: {exp_count} work experience entries found.")
    elif exp_count >= 3:
        scores['experience'] = 80
        exp_reasons.append(f"Good: {exp_count} experience entries detected.")
        exp_suggestions.append("Adding more roles, freelance work, or internships would strengthen this section.")
    elif exp_count >= 1:
        scores['experience'] = 60
        exp_reasons.append(f"Fair: {exp_count} experience {'entry' if exp_count == 1 else 'entries'} found.")
        exp_suggestions.append("Include internships, freelance projects, open-source contributions, or volunteer work.")
        exp_suggestions.append("Add bullet points with specific achievements and metrics (e.g., 'Increased performance by 30%').")
    else:
        scores['experience'] = 20
        exp_reasons.append("No work experience entries were detected.")
        exp_suggestions.append("Add a 'Work Experience' or 'Professional Experience' section with job titles and company names.")
        exp_suggestions.append("Even academic projects or personal projects can be listed under 'Projects' if you lack work experience.")

    # Dated roles: the time they cover says more than how many titles were found
    dated_years = estimate_experience_years(text)
    if dated_years is not None:
        tier = 100 if dated_years >= 5 else 85 if dated_years >= 3 else 70 if dated_years >= 1 else 0
        if tier > scores['experience']:
            scores['experience'] = tier
            exp_reasons.append(f"About {dated_years:g} years of dated work experience.")
        elif dated_years >= 0.5:
            exp_reasons.append(f"About {dated_years:g} years of dated work experience.")

    # Check for years of experience mentions
    year_match = re.findall(r'(\d+)\+?\s*years?', text, re.IGNORECASE)
    if year_match:
        max_years = max(int(y) for y in year_match)
        if max_years >= 10:
            scores['experience'] = min(100, scores['experience'] + 20)
            exp_reasons.append(f"Bonus: {max_years}+ years of experience mentioned.")
        elif max_years >= 5:
            scores['experience'] = min(100, scores['experience'] + 10)
            exp_reasons.append(f"Bonus: {max_years}+ years of experience mentioned.")

    # Check for bullet points in experience
    bullet_count = sum(1 for line in text.split('\n') if line.strip().startswith(('•', '-', '*', '–')))
    if bullet_count < 3 and exp_count > 0:
        exp_suggestions.append("Use bullet points to describe your responsibilities and achievements for each role.")

    explanations['experience'] = {'reasons': exp_reasons, 'suggestions': exp_suggestions}

    # ===== Formatting Score (0-100) =====
    formatting_score = 50
    fmt_reasons = []
    fmt_suggestions = []
    word_count = len(text.split())
    sentences = sent_tokenize(text)

    # Length check
    if 300 <= word_count <= 1500:
        formatting_score += 15
        fmt_reasons.append(f"Good length: {word_count} words (ideal range is 300-1500).")
    elif 200 <= word_count <= 2000:
        formatting_score += 8
        fmt_reasons.append(f"Acceptable length: {word_count} words.")
        if word_count < 300:
            fmt_suggestions.append(f"Your resume is a bit short ({word_count} words). Aim for at least 300 words with detailed descriptions.")
        else:
            fmt_suggestions.append(f"Your resume is slightly long ({word_count} words). Try to keep it under 1500 words (1-2 pages).")
    else:
        if word_count < 200:
            fmt_reasons.append(f"Very short: only {word_count} words detected.")
            fmt_suggestions.append("Your resume needs more content. Add detailed descriptions of your skills, experience, and projects.")
        else:
            fmt_reasons.append(f"Very long: {word_count} words detected.")
            fmt_suggestions.append("Trim your resume to 1-2 pages. Focus on the most relevant and recent experience.")

    # Section headers
    section_headers = ['education', 'experience', 'skills', 'projects',
                       'summary', 'objective', 'certifications', 'achievements']
    found_sections = [s for s in section_headers if s in text_lower]
    missing_sections = [s for s in ['education', 'experience', 'skills'] if s not in text_lower]
    formatting_score += min(20, len(found_sections) * 5)

    if found_sections:
        fmt_reasons.append(f"Sections found: {', '.join(s.title() for s in found_sections)}.")
    if missing_sections:
        fmt_suggestions.append(f"Missing key sections: {', '.join(s.title() for s in missing_sections)}. Add clear section headers.")

    # Bullet points
    if bullet_count >= 5:
        formatting_score += 10
        fmt_reasons.append(f"Good use of bullet points ({bullet_count} found).")
    elif bullet_count >= 2:
        formatting_score += 5
        fmt_reasons.append(f"Some bullet points found ({bullet_count}).")
        fmt_suggestions.append("Use more bullet points to list responsibilities and achievements for better readability.")
    else:
        fmt_suggestions.append("Add bullet points to your experience section. Recruiters scan resumes quickly — bullets help.")

    # Contact info
    has_email = bool(extract_email(text))
    has_phone = bool(extract_phone(text))
    if has_email:
        formatting_score += 5
    else:
        fmt_suggestions.append("Include your email address so recruiters can contact you.")
    if not has_phone:
        fmt_suggestions.append("Consider adding a phone number for easier contact.")

    if has_email and has_phone:
        fmt_reasons.append("Contact information (email and phone) is present.")
    elif has_email:
        fmt_reasons.append("Email found, but no phone number detected.")

    scores['formatting'] = min(100, formatting_score)
    explanations['formatting'] = {'reasons': fmt_reasons, 'suggestions': fmt_suggestions}

    # ===== Overall Score =====
    scores['overall'] = round(
        scores['skills'] * 0.30 +
        scores['education'] * 0.20 +
        scores['experience'] * 0.30 +
        scores['formatting'] * 0.20
    )

    return scores, explanations


def recommend_field(skills, experience, text):
    """Recommend career fields based on actual skills, experience, and education.

    Scoring approach:
    - Core skills: 4 points each (strongest signal from detected skills)
    - Supporting skills: 1 point each (only if there's at least 1 core skill match)
    - Experience keywords: 5 points each (matched against job titles only, not full text)
    - Education context: 3 points (if degree/education text mentions the field)

    Returns a list of (field_name, confidence, matched_details) sorted by confidence.
    """
    if not skills and not experience:
        return [('General', 0, 'No skills or experience detected to determine a specific field.')]

    skill_names = set(s.lower() for s, _ in skills)

    # Build experience text from actual job titles only (not descriptions)
    # Job titles are the first element of experience tuples
    exp_titles = ' | '.join(title for title, _, _ in experience).lower()

    # Extract education-related text for field context
    edu_keywords_in_text = set()
    text_lower = text.lower()
    # Look specifically in lines near education section headers
    lines = text.split('\n')
    in_edu_section = False
    edu_text = ""
    for line in lines:
        stripped = line.strip().lower()
        if stripped in ('education', 'academic background', 'qualifications'):
            in_edu_section = True
            continue
        if in_edu_section:
            if stripped in ('experience', 'skills', 'projects', 'certifications',
                           'work experience', 'professional experience', 'references'):
                in_edu_section = False
                continue
            edu_text += " " + stripped

    field_results = []

    for field, config in FIELD_RECOMMENDATIONS.items():
        score = 0
        matched_core = []
        matched_supporting = []
        matched_experience = []
        matched_education = []

        # Core skills — worth 4 points each (strongest signal)
        for kw in config['core']:
            if kw in skill_names:
                score += 4
                matched_core.append(kw.title())

        # Supporting skills — worth 1 point each
        # BUT only count if there's at least 1 core skill or experience match
        supporting_matches = []
        for kw in config['supporting']:
            if kw in skill_names:
                supporting_matches.append(kw.title())

        # Experience keywords — worth 5 points each
        # Match against job titles and the broader text, but use word boundaries
        # to avoid false matches (e.g., "engineer" in a sentence about something else)
        for kw in config['experience_keywords']:
            # Match in job title lines (high confidence)
            if kw in exp_titles:
                score += 5
                matched_experience.append(kw.title())
            else:
                # Match in full text but require it to be near a job context
                # Use word-boundary matching for multi-word phrases
                pattern = r'\b' + re.escape(kw) + r'\b'
                if re.search(pattern, text_lower):
                    score += 3
                    matched_experience.append(kw.title())

        # Education context — worth 3 points
        # Check if the education section mentions this field
        field_edu_keywords = {
            'Web Development': ['web development', 'web design', 'internet technology'],
            'Data Science & AI': ['data science', 'artificial intelligence', 'machine learning',
                                  'statistics', 'data analytics'],
            'Software Engineering': ['software engineering', 'computer science', 'computing',
                                     'information technology', 'software development'],
            'Mechanical Engineering': ['mechanical engineering', 'mechatronics',
                                      'manufacturing engineering', 'engineering technology'],
            'Electrical & Electronics Engineering': ['electrical engineering', 'electronics',
                                                      'electronic engineering', 'power engineering',
                                                      'telecommunications engineering'],
            'Civil Engineering': ['civil engineering', 'structural engineering',
                                   'construction management', 'geotechnical engineering',
                                   'environmental engineering'],
            'Aerospace & Aviation': ['aerospace engineering', 'aerospace', 'aviation',
                                      'aircraft maintenance', 'aeronautical engineering'],
            'Chemical & Industrial Engineering': ['chemical engineering', 'industrial engineering',
                                                    'process engineering', 'petroleum engineering'],
            'Accounting & Finance': ['accountancy', 'accounting', 'finance', 'business administration',
                                     'business management', 'economics', 'financial'],
            'Customer Service & Hospitality': ['hospitality', 'tourism', 'hotel management',
                                                'culinary', 'food service'],
            'Marketing & Communications': ['marketing', 'communications', 'journalism',
                                           'public relations', 'advertising', 'media studies'],
            'Education & Training': ['education', 'teaching', 'pedagogy', 'instructional design'],
            'Business Administration': ['business administration', 'management', 'mba',
                                        'organizational management'],
            'Nursing & Patient Care': ['nursing', 'nurse', 'healthcare', 'midwifery',
                                        'patient care', 'clinical nursing'],
            'Medicine & Healthcare': ['medicine', 'medical', 'surgery', 'mbbs',
                                       'clinical medicine', 'biomedical', 'public health'],
            'Pharmacy': ['pharmacy', 'pharmaceutical', 'pharmacology',
                          'pharmaceutical science'],
            'Dentistry': ['dentistry', 'dental surgery', 'dental science',
                           'oral health'],
            'Psychology & Counseling': ['psychology', 'counseling', 'behavioral science',
                                         'clinical psychology', 'social psychology'],
            'Law & Legal': ['law', 'legal studies', 'jurisprudence', 'llb',
                             'criminal justice', 'political science'],
            'Human Resources': ['human resource', 'hr management', 'organizational behavior',
                                 'labor relations', 'industrial relations'],
            'Sales & Retail': ['sales', 'retail management', 'business development',
                                'commercial studies'],
            'Logistics & Supply Chain': ['logistics', 'supply chain', 'operations management',
                                          'transportation', 'shipping management'],
            'Architecture & Interior Design': ['architecture', 'interior design',
                                                'landscape architecture', 'urban planning',
                                                'architectural engineering'],
            'Media & Journalism': ['journalism', 'mass communication', 'media studies',
                                    'broadcasting', 'film studies', 'media production'],
            'Graphic Design & Creative Arts': ['graphic design', 'fine arts', 'visual arts',
                                                'multimedia', 'animation', 'creative arts'],
            'Real Estate & Property': ['real estate', 'property management',
                                        'estate management', 'land management'],
            'Banking & Financial Services': ['banking', 'finance', 'financial services',
                                              'investment', 'insurance', 'actuarial science'],
            'IT Support & Systems Administration': ['information technology', 'computer science',
                                                      'network engineering', 'it management'],
            'Social Work & Community Services': ['social work', 'community development',
                                                   'human services', 'social science'],
            'Agriculture & Environmental Science': ['agriculture', 'environmental science',
                                                      'forestry', 'marine biology', 'ecology',
                                                      'horticulture', 'animal science'],
            'Culinary Arts & Food Industry': ['culinary arts', 'food technology',
                                                'hospitality', 'hotel management',
                                                'food science', 'nutrition'],
            'Transportation & Shipping': ['maritime', 'marine engineering', 'shipping',
                                            'naval architecture', 'transportation'],
            'Government & Public Administration': ['public administration', 'political science',
                                                     'governance', 'public policy',
                                                     'international relations'],
            'Research & Academia': ['research', 'scientific research', 'phd',
                                     'doctoral', 'academic research'],
            'Fitness & Sports': ['sports science', 'physical education', 'kinesiology',
                                  'exercise science', 'sports management'],
            'Fashion & Beauty': ['fashion design', 'textile design', 'cosmetology',
                                  'beauty therapy', 'fashion merchandising'],
            'Telecommunications': ['telecommunications', 'communication engineering',
                                    'electronic communication', 'network engineering'],
        }
        for edu_kw in field_edu_keywords.get(field, []):
            if edu_kw in edu_text or edu_kw in text_lower:
                score += 3
                matched_education.append(edu_kw.title())
                break  # Only count education bonus once per field

        # Only add supporting skill points if there's already some core/experience signal
        if matched_core or matched_experience or matched_education:
            for kw_title in supporting_matches:
                score += 1
                matched_supporting.append(kw_title)

        if score > 0:
            # Build explanation
            details = []
            if matched_core:
                details.append(f"Core skills: {', '.join(matched_core)}")
            if matched_supporting:
                details.append(f"Supporting skills: {', '.join(matched_supporting)}")
            if matched_experience:
                details.append(f"Experience match: {', '.join(matched_experience)}")
            if matched_education:
                details.append(f"Education: {', '.join(matched_education)}")
            field_results.append((field, score, '; '.join(details)))

    if not field_results:
        return [('General', 0, 'Your skill set does not strongly match a specific field. Consider adding more domain-specific skills.')]

    # Sort by score descending
    field_results.sort(key=lambda x: x[1], reverse=True)

    # Calculate confidence as percentage relative to max possible
    max_score = field_results[0][1]
    results_with_confidence = []
    for field, score, details in field_results[:3]:  # Top 3
        confidence = min(100, round((score / max(max_score, 1)) * 100))
        results_with_confidence.append((field, confidence, details))

    return results_with_confidence


def generate_recommendations(scores, explanations, skills, education, experience, text):
    """Generate improvement recommendations from score explanations."""
    recommendations = []

    # Collect all suggestions from score explanations
    for category in ['skills', 'education', 'experience', 'formatting']:
        for suggestion in explanations.get(category, {}).get('suggestions', []):
            recommendations.append(suggestion)

    # Additional cross-cutting recommendations
    categories = set(cat for _, cat in skills)
    if 'Soft Skills' not in categories and skills:
        recommendations.append(
            "Include soft skills such as leadership, communication, and teamwork "
            "to make your profile well-rounded."
        )

    if not recommendations:
        recommendations.append(
            "Great resume! Keep it updated with your latest projects and skills."
        )

    return recommendations


def _cross_validate_name(extracted_name, file_path, email, text):
    """Cross-validate the extracted name against the filename and email.

    If the extracted name doesn't match the filename at all, but the filename
    contains what looks like a real name, prefer the filename-derived name.
    Also use the email local part as a secondary signal.
    """
    # Extract name hints from filename
    # e.g., "Rodson_Napoleon_Ubaldo_-_CV.pdf" -> ["rodson", "napoleon", "ubaldo"]
    basename = os.path.splitext(os.path.basename(file_path))[0]
    # Remove common suffixes/prefixes
    cleaned_filename = re.sub(
        r'[_\-\s]*(cv|resume|r[eé]sum[eé]|curriculum[_\s]*vitae|final|draft|'
        r'updated|new|old|v\d+|copy|\d+)[_\-\s]*',
        ' ', basename, flags=re.IGNORECASE
    )
    # Split by underscores, hyphens, spaces
    filename_parts = [p.strip() for p in re.split(r'[_\-\s]+', cleaned_filename) if p.strip()]
    # Filter out non-name parts (numbers, single chars, common words)
    filename_name_parts = [
        p for p in filename_parts
        if len(p) >= 2 and p.isalpha() and p.lower() not in {
            'cv', 'resume', 'final', 'draft', 'updated', 'new', 'old', 'copy',
            'doc', 'pdf', 'file', 'document', 'the', 'and', 'for', 'rev',
        }
    ]

    # Extract name hints from email
    email_name_parts = []
    if email:
        local = email.split('@')[0].lower()
        # Split by dots, underscores, or detect camelCase
        parts = re.split(r'[._\-]', local)
        email_name_parts = [p for p in parts if p.isalpha() and len(p) >= 2]

    # Check if extracted name matches the filename
    if extracted_name and extracted_name != "Unknown Candidate":
        name_words = [w.lower() for w in extracted_name.split()]
        filename_words = [w.lower() for w in filename_name_parts]

        # If at least one word from the extracted name matches the filename, it's validated
        if filename_words:
            overlap = sum(1 for w in name_words if any(fw.startswith(w[:3]) or w.startswith(fw[:3])
                         for fw in filename_words))
            if overlap >= 1:
                return extracted_name  # Name matches filename — confident

        # If no filename match, check against email
        if email_name_parts:
            email_overlap = sum(1 for w in name_words if any(
                ep.startswith(w[:3].lower()) or w.lower().startswith(ep[:3])
                for ep in email_name_parts
            ))
            if email_overlap >= 1:
                return extracted_name  # Name matches email — confident

    # If extracted name is "Unknown Candidate" or doesn't match filename/email,
    # try to build a name from the filename
    if len(filename_name_parts) >= 2:
        # Verify these filename parts look like name parts (not random words)
        # Cross-check against email
        filename_candidate = ' '.join(p.title() for p in filename_name_parts)
        if email_name_parts:
            fn_lower = [p.lower() for p in filename_name_parts]
            email_match = sum(1 for p in fn_lower if any(
                ep.startswith(p[:3]) or p.startswith(ep[:3]) for ep in email_name_parts
            ))
            if email_match >= 1:
                return filename_candidate

        # Even without email match, if filename has 2-4 name-like parts, use it
        if 2 <= len(filename_name_parts) <= 4:
            # But only if extracted name was clearly wrong (Unknown or doesn't match anything)
            if extracted_name == "Unknown Candidate" or (
                extracted_name and not any(
                    w.lower() in [ep.lower() for ep in email_name_parts]
                    for w in extracted_name.split()
                ) and email_name_parts
            ):
                return filename_candidate

    return extracted_name


def analyse_resume(file_path, original_filename=None):
    """Main function: analyse a resume (PDF or image) and return all extracted data.

    original_filename, if given, is used instead of file_path for the
    filename-based name-guessing fallback — app.py stores uploads under a
    randomized name (a hex token prefix, to avoid collisions between users),
    and that random token isn't a name hint, just noise that would otherwise
    get fed into the same heuristic.
    """
    # Step 1: Extract text (supports PDF and images)
    text = extract_text(file_path)

    if not text.strip():
        has_ocr = _has_tesseract()
        ext = os.path.splitext(file_path)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            if not has_ocr:
                return {
                    'error': 'Tesseract OCR is not installed. To scan images, install Tesseract from: '
                             'https://github.com/UB-Mannheim/tesseract/wiki — then restart the server. '
                             'Alternatively, upload a text-based PDF instead.'
                }
            return {
                'error': 'Could not extract text from the image. The image may be too blurry or low resolution. '
                         'Try uploading a clearer image or a PDF version instead.'
            }
        if not has_ocr:
            return {
                'error': 'This PDF appears to be scanned or image-only, and Tesseract OCR is not installed. '
                         'To support scanned PDFs, install Tesseract from: '
                         'https://github.com/UB-Mannheim/tesseract/wiki — then restart the server. '
                         'Alternatively, upload a text-based PDF (created from Word, Google Docs, etc.).'
            }
        return {
            'error': 'Could not extract text from the PDF. The file may be corrupted or contain only images '
                     'that could not be read. Try uploading a different version of your resume.'
        }

    # Step 2: Extract information
    name = extract_name(text)
    email = extract_email(text)
    phone = extract_phone(text)

    # Cross-validate name against filename and email for extra confidence
    name = _cross_validate_name(name, original_filename or file_path, email, text)
    skills = extract_skills(text)
    education = extract_education(text)
    experience = extract_experience(text)

    # Step 3: Calculate scores with explanations
    scores, explanations = calculate_scores(text, skills, education, experience)

    # Step 4: Recommend career fields (improved)
    field_recommendations = recommend_field(skills, experience, text)
    primary_field = field_recommendations[0][0] if field_recommendations else 'General IT'

    # Step 5: Generate recommendations
    recommendations = generate_recommendations(scores, explanations, skills, education, experience, text)

    # Step 6: ATS Simulation
    ats_results = simulate_ats(text, skills, education, experience, scores)

    # Step 7: Career fit roles
    career_roles = suggest_career_roles(skills, experience, education, text)

    # Step 8: Employer summary
    employer_summary = generate_employer_summary(
        name, skills, education, experience, scores, field_recommendations,
        experience_years=estimate_experience_years(text),
    )

    return {
        'name': name,
        'email': email,
        'phone': phone,
        'raw_text': text,
        'skills': skills,
        'education': education,
        'experience': experience,
        'scores': scores,
        'explanations': explanations,
        'recommended_field': primary_field,
        'field_recommendations': field_recommendations,
        'recommendations': recommendations,
        'ats_results': ats_results,
        'career_roles': career_roles,
        'employer_summary': employer_summary,
    }


# ---------------------------------------------------------------------------
# Feature 1 & 7: Context-Aware Personalized Feedback / Resume Personalization
# ---------------------------------------------------------------------------

def generate_personalized_feedback(resume_data, career_goal='', experience_level='', target_role=''):
    """Generate tailored feedback based on the user's career goals, experience level, and target role.

    Also serves Feature 7 (Enhanced Resume Personalization) by providing
    role-specific customization suggestions.
    """
    skills = resume_data.get('skills', [])
    education = resume_data.get('education', [])
    experience = resume_data.get('experience', [])
    scores = resume_data.get('scores', {})
    text = resume_data.get('raw_text', '')
    text_lower = text.lower()

    skill_names = set(s.lower() for s, _ in skills) if skills else set()
    feedback = {
        'experience_level_assessment': '',
        'career_alignment': [],
        'strengths': [],
        'gaps': [],
        'action_items': [],
        'personalization_tips': [],
    }

    # --- Determine experience level ---
    exp_level = experience_level.lower() if experience_level else ''
    if not exp_level:
        # Auto-detect from resume
        exp_count = len(experience)
        has_degree = any(
            entry.get('degree', '') for entry in education
        ) if isinstance(education, list) and education else False

        if exp_count == 0:
            exp_level = 'entry'
        elif exp_count <= 2:
            exp_level = 'junior'
        elif exp_count <= 5:
            exp_level = 'mid'
        else:
            exp_level = 'senior'

    level_labels = {
        'entry': 'Entry-Level / Student',
        'junior': 'Junior Professional (0-2 years)',
        'mid': 'Mid-Level Professional (2-5 years)',
        'senior': 'Senior Professional (5+ years)',
    }
    feedback['experience_level_assessment'] = level_labels.get(exp_level, 'Not determined')

    # --- Tailored feedback by experience level ---
    if exp_level == 'entry':
        if scores.get('skills', 0) < 60:
            feedback['gaps'].append(
                'As an entry-level candidate, focus on listing all technical skills you learned '
                'in school, personal projects, and online courses — even basics like Microsoft Office or Google Suite.'
            )
        if scores.get('experience', 0) < 50:
            feedback['gaps'].append(
                'Include internships, volunteer work, university projects, and part-time jobs. '
                'Entry-level employers value any form of work experience.'
            )
        feedback['action_items'].append(
            'Create a "Projects" section highlighting class or personal projects with the technologies used.'
        )
        feedback['action_items'].append(
            'Add relevant coursework that aligns with your target role.'
        )
    elif exp_level == 'junior':
        if scores.get('skills', 0) < 70:
            feedback['gaps'].append(
                'Expand your skills section — junior roles benefit from showing breadth of knowledge.'
            )
        feedback['action_items'].append(
            'Quantify your achievements: "Increased efficiency by 20%" is stronger than "Improved processes."'
        )
    elif exp_level in ('mid', 'senior'):
        if scores.get('skills', 0) < 80:
            feedback['gaps'].append(
                'At your level, employers expect specialized expertise. Highlight advanced skills and certifications.'
            )
        feedback['action_items'].append(
            'Lead with impact metrics: revenue generated, team size managed, systems scaled.'
        )
        feedback['action_items'].append(
            'Consider adding a "Key Achievements" section at the top of your resume.'
        )

    # --- Strengths ---
    for key in ['skills', 'education', 'experience', 'formatting']:
        score_val = scores.get(key, 0)
        if score_val >= 80:
            feedback['strengths'].append(f'Your {key} section is strong (scored {score_val}/100).')

    if len(skill_names) >= 10:
        feedback['strengths'].append(f'Good skill diversity with {len(skill_names)} skills detected.')

    # --- Career goal alignment ---
    if career_goal:
        career_goal_lower = career_goal.lower()
        # Check if skills align with career goal
        goal_skill_map = {
            'web': ['html', 'css', 'javascript', 'react', 'angular', 'vue', 'node.js',
                     'django', 'flask', 'next.js', 'typescript'],
            'data': ['python', 'pandas', 'numpy', 'machine learning', 'data analysis',
                      'tableau', 'power bi', 'sql', 'statistics'],
            'mobile': ['react native', 'flutter', 'android', 'ios', 'swift', 'kotlin'],
            'cloud': ['aws', 'azure', 'docker', 'kubernetes', 'devops', 'terraform'],
            'security': ['security', 'penetration testing', 'firewall', 'encryption'],
            'management': ['leadership', 'project management', 'agile', 'scrum', 'communication'],
        }
        matched_goal = None
        for goal_key, goal_skills in goal_skill_map.items():
            if goal_key in career_goal_lower:
                matched_goal = goal_key
                found = [s for s in goal_skills if s in skill_names]
                missing = [s for s in goal_skills if s not in skill_names][:5]
                if found:
                    feedback['career_alignment'].append(
                        f'Your skills match your "{career_goal}" goal: {", ".join(s.title() for s in found)}.'
                    )
                if missing:
                    feedback['gaps'].append(
                        f'To strengthen your "{career_goal}" profile, consider learning: '
                        f'{", ".join(s.title() for s in missing)}.'
                    )
                break

        if not matched_goal:
            feedback['career_alignment'].append(
                f'Goal noted: "{career_goal}". Focus on acquiring industry-specific certifications '
                f'and gaining relevant experience in this area.'
            )

    # --- Target role personalization (Feature 7) ---
    if target_role:
        feedback['personalization_tips'].append(
            f'For a "{target_role}" position, place your most relevant experience and skills first.'
        )
        target_lower = target_role.lower()
        # Check for keyword gaps
        role_keywords = {
            'software engineer': ['algorithms', 'data structures', 'git', 'testing', 'agile'],
            'data analyst': ['sql', 'excel', 'tableau', 'power bi', 'data visualization'],
            'web developer': ['html', 'css', 'javascript', 'react', 'responsive design'],
            'project manager': ['agile', 'scrum', 'stakeholder management', 'budgeting'],
            'ux designer': ['figma', 'user research', 'wireframe', 'prototype', 'usability'],
        }
        for role_key, role_skills in role_keywords.items():
            if role_key in target_lower:
                missing = [s for s in role_skills if s not in skill_names]
                if missing:
                    feedback['personalization_tips'].append(
                        f'Consider adding these keywords for ATS compatibility: '
                        f'{", ".join(s.title() for s in missing)}.'
                    )
                break

        feedback['personalization_tips'].append(
            f'Tailor your summary/objective to mention "{target_role}" specifically.'
        )
        feedback['personalization_tips'].append(
            'Reorder your bullet points so the most relevant achievements appear first.'
        )

    # General action items
    if not feedback['action_items']:
        feedback['action_items'].append('Keep your resume updated with your latest accomplishments.')

    return feedback


# ---------------------------------------------------------------------------
# Feature 2: Advanced ATS Simulation with Transparency
# ---------------------------------------------------------------------------

def simulate_ats(text, skills, education, experience, scores):
    """Simulate an Applicant Tracking System scan and report findings.

    Checks for:
    - Required sections (Contact, Summary, Skills, Education, Experience)
    - Formatting issues (special characters, tables, images)
    - Readability and structure
    - Keyword density
    - ATS compatibility score
    """
    text_lower = text.lower()
    lines = text.split('\n')

    results = {
        'ats_score': 0,
        'sections_found': [],
        'sections_missing': [],
        'formatting_issues': [],
        'readability': {},
        'keyword_analysis': {},
        'pass_likely': False,
    }

    # --- Section Detection ---
    required_sections = {
        'Contact Information': ['email', 'phone', '@', 'tel:', 'mobile'],
        'Summary / Objective': ['summary', 'objective', 'profile', 'about me', 'professional summary'],
        'Skills': ['skills', 'technical skills', 'core competencies', 'key skills'],
        'Education': ['education', 'academic', 'qualifications', 'degree'],
        'Experience': ['experience', 'work history', 'employment', 'professional experience'],
    }

    section_score = 0
    for section_name, keywords in required_sections.items():
        found = any(kw in text_lower for kw in keywords)
        if found:
            results['sections_found'].append(section_name)
            section_score += 20
        else:
            results['sections_missing'].append(section_name)

    # --- Formatting Issues ---
    # Check for special/problematic characters
    special_chars = re.findall(r'[\uf0d8\uf0b7\uf0e0\uf095\u2022\u25cf\u25cb\u25aa\u25ab]', text)
    if len(special_chars) > 5:
        results['formatting_issues'].append({
            'issue': 'Special Unicode Characters Detected',
            'detail': f'Found {len(special_chars)} special characters that may not parse correctly in ATS systems.',
            'fix': 'Replace fancy bullet points with standard dashes (-) or asterisks (*).',
            'severity': 'medium',
        })

    # Check line length (very long lines suggest table/column layouts)
    long_lines = [l for l in lines if len(l.strip()) > 120]
    if len(long_lines) > 5:
        results['formatting_issues'].append({
            'issue': 'Complex Layout Detected',
            'detail': f'{len(long_lines)} lines exceed 120 characters, suggesting multi-column or table layout.',
            'fix': 'Use a single-column layout. ATS systems read left-to-right and may scramble multi-column content.',
            'severity': 'high',
        })

    # Check for excessive blank lines (poor structure)
    blank_count = sum(1 for l in lines if not l.strip())
    if blank_count > len(lines) * 0.4:
        results['formatting_issues'].append({
            'issue': 'Excessive Blank Lines',
            'detail': f'{blank_count} out of {len(lines)} lines are blank ({round(blank_count/max(len(lines),1)*100)}%).',
            'fix': 'Remove unnecessary blank lines to improve information density.',
            'severity': 'low',
        })

    # Check for header/footer noise
    if re.search(r'page\s+\d+\s*(of\s+\d+)?', text_lower):
        results['formatting_issues'].append({
            'issue': 'Page Numbers Detected',
            'detail': 'Page numbers can confuse ATS parsers.',
            'fix': 'Remove headers and footers including page numbers from your resume.',
            'severity': 'low',
        })

    # Check for images/graphics mention
    if not text.strip() or len(text.strip()) < 100:
        results['formatting_issues'].append({
            'issue': 'Minimal Text Content',
            'detail': 'Very little text was extracted. Resume may be image-heavy or use graphics for text.',
            'fix': 'Use actual text instead of images. ATS cannot read text embedded in images.',
            'severity': 'high',
        })

    # --- Readability Analysis ---
    words = text.split()
    word_count = len(words)
    sentence_count = len(re.findall(r'[.!?]+', text)) or 1
    avg_sentence_len = word_count / sentence_count

    results['readability'] = {
        'word_count': word_count,
        'line_count': len(lines),
        'avg_sentence_length': round(avg_sentence_len, 1),
    }

    # Word count assessment
    if word_count < 150:
        results['formatting_issues'].append({
            'issue': 'Resume Too Short',
            'detail': f'Only {word_count} words detected. Most ATS-friendly resumes have 300-700 words.',
            'fix': 'Expand your descriptions with specific achievements, metrics, and relevant details.',
            'severity': 'high',
        })
    elif word_count > 1000:
        results['formatting_issues'].append({
            'issue': 'Resume May Be Too Long',
            'detail': f'{word_count} words detected. Consider condensing to 1-2 pages.',
            'fix': 'Focus on the most relevant and recent experience. Remove outdated entries.',
            'severity': 'medium',
        })

    # --- Keyword Analysis ---
    skill_count = len(skills)
    results['keyword_analysis'] = {
        'total_skills_detected': skill_count,
        'skill_density': round(skill_count / max(word_count / 100, 1), 1),
        'has_industry_keywords': skill_count >= 5,
    }

    # --- Calculate ATS Score ---
    ats_score = section_score  # 0-100 from sections

    # Formatting penalty
    high_issues = sum(1 for i in results['formatting_issues'] if i['severity'] == 'high')
    med_issues = sum(1 for i in results['formatting_issues'] if i['severity'] == 'medium')
    ats_score -= (high_issues * 15 + med_issues * 5)

    # Keyword bonus
    if skill_count >= 10:
        ats_score += 10
    elif skill_count >= 5:
        ats_score += 5

    # Readability bonus (word count in good range)
    if 300 <= word_count <= 800:
        ats_score += 10

    results['ats_score'] = max(0, min(100, ats_score))
    results['pass_likely'] = results['ats_score'] >= 60

    return results


# ---------------------------------------------------------------------------
# Feature 3: Smart Job-Match Analysis
# ---------------------------------------------------------------------------

_semantic_model = None


def _get_semantic_model():
    """Lazily load and cache the sentence-embedding model (only on first use,
    so importing analyzer.py or running the rest of the app doesn't pay the
    load cost when job-matching is never used)."""
    global _semantic_model
    if _semantic_model is None:
        from sentence_transformers import SentenceTransformer
        _semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _semantic_model


def _semantic_similarity(resume_text, job_description):
    """Cosine similarity (0-100) between resume and JD embeddings.

    Returns None if the model can't be loaded (e.g. dependency missing or a
    first-run model download failed) so the caller can fall back gracefully
    to lexical-only matching instead of crashing the whole feature.
    """
    try:
        from sentence_transformers import util
        model = _get_semantic_model()
        embeddings = model.encode([resume_text[:2000], job_description[:2000]])
        score = float(util.cos_sim(embeddings[0], embeddings[1])[0][0]) * 100
        return max(0, min(100, round(score)))
    except Exception:
        return None


def match_job_description(resume_text, job_description):
    """Compare a resume against a job description.

    Blends lexical matching (word/phrase overlap and a skills-database
    lookup, via NLTK tokenization and stopword removal) with real semantic
    similarity from sentence embeddings, so e.g. "JS" in a resume can match
    "JavaScript" in a job description even without an exact string match.
    """
    if not job_description.strip():
        return {'error': 'No job description provided.'}

    # Tokenize and clean both texts
    stop_words = set(stopwords.words('english'))

    def extract_meaningful_words(text):
        tokens = word_tokenize(text.lower())
        return set(t for t in tokens if t.isalpha() and len(t) > 2 and t not in stop_words)

    def extract_phrases(text):
        """Extract 2-3 word phrases (bigrams/trigrams) for better matching."""
        tokens = word_tokenize(text.lower())
        clean = [t for t in tokens if t.isalpha() and t not in stop_words]
        phrases = set()
        for i in range(len(clean) - 1):
            phrases.add(f"{clean[i]} {clean[i+1]}")
        for i in range(len(clean) - 2):
            phrases.add(f"{clean[i]} {clean[i+1]} {clean[i+2]}")
        return phrases

    resume_words = extract_meaningful_words(resume_text)
    jd_words = extract_meaningful_words(job_description)

    resume_phrases = extract_phrases(resume_text)
    jd_phrases = extract_phrases(job_description)

    # Word-level matching
    word_matches = resume_words & jd_words
    word_only_in_jd = jd_words - resume_words

    # Phrase-level matching
    phrase_matches = resume_phrases & jd_phrases

    # Extract specific requirements from JD using word-boundary matching
    jd_lower = job_description.lower()
    resume_lower = resume_text.lower()
    required_skills = set()
    matched_skills = set()
    missing_skills = set()

    # Short skills that need strict word-boundary matching to avoid false positives
    SHORT_SKILLS = {'r', 'c', 'go', 'css', 'sql', 'git', 'npm', 'pip', 'lua',
                    'ios', 'aws', 'gcp', 'qa', 'ui', 'ux', 'ai', 'ml', 'nlp',
                    'svm', 'hnd', 'hnc', 'ba', 'ma', 'md', 'vba', 'sre'}

    for category, skill_list in SKILLS_DB.items():
        for skill in skill_list:
            # Use word-boundary regex for accurate matching
            if len(skill) <= 3 or skill in SHORT_SKILLS:
                pattern = r'(?<![a-zA-Z])' + re.escape(skill) + r'(?![a-zA-Z])'
            else:
                pattern = r'\b' + re.escape(skill) + r'\b'

            if re.search(pattern, jd_lower):
                required_skills.add(skill)
                if re.search(pattern, resume_lower):
                    matched_skills.add(skill)
                else:
                    missing_skills.add(skill)

    # Semantic similarity (embeddings) — supplements the lexical signals below
    # with something that understands "JS" and "JavaScript" are related even
    # when the resume and JD don't share the exact same string.
    semantic_similarity = _semantic_similarity(resume_text, job_description)

    # Calculate match score
    if not jd_words:
        match_pct = 0
    else:
        word_pct = len(word_matches) / len(jd_words) * 100
        phrase_pct = min(len(phrase_matches) * 5, 100)  # Each phrase match is worth more
        skill_pct = (len(matched_skills) / max(len(required_skills), 1)) * 100

        if semantic_similarity is not None:
            # word (35%) + phrase (15%) + skill-database (25%) + semantic (25%)
            match_pct = round(word_pct * 0.35 + phrase_pct * 0.15 + skill_pct * 0.25 + semantic_similarity * 0.25)
        else:
            # Semantic model unavailable — fall back to the original lexical-only weights
            match_pct = round(word_pct * 0.5 + phrase_pct * 0.2 + skill_pct * 0.3)
        match_pct = min(100, match_pct)

    # Categorize missing keywords by importance
    all_skills_flat = set(s for sl in SKILLS_DB.values() for s in sl)
    important_missing = []
    nice_to_have_missing = []
    for word in sorted(word_only_in_jd):
        if word in all_skills_flat:
            important_missing.append(word)
        elif len(word) > 4:
            nice_to_have_missing.append(word)

    # Generate recommendations for missing skills
    missing_skill_recommendations = []
    for skill in sorted(missing_skills):
        tip = _get_skill_recommendation(skill)
        missing_skill_recommendations.append({
            'skill': skill.title(),
            'tip': tip,
        })

    return {
        'match_score': match_pct,
        'semantic_similarity': semantic_similarity,
        'matched_keywords': sorted(word_matches)[:30],
        'matched_skills': sorted(s.title() for s in matched_skills),
        'missing_skills': sorted(s.title() for s in missing_skills),
        'missing_skill_recommendations': missing_skill_recommendations,
        'important_missing_keywords': sorted(important_missing)[:15],
        'nice_to_have_keywords': sorted(nice_to_have_missing)[:15],
        'phrase_matches': sorted(phrase_matches)[:10],
        'total_jd_keywords': len(jd_words),
        'total_matched': len(word_matches),
        'recommendation': _get_match_recommendation(match_pct),
    }


def _get_skill_recommendation(skill):
    """Return a brief actionable tip for a missing skill."""
    skill_lower = skill.lower()
    # Programming languages
    if skill_lower in ('python', 'java', 'javascript', 'c++', 'c#', 'ruby', 'php',
                       'swift', 'kotlin', 'go', 'rust', 'typescript', 'r', 'dart'):
        return f'Add {skill.title()} to your Skills section if you have any experience with it, even from coursework or personal projects.'
    # Frameworks
    if skill_lower in ('react', 'angular', 'vue', 'django', 'flask', 'node.js',
                       'spring boot', 'laravel', 'flutter', 'react native', 'next.js',
                       'express', 'asp.net', 'bootstrap', 'tailwind'):
        return f'If you have used {skill.title()}, list it under Technical Skills. Even tutorial-level experience counts for entry roles.'
    # Cloud/DevOps
    if skill_lower in ('aws', 'azure', 'docker', 'kubernetes', 'jenkins', 'ci/cd',
                       'terraform', 'linux', 'git', 'devops', 'google cloud', 'gcp'):
        return f'Consider adding {skill.title()} — free certifications or labs (e.g., AWS Free Tier, Docker tutorials) can help you build this skill quickly.'
    # Data
    if skill_lower in ('machine learning', 'deep learning', 'data analysis', 'pandas',
                       'tensorflow', 'pytorch', 'tableau', 'power bi', 'sql'):
        return f'Mention any {skill.title()} projects, even academic ones. Highlight datasets analyzed or models built.'
    # Soft skills
    if skill_lower in ('leadership', 'teamwork', 'communication', 'project management',
                       'agile', 'scrum', 'problem solving', 'time management'):
        return f'Demonstrate {skill.title()} through concrete examples in your Experience section rather than just listing it.'
    # Default
    return f'Consider learning or highlighting {skill.title()} on your resume if relevant to this role.'


def _get_match_recommendation(score):
    # Thresholds match the match-circle CSS tiers in job_match.html (70/50/30)
    # so the visual tier and this verdict text always agree.
    if score >= 70:
        return 'Excellent match! Your resume aligns very well with this job description.'
    elif score >= 50:
        return 'Good match. Add the missing keywords to strengthen your application.'
    elif score >= 30:
        return 'Moderate match. Consider tailoring your resume significantly for this role.'
    else:
        return 'Low match. This role may require skills or experience not reflected in your resume.'


# ---------------------------------------------------------------------------
# Feature 5: Career Fit and Role Recommendation
# ---------------------------------------------------------------------------

def suggest_career_roles(skills, experience, education, text):
    """Suggest specific job roles/titles based on skills, experience, and education.

    Returns a list of role suggestions with reasoning.
    """
    skill_names = set(s.lower() for s, _ in skills) if skills else set()
    text_lower = text.lower()
    exp_text = ' '.join(title for title, _, _ in experience).lower() if experience else ''

    role_database = {
        'Junior Web Developer': {
            'required': ['html', 'css', 'javascript'],
            'bonus': ['react', 'vue', 'angular', 'node.js', 'typescript', 'bootstrap'],
            'level': 'entry',
        },
        'Full-Stack Developer': {
            'required': ['javascript', 'html', 'css'],
            'bonus': ['react', 'node.js', 'python', 'sql', 'mongodb', 'express', 'next.js'],
            'level': 'mid',
        },
        'Software Engineer': {
            'required': ['python', 'git'],
            'bonus': ['java', 'c++', 'c#', 'algorithms', 'data structures', 'sql', 'docker'],
            'level': 'mid',
        },
        'Data Analyst': {
            'required': ['sql', 'excel'],
            'bonus': ['python', 'tableau', 'power bi', 'pandas', 'data analysis', 'data visualization'],
            'level': 'entry',
        },
        'Data Scientist': {
            'required': ['python', 'machine learning'],
            'bonus': ['tensorflow', 'pytorch', 'pandas', 'numpy', 'scikit-learn', 'deep learning'],
            'level': 'mid',
        },
        'Mobile App Developer': {
            'required': ['react native'],
            'bonus': ['flutter', 'android', 'ios', 'swift', 'kotlin', 'dart'],
            'level': 'mid',
        },
        'DevOps Engineer': {
            'required': ['docker', 'linux'],
            'bonus': ['aws', 'kubernetes', 'terraform', 'jenkins', 'ci/cd', 'ansible'],
            'level': 'mid',
        },
        'UI/UX Designer': {
            'required': ['figma'],
            'bonus': ['adobe photoshop', 'sketch', 'wireframe', 'user research', 'prototype'],
            'level': 'entry',
        },
        'Database Administrator': {
            'required': ['sql', 'database design'],
            'bonus': ['mysql', 'postgresql', 'mongodb', 'oracle', 'redis', 'sql server'],
            'level': 'mid',
        },
        'Project Coordinator': {
            'required': ['communication', 'teamwork'],
            'bonus': ['leadership', 'time management', 'agile', 'scrum', 'jira', 'strategic planning'],
            'level': 'entry',
        },
        'Office Administrator': {
            'required': ['communication'],
            'bonus': ['time management', 'teamwork', 'adaptability', 'presentation', 'problem solving'],
            'level': 'entry',
        },
        'Customer Service Representative': {
            'required': ['communication'],
            'bonus': ['teamwork', 'problem solving', 'adaptability', 'time management'],
            'level': 'entry',
        },
        'Business Analyst': {
            'required': ['communication', 'data analysis'],
            'bonus': ['sql', 'excel', 'tableau', 'power bi', 'strategic planning'],
            'level': 'mid',
        },
        'IT Support Specialist': {
            'required': ['communication'],
            'bonus': ['linux', 'networking', 'python', 'bash', 'problem solving'],
            'level': 'entry',
        },
    }

    suggestions = []
    for role, config in role_database.items():
        required = config['required']
        bonus = config['bonus']

        # Check required skills
        req_match = sum(1 for s in required if s in skill_names)
        if req_match < len(required):
            continue  # Must have all required skills

        # Count bonus skills
        bonus_match = sum(1 for s in bonus if s in skill_names)
        total_match = req_match + bonus_match
        max_possible = len(required) + len(bonus)

        fit_score = round((total_match / max_possible) * 100)

        # Experience boost
        if any(role.lower().split()[0] in exp_text for _ in [1]):
            fit_score = min(100, fit_score + 15)

        matched_skills = [s.title() for s in required + bonus if s in skill_names]

        suggestions.append({
            'role': role,
            'fit_score': fit_score,
            'level': config['level'],
            'matched_skills': matched_skills,
            'total_matched': total_match,
        })

    # Sort by fit score
    suggestions.sort(key=lambda x: x['fit_score'], reverse=True)
    return suggestions[:6]  # Top 6 roles


# ---------------------------------------------------------------------------
# Feature 6: Employer-Oriented Insights
# ---------------------------------------------------------------------------

def generate_employer_summary(name, skills, education, experience, scores, field_recommendations,
                              experience_years=None):
    """Generate a hiring-manager-friendly summary of the candidate.

    Provides a quick overview for recruiters to assess fit.
    experience_years is the time covered by the dated jobs; when it is known it decides the seniority, because
    counting job-title lines overrates someone with several short roles and underrates a long single one.
    """
    skill_names = [s for s, _ in skills] if skills else []
    categories = set(cat for _, cat in skills) if skills else set()

    # Determine seniority
    exp_count = len(experience) if experience else 0
    if experience_years is not None:
        seniority = 'Senior' if experience_years >= 5 else 'Mid-Level' if experience_years >= 2 else 'Entry-Level'
    elif exp_count >= 5:
        seniority = 'Senior'
    elif exp_count >= 2:
        seniority = 'Mid-Level'
    else:
        seniority = 'Entry-Level'

    # Top field
    top_field = field_recommendations[0][0] if field_recommendations else 'General'

    # Build summary
    edu_text = ''
    if education:
        for entry in education:
            if isinstance(entry, dict):
                inst = entry.get('institution', '')
                deg = entry.get('degree', '')
                if inst or deg:
                    edu_text = f"{deg} from {inst}" if deg and inst else (deg or inst)
                    break

    overall = scores.get('overall', 0)
    if overall >= 80:
        verdict = 'Strong Candidate'
        verdict_class = 'excellent'
    elif overall >= 60:
        verdict = 'Good Candidate'
        verdict_class = 'good'
    elif overall >= 40:
        verdict = 'Potential Candidate'
        verdict_class = 'average'
    else:
        verdict = 'Needs Development'
        verdict_class = 'poor'

    # Highlight skills (top 8)
    highlight_skills = skill_names[:8]

    # Key strengths
    strengths = []
    if scores.get('skills', 0) >= 80:
        strengths.append(f'Diverse skill set ({len(skill_names)} skills across {len(categories)} categories)')
    if scores.get('experience', 0) >= 80:
        strengths.append(f'Solid work experience ({exp_count} positions)')
    if scores.get('education', 0) >= 70:
        strengths.append(f'Strong educational background')
    if scores.get('formatting', 0) >= 80:
        strengths.append('Well-formatted, professional resume')

    # Areas of concern
    concerns = []
    if scores.get('skills', 0) < 50:
        concerns.append('Limited technical skills demonstrated')
    if scores.get('experience', 0) < 50:
        concerns.append('Limited work experience')
    if scores.get('education', 0) < 40:
        concerns.append('Education section needs improvement')

    return {
        'candidate_name': name,
        'seniority': seniority,
        'primary_field': top_field,
        'verdict': verdict,
        'verdict_class': verdict_class,
        'overall_score': overall,
        'education_summary': edu_text,
        'highlight_skills': highlight_skills,
        'strengths': strengths,
        'concerns': concerns,
        'scores': scores,
    }


from resume_templates import RESUME_TEMPLATES  # noqa: E402,F401  (the builder's templates now live there)


def highlight_matches(raw_text, skill_names):
    """HTML-escape raw resume text and wrap case-insensitive, word-boundary
    matches of each skill name in <mark> tags, so the caller can render it
    with |safe. Longest names are matched first via a single alternation
    pass so multi-word skills aren't shadowed by a shorter substring skill
    and nothing gets double-wrapped."""
    from markupsafe import escape
    if not raw_text:
        return ''
    escaped = str(escape(raw_text))
    names = sorted({s for s in skill_names if s}, key=len, reverse=True)
    if not names:
        return escaped
    pattern = re.compile(
        r'(?<!\w)(' + '|'.join(re.escape(n) for n in names) + r')(?!\w)',
        re.IGNORECASE
    )
    return pattern.sub(r'<mark>\1</mark>', escaped)
