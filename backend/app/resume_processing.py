import time
from datetime import UTC, datetime

from app.config import get_settings
from app.database import SessionLocal
from app.models import Application, ApplicationStatus
from app.ai_provider import analyze_with_gemini
from app.resume_parser import PARSER_VERSION, parse_resume, structured_profile
from app.scoring import ANALYSIS_VERSION, advanced_score, hybrid_score
from app.object_storage import resume_storage
from app.logging_config import get_logger


logger = get_logger(__name__)

def sanitize_extracted_text(text: str) -> str:
    """Remove database-invalid PDF control bytes while preserving readable layout."""
    return "".join(character for character in text if character in "\n\r\t" or ord(character) >= 32)


def process_application(application_id: str, force: bool = False) -> None:
    started = time.perf_counter()
    db = SessionLocal()
    try:
        application = db.get(Application, application_id)
        if not application:
            logger.warning("Analysis skipped: application %s no longer exists", application_id)
            return
        if application.status == ApplicationStatus.COMPLETED and not force:
            logger.info("Analysis skipped: application %s already completed", application_id)
            return
        logger.info("Analyzing application %s (force=%s)", application_id, force)
        text = (application.resume.extracted_text or "").strip()
        if text:
            profile = structured_profile(text, application.job.required_skills, application.job.domain_keywords or [])
            parser_version = application.parser_version or PARSER_VERSION
        else:
            # Remote objects have no path, so the store yields a temporary one
            # that is removed when the block exits.
            with resume_storage.open(application.resume.storage_key) as resume_path:
                text, profile, parser_version = parse_resume(
                    resume_path,
                    application.resume.mime_type,
                    application.job.required_skills,
                    application.job.domain_keywords or [],
                )
        if len(text) < 30:
            raise ValueError("The PDF contains insufficient extractable text")
        score, matched, components, evidence = advanced_score(
            text,
            application.job.title,
            application.job.description,
            application.job.required_skills,
            application.job.experience_level,
            profile,
            application.job.scorecard,
            application.job.skill_priorities,
            application.job.domain_keywords,
            application.job.education_requirements,
            application.job.certification_requirements,
        )
        components["scorecard_snapshot"] = {
            "weights": application.job.scorecard,
            "skill_priorities": application.job.skill_priorities,
            "domain_keywords": application.job.domain_keywords,
            "education_requirements": application.job.education_requirements,
            "certification_requirements": application.job.certification_requirements,
        }
        components["prompt_version"] = "gemini-evidence-v1"
        settings = get_settings()
        ai_error = None
        try:
            ai = analyze_with_gemini(
                text,
                f"{application.job.title}\n{application.job.description}",
                application.job.required_skills,
                profile,
            )
        except Exception as exc:
            # AI enrichment must never invalidate deterministic resume processing.
            ai = None
            ai_error = f"{type(exc).__name__}: {exc}"[:500]
            # Warning, not exception: the deterministic score still stands, so
            # this degrades the result rather than failing the analysis.
            logger.warning(
                "AI enrichment failed for application %s, using deterministic score only: %s",
                application_id,
                ai_error,
            )
        application.resume.extracted_text = text
        application.structured_profile = {
            **profile,
            "ai_evidence_findings": ai.evidence_findings if ai else [],
            "ai_risk_flags": ai.risk_flags if ai else [],
        }
        application.evidence_matrix = evidence
        application.analysis_version = ANALYSIS_VERSION
        application.parser_version = parser_version
        application.deterministic_score = score
        application.ai_score = round(ai.semantic_score, 2) if ai else None
        application.ai_status = "completed" if ai else "failed" if ai_error else "not_configured"
        application.ai_error = ai_error
        hybrid_meta = {}
        if ai:
            application.final_score, hybrid_meta = hybrid_score(
                score,
                ai.semantic_score,
                ai.confidence,
                settings.gemini_weight,
                settings.hybrid_disagreement_threshold,
            )
        else:
            application.final_score = score
        application.matched_skills = matched
        components["deterministic_total"] = score
        if ai:
            components["gemini_semantic"] = round(ai.semantic_score, 2)
            components["gemini_skills"] = round(ai.skills_score, 2)
            components["gemini_experience"] = round(ai.experience_score, 2)
            components["gemini_role_alignment"] = round(ai.role_alignment_score, 2)
            components.update(hybrid_meta)
        application.component_scores = components
        missing = [skill for skill in application.job.required_skills if skill not in matched]
        application.ai_summary = ai.summary if ai else f"Matched {len(matched)} of {len(application.job.required_skills)} required skills. Evidence-based score: {score}%."
        application.ai_strengths = ai.strengths if ai else matched[:5]
        application.ai_gaps = ai.gaps if ai else missing[:5]
        application.ai_recommendation = (
            "manual_review_required"
            if hybrid_meta.get("manual_review_required")
            else ai.recommendation
        ) if ai else ("strong_match" if score >= 75 else "review" if score >= 50 else "weak_match")
        application.ai_provider = settings.gemini_model if ai else "deterministic-fallback"
        application.status = ApplicationStatus.COMPLETED
        application.processed_at = datetime.now(UTC)
        application.processing_error = None
        db.commit()
        logger.info(
            "Analyzed application %s in %.2fs: final=%s deterministic=%s ai=%s matched=%d/%d",
            application_id,
            time.perf_counter() - started,
            application.final_score,
            score,
            application.ai_status,
            len(matched),
            len(application.job.required_skills),
        )
    except Exception as exc:
        db.rollback()
        # exception() rather than error(): without the traceback there is no way
        # to tell a malformed PDF from a bug in the scorer.
        logger.exception(
            "Analysis failed for application %s after %.2fs",
            application_id,
            time.perf_counter() - started,
        )
        application = db.get(Application, application_id)
        if application:
            application.status = ApplicationStatus.FAILED
            application.processing_error = str(exc)[:500]
            db.commit()
        else:
            logger.error(
                "Could not mark application %s failed: row is gone", application_id
            )
    finally:
        db.close()
