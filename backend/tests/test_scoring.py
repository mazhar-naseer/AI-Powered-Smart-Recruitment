from app.scoring import advanced_score, normalize, score_resume
from app.skill_ontology import canonical_skill, find_skill_evidence


def test_normalize_removes_case_punctuation_and_extra_space():
    assert normalize("  Python, FASTAPI!  SQL ") == "python fastapi sql"


def test_score_is_bounded_repeatable_and_reports_skills():
    args = (
        "Python FastAPI SQL developer with REST API experience",
        "Python Developer",
        "Build REST APIs using Python",
        ["Python", "FastAPI", "SQL"],
    )
    first = score_resume(*args)
    second = score_resume(*args)
    assert first == second
    assert 0 <= first[0] <= 100
    assert first[1] == ["Python", "FastAPI", "SQL"]


def test_empty_resume_scores_zero():
    assert score_resume("", "Developer", "Build software", ["Python"]) == (0.0, [])


def test_skill_ontology_recognizes_common_aliases():
    assert canonical_skill("Postgres") == "postgresql"
    assert canonical_skill("JS") == "javascript"
    assert find_skill_evidence("Built services with PostgreSQL and JavaScript.", "Postgres")


def test_advanced_score_is_explainable_and_applies_mandatory_cap():
    score, matched, components, evidence = advanced_score(
        "Python developer with 6 years experience building FastAPI services.",
        "Senior Backend Engineer",
        "Build Python APIs using PostgreSQL in financial services.",
        ["Python", "FastAPI", "PostgreSQL"],
        "Senior",
        {"maximum_stated_years": 6, "education": [], "certifications": []},
        skill_priorities={"Python": "mandatory", "FastAPI": "mandatory", "PostgreSQL": "mandatory"},
        domain_keywords=["financial services"],
    )
    assert "Python" in matched and "FastAPI" in matched
    assert "PostgreSQL" not in matched
    assert score <= 55
    assert components["mandatory_cap_applied"] is True
    assert components["missing_mandatory_skills"] == ["PostgreSQL"]
    assert any(item["criterion"] == "PostgreSQL" and not item["matched"] for item in evidence)


def test_advanced_score_uses_configurable_weights():
    weights = {"semantic": 0, "skills": 100, "experience": 0, "role_alignment": 0, "domain": 0, "education_certifications": 0}
    score, _, components, _ = advanced_score(
        "Python FastAPI PostgreSQL", "Backend Engineer", "Build APIs", ["Python", "FastAPI", "PostgreSQL"], None,
        {"maximum_stated_years": 0, "education": [], "certifications": []}, scorecard=weights,
    )
    assert score == 100
    assert components["scorecard_weights"] == weights
