import re


SKILL_ALIASES: dict[str, set[str]] = {
    "javascript": {"javascript", "java script", "js", "ecmascript"},
    "typescript": {"typescript", "type script", "ts"},
    "react": {"react", "reactjs", "react.js"},
    "node.js": {"node", "nodejs", "node.js"},
    "postgresql": {"postgresql", "postgres", "postgre sql", "psql"},
    "python": {"python", "python3", "python 3"},
    "fastapi": {"fastapi", "fast api"},
    "amazon web services": {"aws", "amazon web services", "amazon cloud"},
    "google cloud platform": {"gcp", "google cloud", "google cloud platform"},
    "microsoft azure": {"azure", "microsoft azure"},
    "kubernetes": {"kubernetes", "k8s"},
    "continuous integration": {"ci/cd", "cicd", "continuous integration", "continuous delivery"},
    "machine learning": {"machine learning", "ml"},
    "natural language processing": {"natural language processing", "nlp"},
    "large language models": {"large language model", "large language models", "llm", "llms"},
    "rest api": {"rest", "restful", "rest api", "rest apis"},
    "docker": {"docker", "containerization", "containers"},
}


def normalize_skill(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#.]+", " ", value.lower())).strip()


def canonical_skill(value: str) -> str:
    normalized = normalize_skill(value)
    for canonical, aliases in SKILL_ALIASES.items():
        if normalized == canonical or normalized in {normalize_skill(alias) for alias in aliases}:
            return canonical
    return normalized


def aliases_for(value: str) -> set[str]:
    canonical = canonical_skill(value)
    aliases = SKILL_ALIASES.get(canonical, {canonical})
    return {normalize_skill(item) for item in aliases | {canonical, value}}


def find_skill_evidence(text: str, skill: str) -> list[str]:
    evidence: list[str] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        normalized_line = normalize_skill(line)
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized_line) for alias in aliases_for(skill)):
            evidence.append(line[:300])
        if len(evidence) == 3:
            break
    return evidence

