import re
import string

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def hybrid_score(
    deterministic_score: float,
    ai_score: float,
    ai_confidence: float,
    maximum_ai_weight: float = 0.35,
    disagreement_threshold: float = 25.0,
) -> tuple[float, dict[str, float | bool]]:
    """Blend an auditable score with confidence-limited AI influence and review guardrails."""
    confidence = max(0.0, min(1.0, ai_confidence))
    ai_weight = max(0.0, min(0.5, maximum_ai_weight)) * confidence
    deterministic_weight = 1 - ai_weight
    difference = abs(deterministic_score - ai_score)
    result = deterministic_score * deterministic_weight + ai_score * ai_weight
    return round(max(0, min(100, result)), 2), {
        "deterministic_weight": round(deterministic_weight * 100, 2),
        "ai_weight": round(ai_weight * 100, 2),
        "ai_confidence": round(confidence * 100, 2),
        "score_difference": round(difference, 2),
        "manual_review_required": difference >= disagreement_threshold,
    }


def normalize(text: str) -> str:
    table = str.maketrans({char: " " for char in string.punctuation})
    return re.sub(r"\s+", " ", text.lower().translate(table)).strip()


def score_resume(
    resume_text: str, title: str, description: str, skills: list[str]
) -> tuple[float, list[str]]:
    clean_resume = normalize(resume_text)
    clean_reference = normalize(f"{title} {description} {' '.join(skills)}")
    if not clean_resume or not clean_reference:
        return 0.0, []
    vectors = TfidfVectorizer(stop_words="english").fit_transform([clean_resume, clean_reference])
    tfidf_score = float(cosine_similarity(vectors[0:1], vectors[1:2])[0][0]) * 100
    matched = [skill for skill in skills if normalize(skill) in clean_resume]
    skill_score = len(matched) / len(skills) * 100 if skills else 0
    return round(min(100, max(0, tfidf_score * 0.75 + skill_score * 0.25)), 2), matched


def detailed_score(resume_text: str, title: str, description: str, skills: list[str], experience_level: str | None = None) -> tuple[float, list[str], dict]:
    clean_resume = normalize(resume_text)
    reference = normalize(f"{title} {description} {' '.join(skills)}")
    if not clean_resume:
        return 0.0, [], {"semantic": 0, "skills": 0, "title": 0, "experience": 0}
    vectors = TfidfVectorizer(stop_words="english", ngram_range=(1, 2)).fit_transform([clean_resume, reference])
    semantic = float(cosine_similarity(vectors[0:1], vectors[1:2])[0][0]) * 100
    matched = [skill for skill in skills if normalize(skill) in clean_resume]
    skill_score = len(matched) / len(skills) * 100 if skills else 100
    title_terms = [term for term in normalize(title).split() if len(term) > 2]
    title_score = sum(term in clean_resume for term in title_terms) / len(title_terms) * 100 if title_terms else 0
    years = max([int(value) for value in re.findall(r"(\d{1,2})\+?\s+years?", clean_resume)] or [0])
    required = 5 if experience_level and "senior" in experience_level.lower() else 2 if experience_level else 0
    experience_score = 100 if required == 0 else min(100, years / required * 100)
    parts = {"semantic": round(semantic, 2), "skills": round(skill_score, 2), "title": round(title_score, 2), "experience": round(experience_score, 2)}
    final = semantic * .5 + skill_score * .3 + title_score * .1 + experience_score * .1
    return round(max(0, min(100, final)), 2), matched, parts
