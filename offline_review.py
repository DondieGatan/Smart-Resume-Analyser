"""A plain, rule-based review of the Resume Builder draft, used when the AI cannot answer.

The "Review My Whole Resume for Gaps" button must never leave the user with an error or a spinner. When the AI is
busy, rate limited or too slow, builder_assistant falls back to this: it needs no network, runs in milliseconds and
points at the same kinds of gaps (missing sections, no dates, no numbers, placeholders left in). It cannot rewrite
text, so it returns no suggestion cards.
"""
import re

INTRO = ('The AI is busy right now, so this is a quick automatic check of your draft instead of the full AI review. '
         'Press the button again in a minute for the full review.')

_PLACEHOLDER = re.compile(r'\[[^\]\n]{3,}\]')
_EMAIL = re.compile(r'[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}')
_PHONE = re.compile(r'\+?\d[\d\s().-]{7,}\d')
_DATE = re.compile(r'\b(?:19|20)\d{2}\b|\bpresent\b|\bcurrent\b', re.IGNORECASE)
_WEAK_OPENER = re.compile(r'^[-*\s]*(?:responsible for|worked on|helped|assisted with|duties included|tasked with)\b',
                          re.IGNORECASE | re.MULTILINE)
_SKILL_LABEL = re.compile(r'(?im)^[A-Za-z ]{3,25}:')


def _text_of(draft, key):
    value = draft.get(key) if isinstance(draft, dict) else None
    return (value if isinstance(value, str) else '').strip()


def review(draft, sections):
    """Returns {'reply', 'parts', 'offline': True} in the same shape as an AI answer."""
    names = {s['id']: s['name'] for s in sections}
    issues, flagged = [], set()

    def flag(section_id, message):
        flagged.add(section_id)
        issues.append(f'- {names.get(section_id, section_id)}: {message}')

    contact = _text_of(draft, 'contact')
    if not contact:
        flag('contact', 'empty. Add your full name, email, phone number and city.')
    else:
        if not _EMAIL.search(contact):
            flag('contact', 'no email address found.')
        if not _PHONE.search(contact):
            flag('contact', 'no phone number found.')

    summary = _text_of(draft, 'summary')
    words = len(summary.split())
    if not summary:
        flag('summary', 'empty. Write 2 to 3 sentences: your role or field, your strongest skills, and what you want next.')
    elif words < 20:
        flag('summary', f"only {words} word{'' if words == 1 else 's'}. Aim for 30 to 70 so it says who you are and what you offer.")
    elif words > 100:
        flag('summary', f'{words} words is long. Trim it to about 30 to 70 words.')

    skills = [x for x in re.split(r'[,;|\n]', _SKILL_LABEL.sub('', _text_of(draft, 'skills'))) if x.strip()]
    if not skills:
        flag('skills', 'empty. List the tools, technologies and strengths the jobs you want ask for.')
    elif len(skills) < 6:
        flag('skills', f'only {len(skills)} listed. Add more of the tools and strengths the job posts mention.')
    elif len(skills) > 30:
        flag('skills', f'{len(skills)} listed is a lot. Keep the ones that matter most for the jobs you want.')

    experience = _text_of(draft, 'experience')
    if not experience:
        flag('experience', 'empty. Add jobs, internships, freelance, volunteer or part-time work. It all counts.')
    else:
        problems = []
        for block in (b for b in re.split(r'\n\s*\n', experience) if b.strip()):
            lines = [l for l in block.split('\n') if l.strip()]
            title = lines[0][:45]
            if not _DATE.search(block):
                problems.append(f'"{title}" has no dates')
            if len(lines) < 2:
                problems.append(f'"{title}" has no description. Add 2 or 3 bullet points')
            elif not any(ch.isdigit() for ch in ' '.join(lines[1:])):
                problems.append(f'"{title}" has no numbers or results (how many, how much, how fast)')
            if _WEAK_OPENER.search(block):
                problems.append(f'"{title}" starts a line with a weak phrase. Start with a verb such as Built, Led or Reduced')
        for problem in problems[:5]:
            flag('experience', problem + '.')
        if len(problems) > 5:
            flag('experience', f'and {len(problems) - 5} more of the same kind.')

    education = _text_of(draft, 'education')
    if not education:
        flag('education', 'empty. Add your degree or course, the school and the year (or expected year).')
    elif not _DATE.search(education):
        flag('education', 'no year found. Add when you finished, or expect to finish.')

    if not _text_of(draft, 'projects'):
        flag('projects', 'empty. One or two projects with the tools you used and the result make a junior resume much stronger.')

    leftovers = sum(len(_PLACEHOLDER.findall(_text_of(draft, s['id']))) for s in sections)
    if leftovers:
        issues.append(f'- Whole resume: {leftovers} [bracketed] placeholder(s) are still in the text. Replace them with your own details.')

    fine = [names[s['id']] for s in sections if s['id'] not in flagged and s['id'] != 'references' and _text_of(draft, s['id'])]
    lines = [INTRO, '']
    if issues:
        lines += ['Needs attention:'] + issues
    else:
        lines.append('No obvious gaps found in the basics. A full AI review can still sharpen the wording.')
    if fine:
        lines += ['', 'Looks fine: ' + ', '.join(fine) + '.']
    reply = '\n'.join(lines)
    return {'reply': reply, 'parts': [{'type': 'text', 'text': reply}], 'offline': True}
