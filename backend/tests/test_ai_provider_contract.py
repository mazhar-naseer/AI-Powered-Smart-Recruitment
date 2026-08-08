"""The Gemini response contract.

`applications.ai_recommendation` is a VARCHAR(40). A model that answers the
recommendation field in prose used to reach the database verbatim and fail the
UPDATE, which discarded an otherwise complete analysis.
"""

import pytest

from app.ai_provider import RECOMMENDATIONS, AIAnalysis

# Column width of applications.ai_recommendation.
MAX_RECOMMENDATION = 40

VALID = {
    "summary": "Solid backend candidate.",
    "strengths": ["FastAPI"],
    "gaps": ["GraphQL"],
    "semantic_score": 68.0,
    "skills_score": 55.0,
    "experience_score": 60.0,
    "role_alignment_score": 62.0,
    "confidence": 0.8,
    "recommendation": "review",
}


def analysis(**overrides) -> AIAnalysis:
    return AIAnalysis.model_validate({**VALID, **overrides})


def test_the_vocabulary_fits_the_column():
    assert all(len(value) <= MAX_RECOMMENDATION for value in RECOMMENDATIONS)
    # Assigned by resume_processing rather than the model, but stored in the
    # same column, so it has to fit too.
    assert len("manual_review_required") <= MAX_RECOMMENDATION


@pytest.mark.parametrize("value", RECOMMENDATIONS)
def test_known_values_pass_through(value):
    assert analysis(recommendation=value).recommendation == value


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Strong_Match", "strong_match"),
        ("  weak_match  ", "weak_match"),
        ("strong match", "strong_match"),
        ("weak-match", "weak_match"),
        ("weak_match overall, but promising", "weak_match"),
        ("manual_review_required", "review"),
    ],
)
def test_near_misses_are_normalized(raw, expected):
    assert analysis(recommendation=raw).recommendation == expected


def test_the_prose_that_broke_production_degrades_to_review():
    prose = (
        "Consider for a Mid-Level Backend Developer role rather than Senior "
        "Backend Developer based on depth of experience."
    )
    assert len(prose) > MAX_RECOMMENDATION
    result = analysis(recommendation=prose)
    # Degraded rather than rejected: the scores and summary are still worth
    # keeping, and `review` is the token that asks for a human.
    assert result.recommendation == "review"
    assert result.semantic_score == 68.0


def test_the_schema_sent_to_gemini_pins_the_enum():
    """The enum is the API-level constraint; the coercion is the safety net."""
    schema = AIAnalysis.model_json_schema()
    field = schema["properties"]["recommendation"]
    enum = field.get("enum") or schema["$defs"][field["$ref"].split("/")[-1]]["enum"]
    assert sorted(enum) == sorted(RECOMMENDATIONS)


def test_scores_are_still_bounded():
    with pytest.raises(ValueError):
        analysis(semantic_score=180.0)
    with pytest.raises(ValueError):
        analysis(confidence=1.5)
