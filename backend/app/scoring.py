import re
import string

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.skill_ontology import canonical_skill, find_skill_evidence, normalize_skill

DEFAULT_SCORECARD = {
    "semantic": 15,
    "skills": 35,
    "experience": 25,
    "role_alignment": 15,
    "domain": 5,
    "education_certifications": 5,
}
ANALYSIS_VERSION = "advanced-evidence-v1"


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


def semantic_similarity(resume_text: str, reference: str) -> float:
    if not resume_text.strip() or not reference.strip():
        return 0.0
    word_vectors = TfidfVectorizer(stop_words="english", ngram_range=(1, 2)).fit_transform([resume_text, reference])
    char_vectors = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=12000).fit_transform([resume_text, reference])
    word_score = float(cosine_similarity(word_vectors[0:1], word_vectors[1:2])[0][0])
    char_score = float(cosine_similarity(char_vectors[0:1], char_vectors[1:2])[0][0])
    return round((word_score * 0.7 + char_score * 0.3) * 100, 2)


def advanced_score(
    resume_text: str,
    title: str,
    description: str,
    skills: list[str],
    experience_level: str | None,
    profile: dict,
    scorecard: dict | None = None,
    skill_priorities: dict | None = None,
    domain_keywords: list[str] | None = None,
    education_requirements: list[str] | None = None,
    certification_requirements: list[str] | None = None,
) -> tuple[float, list[str], dict, list[dict]]:
    weights = {**DEFAULT_SCORECARD, **(scorecard or {})}
    priorities = {canonical_skill(key): value for key, value in (skill_priorities or {}).items()}
    domains = domain_keywords or []
    education_requirements = education_requirements or []
    certification_requirements = certification_requirements or []
    reference = f"{title}\n{description}\n{' '.join(skills)}\n{' '.join(domains)}"
    semantic = semantic_similarity(resume_text, reference)

    evidence: list[dict] = []
    matched: list[str] = []
    skill_points = 0.0
    skill_total = 0.0
    missing_mandatory: list[str] = []
    priority_values = {"mandatory": 3.0, "preferred": 2.0, "optional": 1.0}
    for original in skills:
        canonical = canonical_skill(original)
        priority = priorities.get(canonical, priorities.get(normalize_skill(original), "preferred"))
        importance = priority_values.get(priority, 2.0)
        snippets = find_skill_evidence(resume_text, original)
        skill_total += importance
        if snippets:
            skill_points += importance
            matched.append(original)
        elif priority == "mandatory":
            missing_mandatory.append(original)
        evidence.append({"criterion": original, "category": "skill", "priority": priority, "matched": bool(snippets), "evidence": snippets, "score": 100 if snippets else 0})
    skills_score = skill_points / skill_total * 100 if skill_total else 100.0

    title_terms = [term for term in normalize(title).split() if len(term) > 2]
    title_hits = [term for term in title_terms if term in normalize(resume_text)]
    role_alignment = len(title_hits) / len(title_terms) * 100 if title_terms else 0.0
    evidence.append({"criterion": title, "category": "role_alignment", "priority": "preferred", "matched": bool(title_hits), "evidence": title_hits, "score": round(role_alignment, 2)})

    years = int(profile.get("maximum_stated_years") or 0)
    required_years = 5 if experience_level and "senior" in experience_level.lower() else 2 if experience_level and "mid" in experience_level.lower() else 0
    experience = 100.0 if required_years == 0 else min(100.0, years / required_years * 100)
    evidence.append({"criterion": f"{experience_level or 'Unspecified'} experience", "category": "experience", "priority": "preferred", "matched": experience >= 60, "evidence": [f"Maximum explicitly stated experience: {years} years"], "score": round(experience, 2)})

    domain_matches = [keyword for keyword in domains if find_skill_evidence(resume_text, keyword)]
    domain = len(domain_matches) / len(domains) * 100 if domains else semantic
    for keyword in domains:
        snippets = find_skill_evidence(resume_text, keyword)
        evidence.append({"criterion": keyword, "category": "domain", "priority": "preferred", "matched": bool(snippets), "evidence": snippets, "score": 100 if snippets else 0})

    education_text = " ".join(profile.get("education", [])).lower()
    certification_text = " ".join(profile.get("certifications", [])).lower()
    edu_items = education_requirements + certification_requirements
    edu_matches = [item for item in education_requirements if normalize_skill(item) in normalize_skill(education_text)]
    cert_matches = [item for item in certification_requirements if normalize_skill(item) in normalize_skill(certification_text)]
    education_certifications = len(edu_matches + cert_matches) / len(edu_items) * 100 if edu_items else 100.0
    for item in edu_items:
        matched_item = item in edu_matches or item in cert_matches
        evidence.append({"criterion": item, "category": "education_certification", "priority": "preferred", "matched": matched_item, "evidence": (profile.get("education", []) + profile.get("certifications", []))[:3] if matched_item else [], "score": 100 if matched_item else 0})

    components = {
        "semantic": round(semantic, 2),
        "skills": round(skills_score, 2),
        "experience": round(experience, 2),
        "role_alignment": round(role_alignment, 2),
        "domain": round(domain, 2),
        "education_certifications": round(education_certifications, 2),
        "scorecard_weights": weights,
        "missing_mandatory_count": len(missing_mandatory),
    }
    total = sum(float(components[key]) * float(weights[key]) / 100 for key in DEFAULT_SCORECARD)
    if missing_mandatory:
        total = min(total, 55.0)
    components["mandatory_cap_applied"] = bool(missing_mandatory)
    components["missing_mandatory_skills"] = missing_mandatory
    components["deterministic_total"] = round(total, 2)
    return round(max(0, min(100, total)), 2), matched, components, evidence


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
