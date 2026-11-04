"""Resume Builder template definitions: the sections, their guidance text and (for repeatable sections) their
fields. Kept apart from the analyser so the builder page, the AI assistant and the tests can all use it without
importing the whole resume-analysis engine.

Every section has a stable `id`. The AI assistant and the page refer to sections by id, never by their position
in the list, so reordering or adding a section cannot make a suggestion land in the wrong box.
"""

# Field schemas shared by every template's Work Experience / Education
# sections — kept as module-level constants so the three templates below
# don't each duplicate the same five field definitions.
_WORK_EXPERIENCE_FIELDS = [
    {'key': 'title', 'label': 'Job Title', 'placeholder': 'e.g. Sales Associate'},
    {'key': 'company', 'label': 'Company', 'placeholder': 'e.g. ABC Store'},
    {'key': 'location', 'label': 'Location', 'placeholder': 'e.g. Dubai, UAE'},
    {'key': 'dates', 'label': 'Dates', 'placeholder': 'e.g. Jan 2023 – Present'},
    {'key': 'description', 'label': 'Description', 'type': 'textarea',
     'placeholder': '- Describe what you did using action verbs\n- Include numbers and results where possible'},
]

_EDUCATION_FIELDS = [
    {'key': 'degree', 'label': 'Degree / Qualification', 'placeholder': 'e.g. Bachelor of Science in Information Technology'},
    {'key': 'institution', 'label': 'Institution', 'placeholder': 'e.g. AMA University'},
    {'key': 'location', 'label': 'Location', 'placeholder': 'e.g. Manila, Philippines'},
    {'key': 'dates', 'label': 'Dates', 'placeholder': 'e.g. 2020 – 2024'},
    {'key': 'details', 'label': 'Coursework / GPA (optional)', 'type': 'textarea',
     'placeholder': 'Relevant coursework, GPA if 3.0+, honors, etc.'},
]

RESUME_TEMPLATES = {
    'universal': {
        'title': 'Resume Builder',
        'icon': 'document',
        'description': 'One flexible template for any situation — students working while studying, career '
                        'changers, online-education graduates, and experienced professionals alike.',
        'sections': [
            {
                'id': 'contact',
                'name': 'Contact Information',
                'hint': 'Full Name\nEmail Address\nPhone Number\nCity, Country\nLinkedIn / Portfolio / Website (optional)',
            },
            {
                'id': 'summary',
                'name': 'Professional Summary / Objective',
                'hint': '[Your profession, field of study, or target role] with [X years experience / currently studying / '
                        'fresh graduate] in [your field].\n'
                        'Skilled in [top 3-5 skills relevant to the job].\n'
                        'Seeking a [target role] position to [what you want to contribute].\n\n'
                        'Examples:\n'
                        '• "Detail-oriented Accountant with 3 years of experience in financial reporting and tax preparation."\n'
                        '• "Final-year Computer Science student working part-time as a support technician, seeking a '
                        'software development internship."\n'
                        '• "Results-driven Sales Director with 10+ years leading teams and driving revenue growth."',
            },
            {
                'id': 'skills',
                'name': 'Skills',
                'hint': 'List your key skills relevant to the job you are applying for.\n'
                        'Group them into categories if possible:\n\n'
                        'Technical Skills: [e.g., Python, Excel, AutoCAD, QuickBooks, Adobe Photoshop]\n'
                        'Soft Skills: [e.g., Communication, Leadership, Problem Solving, Teamwork]\n'
                        'Languages: [e.g., English (Fluent), Arabic (Native), French (Intermediate)]\n'
                        'Certifications: [e.g., PMP, AWS Certified, IELTS Band 7, First Aid]',
            },
            {
                'id': 'experience',
                'name': 'Work Experience',
                'type': 'repeatable',
                'fields': _WORK_EXPERIENCE_FIELDS,
                'hint': 'Include full-time jobs, part-time work, internships, freelance projects, or volunteer roles — '
                        'if you\'re studying while working, that counts as real experience, so list it here too.\n'
                        '- Describe what you did using action verbs (Managed, Developed, Designed, Coordinated, etc.)\n'
                        '- Include numbers and results when possible (e.g., "Served 50+ customers daily")\n'
                        '- Focus on achievements, not just duties\n\n'
                        'Example: "Sales Associate — ABC Store | Dubai | Jan 2023 – Present\n'
                        '- Assisted 40+ customers daily and achieved 110% of monthly sales targets\n'
                        '- Trained 3 new team members on product knowledge and POS system"',
            },
            {
                'id': 'education',
                'name': 'Education',
                'type': 'repeatable',
                'fields': _EDUCATION_FIELDS,
                'hint': 'Include traditional degrees (completed or in progress), online courses, certifications, or '
                        'bootcamps (Coursera, edX, Udemy, etc.) — these all count as education. Add one entry per '
                        'qualification, most recent first.\n\n'
                        'Example: "Bachelor of Science in Information Technology — AMA University | 2024"\n'
                        'Example: "Google Data Analytics Certificate — Coursera | 2025"\n'
                        'Include relevant coursework or GPA only if it strengthens your application.',
            },
            {
                'id': 'projects',
                'name': 'Projects & Achievements',
                'hint': 'Anything that shows initiative or impact but doesn\'t fit under Work Experience or Education: '
                        'personal or academic projects, awards, leadership roles, competitions, publications, speaking '
                        'engagements, or board/club positions.\n\n'
                        'Project Name | Tools/Technologies Used\n'
                        '- Brief description of the project and your role\n'
                        '- Key results or outcomes\n\n'
                        'Or list awards and achievements:\n'
                        '• "Dean\'s List — 4 consecutive semesters"\n'
                        '• "Recipient, Company-wide Excellence Award, 2023"\n'
                        '• "Guest speaker, Regional Marketing Summit, 2022"\n'
                        '• "Volunteer of the Year — Red Cross Dubai Chapter"',
            },
            {
                'id': 'references',
                'name': 'References (Optional)',
                'hint': 'Reference Name — Position, Company\nEmail: [email]\nPhone: [phone]\n\n'
                        'Or simply write: "References available upon request"',
            },
        ],
    },
}
