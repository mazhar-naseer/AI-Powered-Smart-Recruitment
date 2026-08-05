import re
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from app.skill_ontology import canonical_skill, find_skill_evidence

PARSER_VERSION = "structured-parser-v1"


def sanitize_text(text: str) -> str:
    return "".join(character for character in text if character in "\n\r\t" or ord(character) >= 32)


def _pdf_text(path: Path) -> tuple[str, bool]:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if len(text.strip()) >= 80:
        return text, False
    try:
        import fitz
        import pytesseract
        from PIL import Image

        document = fitz.open(path)
        pages: list[str] = []
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            pages.append(pytesseract.image_to_string(image))
        ocr_text = "\n".join(pages)
        return ocr_text if len(ocr_text.strip()) > len(text.strip()) else text, True
    except Exception:
        return text, False


def extract_resume_text(path: Path, mime_type: str) -> tuple[str, bool]:
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or path.suffix.lower() == ".docx":
        document = Document(path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs), False
    return _pdf_text(path)


def structured_profile(text: str, skills: list[str], domain_keywords: list[str]) -> dict:
    clean = sanitize_text(text).strip()
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    emails = list(dict.fromkeys(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", clean)))
    phones = list(dict.fromkeys(re.findall(r"(?:\+?\d[\d\s().-]{7,}\d)", clean)))[:3]
    years = [int(value) for value in re.findall(r"(\d{1,2})\+?\s*(?:years?|yrs?)", clean, re.I)]
    education_terms = ("bachelor", "master", "phd", "doctorate", "university", "college", "bsc", "msc", "bs ", "ms ")
    certification_terms = ("certified", "certification", "certificate", "aws ", "azure ", "pmp", "cissp", "ccna")
    education = [line[:300] for line in lines if any(term in line.lower() for term in education_terms)][:10]
    certifications = [line[:300] for line in lines if any(term in line.lower() for term in certification_terms)][:10]
    skill_evidence = {canonical_skill(skill): find_skill_evidence(clean, skill) for skill in skills}
    detected_skills = [skill for skill, evidence in skill_evidence.items() if evidence]
    domain_evidence = {keyword: find_skill_evidence(clean, keyword) for keyword in domain_keywords}
    return {
        "headline": lines[0][:180] if lines else None,
        "emails": emails,
        "phones": phones,
        "maximum_stated_years": max(years or [0]),
        "education": education,
        "certifications": certifications,
        "detected_skills": detected_skills,
        "skill_evidence": skill_evidence,
        "domain_evidence": domain_evidence,
        "text_length": len(clean),
    }


def parse_resume(path: Path, mime_type: str, skills: list[str], domain_keywords: list[str]) -> tuple[str, dict, str]:
    raw_text, ocr_used = extract_resume_text(path, mime_type)
    text = sanitize_text(raw_text).strip()
    profile = structured_profile(text, skills, domain_keywords)
    profile["ocr_used"] = ocr_used
    profile["source_format"] = "docx" if path.suffix.lower() == ".docx" else "pdf"
    return text, profile, PARSER_VERSION

