from app.scoring import normalize, score_resume


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
