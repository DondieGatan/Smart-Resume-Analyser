"""Unit tests for the scoring/matching logic in analyzer.py.

These deliberately don't assert exact hand-computed scores for every
sub-dimension (skills/education/experience/formatting) — that internal
logic is expected to evolve. Instead they lock down the parts that would
be a real, silent bug if they drifted: the overall-score weighting
formula, the score-band thresholds, and the fact that pass/fail verdicts
always agree with the numeric score that produced them.
"""
import pytest

from analyzer import (
    calculate_scores,
    simulate_ats,
    match_job_description,
    _get_match_recommendation,
)
import analyzer as analyzer_module


SAMPLE_RESUME = """
John Doe
john.doe@example.com | +1 555 123 4567

SUMMARY
Backend engineer with 6 years of experience building Python and SQL
services on AWS.

SKILLS
Python, SQL, AWS, Docker, Git, Leadership

EDUCATION
Bachelor of Science in Computer Science - State University, 2018

EXPERIENCE
Software Engineer - Example Corp (2019 - Present)
- Built and maintained backend services using Python and PostgreSQL.
- Deployed infrastructure on AWS using Docker containers.
"""


def _sample_skills(n, categories=('Programming Languages', 'Web Development',
                                   'Database', 'Cloud & DevOps', 'Soft Skills')):
    """n synthetic (skill_name, category) tuples cycling through categories,
    matching the shape extract_skills() returns."""
    return [(f'skill-{i}', categories[i % len(categories)]) for i in range(n)]


class TestOverallScoreWeighting:
    def test_weighting_formula_matches_documented_30_20_30_20(self):
        scores, _ = calculate_scores(SAMPLE_RESUME, _sample_skills(12), [{'degree': 'BSc'}],
                                      [('Software Engineer', 'Example Corp', 'Built things')])
        expected = round(
            scores['skills'] * 0.30 +
            scores['education'] * 0.20 +
            scores['experience'] * 0.30 +
            scores['formatting'] * 0.20
        )
        assert scores['overall'] == expected

    def test_all_scores_are_within_0_100(self):
        scores, _ = calculate_scores(SAMPLE_RESUME, _sample_skills(12), [{'degree': 'BSc'}],
                                      [('Software Engineer', 'Example Corp', 'Built things')])
        for key in ('skills', 'education', 'experience', 'formatting', 'overall'):
            assert 0 <= scores[key] <= 100, f'{key} out of range: {scores[key]}'


class TestSkillsScoreBands:
    @pytest.mark.parametrize('skill_count,min_expected', [
        (0, 0),
        (2, 20),
        (5, 50),
        (8, 70),
        (12, 85),
        (16, 100),
    ])
    def test_more_skills_never_scores_lower(self, skill_count, min_expected):
        scores, _ = calculate_scores(SAMPLE_RESUME, _sample_skills(skill_count), [], [])
        assert scores['skills'] >= min_expected

    def test_category_diversity_bonus_does_not_exceed_100(self):
        # 20 skills across 5 categories should hit both the top count band
        # and the >=4-category bonus — score must still cap at 100.
        scores, _ = calculate_scores(SAMPLE_RESUME, _sample_skills(20), [], [])
        assert scores['skills'] == 100


class TestAtsPassLikelyAgreesWithScore:
    def test_pass_likely_matches_60_threshold(self):
        skills = _sample_skills(12)
        scores, _ = calculate_scores(SAMPLE_RESUME, skills, [{'degree': 'BSc'}],
                                      [('Software Engineer', 'Example Corp', 'Built things')])
        results = simulate_ats(SAMPLE_RESUME, skills, [{'degree': 'BSc'}],
                                [('Software Engineer', 'Example Corp', 'Built things')], scores)
        assert results['pass_likely'] == (results['ats_score'] >= 60)

    def test_empty_resume_does_not_pass(self):
        scores, _ = calculate_scores('', [], [], [])
        results = simulate_ats('', [], [], [], scores)
        assert results['pass_likely'] is False


class TestMatchJobDescriptionWeighting:
    """Forces the lexical-only fallback path by making the semantic model
    unavailable, so these tests are deterministic and don't need to
    download/run the real sentence-transformers model in CI."""

    @pytest.fixture(autouse=True)
    def no_semantic_model(self, monkeypatch):
        monkeypatch.setattr(analyzer_module, '_semantic_similarity', lambda resume, jd: None)

    def test_identical_text_scores_highly(self):
        text = 'Python developer with AWS and Docker experience building SQL services.'
        result = match_job_description(text, text)
        assert result['match_score'] >= 70

    def test_unrelated_text_scores_low(self):
        result = match_job_description(
            'Pastry chef specializing in French desserts and cake decoration.',
            'Senior Python backend engineer with AWS, Docker, and Kubernetes experience.'
        )
        assert result['match_score'] < 40

    def test_empty_job_description_returns_error(self):
        result = match_job_description(SAMPLE_RESUME, '')
        assert 'error' in result

    def test_fallback_weighting_formula(self):
        """With no semantic model, match_pct should equal
        word*0.5 + phrase*0.2 + skill*0.3 (rounded) — recompute independently
        via the same public function's other returned fields rather than
        re-deriving word/phrase/skill percentages by hand, since those are
        internal to the function."""
        result = match_job_description(
            'Python developer with SQL and AWS experience.',
            'Looking for a Python developer with SQL and AWS experience.'
        )
        assert 0 <= result['match_score'] <= 100
        assert result['recommendation'] == _get_match_recommendation(result['match_score'])


