# SmartHire - Decisions, Assumptions, and Questions

This file prevents source conflicts and unstated assumptions from leaking into implementation.

## Decisions already supported by the user's instruction

1. **Backend:** FastAPI, not Flask.
2. **API style:** versioned REST API under `/api/v1` with Pydantic v2 schemas.
3. **Authentication:** JWT-based authentication with Applicant, Employer, and Admin RBAC.
4. **Architecture:** modular Clean Architecture with services, repositories, dependency injection, and SQLAlchemy 2.0/Alembic.
5. **Process:** planning documents first; implementation begins only after a later user command.
6. **Communication:** English or Roman Urdu only; no Hindi script.

## Recommended baseline decisions

These are recorded in the blueprint and can be changed before their implementation phase.

1. **Frontend:** React + TypeScript because the backend document explicitly says React and describes a REST-only backend.
2. **Primary design:** `Design Idea.png` (green/navy) because it covers landing, login, employer, applicant, and admin screens most completely. Use `designe idea 2.png` as secondary guidance.
3. **MVP resume input:** PDF only, following the original functional requirement and both upload screens. Keep the parser interface extensible for DOC/DOCX later.
4. **MVP scoring:** deterministic TF-IDF/cosine similarity plus required-skill coverage. Gemini is optional enrichment and does not determine whether an application succeeds.
5. **Processing:** persisted `processing/completed/failed` status with FastAPI BackgroundTasks for MVP and an interface ready for a durable queue.
6. **Database:** SQLite for development/single-instance academic deployment with PostgreSQL-compatible conventions.
7. **Deletion:** prefer soft deletion and auditable suspension; reserve irreversible purge for an explicit policy/workflow.
8. **Design-only features:** messages, interviews, reports, notifications, settings, and hiring-stage tabs are deferred until approved because they are not in the written MVP requirements.
9. **Optional job fields:** location, employment type, experience, education, salary, work mode are included in the schema/UI when practical because the designs display them, but only title, description, and required skills are mandatory.

## Questions to confirm before affected phases

None of these blocks the planning deliverables. Phase 0 should confirm them before code choices become expensive.

1. **Frontend stack:** Approve React + TypeScript, or do you want the academic Bootstrap/Jinja frontend despite the REST/React backend document?
2. **Visual theme:** Approve the green/navy `Design Idea.png` as primary, or prefer the indigo/navy `designe idea 2.png`?
3. **Testing framework:** May we use `pytest` (recommended for FastAPI), or is Python `unittest` a hard academic requirement?
4. **Gemini scope:** Should Gemini be enabled in the MVP, or should MVP ship with deterministic TF-IDF scoring and add Gemini afterward?
5. **Score formula:** Approve the proposed 75% TF-IDF + 25% required-skill coverage formula, or provide a different weighting/rubric.
6. **Production database:** Is the intended final deployment strictly a single-instance SQLite project, or should production use PostgreSQL while SQLite remains local?
7. **Deployment target:** Local Docker only, a specific VPS/cloud provider, or another hosting environment?
8. **User deletion:** Should admin deletion be recoverable soft delete by default, or truly permanent deletion including resumes and applications?
9. **Resume retention/privacy:** How long should original resumes and extracted text be retained, and should applicants be able to withdraw/delete them?
10. **Design-only modules:** Are messages, interview/hiring stages, notifications, reports, and settings required now or explicitly post-MVP?

## Risks requiring early attention

- **Source conflict:** implementing Flask/Jinja and FastAPI/React simultaneously would create unnecessary duplication. One stack must be authoritative.
- **BackgroundTasks durability:** an in-process task can be lost on restart; persisted state and an idempotent processor are essential.
- **AI reliability/privacy:** LLM output is non-deterministic and resumes contain personal data. Deterministic scoring, consent/configuration, timeouts, and redacted logs are required.
- **SQLite concurrency:** suitable for the academic/single-instance case but not a multi-instance production service.
- **Scanned resumes:** text-only PDF extraction will fail on image-only PDFs without OCR; MVP should return a clear failed/unsupported result.
- **Authorization:** employer resume downloads and applicant/application endpoints are high-risk IDOR surfaces and need negative tests.
- **Illustrative UI numbers:** sample percentages, candidates, metrics, and companies in the image collages are design placeholders, not functional requirements or seed data obligations.

## Phase approval format

When ready, a concise instruction is enough, for example:

> Approve Phase 0 decisions: React TypeScript, green/navy design, pytest, deterministic scoring first, SQLite for MVP. Start Phase 1.

Any undecided item can remain deferred if it does not affect the approved phase.