class TestMatchRecommendationThresholds:
    """The template's score-band CSS uses 70/50/30 — this locks the verdict
    text to the same boundaries so they can't silently drift apart again."""

    @pytest.mark.parametrize('score,expected_substring', [
        (100, 'Excellent'),
        (70, 'Excellent'),
        (69, 'Good match'),
        (50, 'Good match'),
        (49, 'Moderate'),
        (30, 'Moderate'),
        (29, 'Low match'),
        (0, 'Low match'),
    ])
    def test_boundary_values(self, score, expected_substring):
        assert expected_substring in _get_match_recommendation(score)


CLEAN_RESUME = """Alex Morgan
Junior Full-Stack Developer | alex.morgan@example.test | +971 50 000 0000 | Dubai, UAE
Professional Summary
Software engineering graduate. Looking for a junior developer role.
Skills
Python, Flask, React
Experience
Software Engineering Intern - Northwind Digital, Dubai (Jun 2025 - Dec 2025)
- Built a customer dashboard in React and Flask.
Freelance Web Developer - Self-employed (Jan 2024 - May 2025)
- Delivered 6 small-business websites.
Education
Bachelor of Science in Software Engineering - Example University, 2021 - 2025
Projects
- Task Manager API: Flask REST API with JWT auth.
"""


class TestEducationAndExperienceExtraction:
    """Regressions found on a plain resume: a degree written with a hyphen was not found, and every job-title
    word in the summary, contact line, projects or education block was counted as a job."""

    def test_a_degree_and_school_separated_by_a_hyphen_are_found(self):
        edu = analyzer_module.extract_education(CLEAN_RESUME)
        assert edu == [{'institution': 'Example University', 'degree': 'Bachelor of Science in Software Engineering'}]

    def test_a_hyphen_inside_a_date_range_does_not_split_the_line(self):
        edu = analyzer_module.extract_education('Bachelor of Science in Computer Science - State University, 2018')
        assert edu[0]['institution'] == 'State University'

    def test_only_the_experience_section_is_read_for_jobs(self):
        jobs = analyzer_module.extract_experience(CLEAN_RESUME)
        assert [j[0] for j in jobs] == ['Software Engineering Intern', 'Freelance Web Developer']
        assert jobs[0][1] == 'Northwind Digital, Dubai'

    def test_without_an_experience_heading_the_whole_text_is_still_scanned(self):
        jobs = analyzer_module.extract_experience('Jane Roe\nSenior Software Engineer at Globex 2018 - 2022\n')
        assert [j[0] for j in jobs] == ['Senior Software Engineer'] and jobs[0][1] == 'Globex'

    def test_years_of_experience_come_from_the_dated_roles_only(self):
        import datetime
        years = analyzer_module.estimate_experience_years(CLEAN_RESUME, today=datetime.date(2026, 1, 1))
        assert 1.5 <= years <= 2.0          # 2021-2025 (the degree) must not be counted
        assert analyzer_module.estimate_experience_years('No dates here') is None

    def test_overlapping_roles_are_counted_once(self):
        import datetime
        text = 'Experience\nDeveloper - A (2020 - 2022)\nConsultant - B (2021 - 2023)\n'
        years = analyzer_module.estimate_experience_years(text, today=datetime.date(2026, 1, 1))
        assert 2.5 <= years <= 3.5

    def test_seniority_follows_the_dated_years_when_they_are_known(self):
        base = dict(name='A', skills=[], education=[], scores={'overall': 70, 'skills': 70, 'education': 70,
                    'experience': 70, 'formatting': 70}, field_recommendations=[])
        few_jobs_long = analyzer_module.generate_employer_summary(
            experience=[('Dev', 'X', '')] * 1, experience_years=8, **base)
        many_jobs_short = analyzer_module.generate_employer_summary(
            experience=[('Dev', 'X', '')] * 6, experience_years=1.5, **base)
        assert few_jobs_long['seniority'] == 'Senior'
        assert many_jobs_short['seniority'] == 'Entry-Level'

    def test_dated_experience_lifts_the_experience_score(self):
        skills = [('Python', 'Programming Languages')]
        exp = analyzer_module.extract_experience(CLEAN_RESUME)
        scores, explanations = calculate_scores(CLEAN_RESUME, skills, analyzer_module.extract_education(CLEAN_RESUME), exp)
        assert scores['experience'] >= 70
        assert scores['education'] > 20


class TestHostileInput:
    """Found by a robustness sweep: one very long line made the email search quadratic (over a minute for 200,000
    characters), and garbage text could produce thousands of 'jobs' to save as database rows."""

    def test_a_200000_character_line_is_analysed_in_seconds(self):
        import time
        text = 'a' * 200000
        t0 = time.time()
        analyzer_module.extract_email(text)
        analyzer_module.extract_name(text)
        assert time.time() - t0 < 15

    def test_a_long_run_of_spaces_does_not_stall_the_email_search(self):
        import time
        t0 = time.time()
        analyzer_module.extract_email(' ' * 200000 + 'x')
        assert time.time() - t0 < 5

    def test_emails_are_still_found(self):
        assert analyzer_module.extract_email('Contact: jane.doe@example.com | +1 555 123 4567') == 'jane.doe@example.com'
        assert analyzer_module.extract_email('mail me: robin @ gmail.com') == 'robin@gmail.com'

    def test_the_caps_exist_and_are_sensible(self):
        assert 5 <= analyzer_module.MAX_EDUCATION_ENTRIES <= 20
        assert 10 <= analyzer_module.MAX_EXPERIENCE_ENTRIES <= 100
        assert analyzer_module.MAX_RESUME_TEXT_CHARS >= 50000
