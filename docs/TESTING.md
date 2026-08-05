# SmartHire Test Plan and Acceptance Suite

## Automated commands

| Layer | Command | Coverage |
|---|---|---|
| Backend | `cd backend && ../.venv/bin/pytest --cov=app` | Auth, RBAC, jobs, ownership, applications, upload validation, resume access, admin, scoring |
| Frontend unit | `cd frontend && npm run test` | Client authentication storage and isolated UI logic |
| Frontend build | `cd frontend && npm run build` | Strict TypeScript and optimized production bundle |
| Browser E2E | `cd frontend && npx playwright test` | Public journeys and browser interaction; extend for environment-seeded role journeys |

## Manual end-to-end test cases

### Authentication and authorization

1. Register an Applicant with a unique email; expect success and login availability.
2. Register an Employer with company name; expect success.
3. Attempt duplicate email with different casing; expect `409`.
4. Attempt public Admin registration; expect `422`.
5. Login with bad password; expect generic failure without account disclosure.
6. Login as every role; expect correct dashboard.
7. Logout and revisit protected URL; expect login redirect.
8. Use an Applicant token on Employer/Admin APIs; expect `403`.
9. Suspend an active user; existing access and refresh sessions must stop working.

### Employer and job management

10. Create a job with title, 20+ character description, and skills; expect it in My Jobs and Applicant board.
11. Submit invalid/empty job fields; expect visible field/API errors.
12. Edit job and close it; expect it removed from Applicant board.
13. Reopen job; expect it visible again.
14. Employer B tries to edit Employer A's job ID; expect `404`.
15. Delete a job; expect it hidden from standard lists.

### Applicant and resume processing

16. Search jobs by title/description; expect relevant open results.
17. Open job detail; expect company, description, skill chips, and metadata.
18. Upload `.txt`, renamed non-PDF, and file above 5 MB; expect rejection.
19. Upload valid text-based PDF; expect `202`, then completed score.
20. Apply to same job again; expect `409` and no duplicate record/file.
21. Upload image-only PDF; expect clear processing failure because OCR is deferred.
22. View My Applications; expect only current applicant's records.

### Ranking and protected files

23. Submit multiple resumes to one job; expect completed candidates ordered by score descending.
24. Confirm score is 0-100 and matched skills are displayed.
25. Job owner downloads candidate PDF; expect original content and safe filename.
26. Another Employer attempts the same application download URL; expect `404`.
27. Applicant attempts employer download endpoint; expect `403`.

### Admin and moderation

28. Admin dashboard totals should match database fixtures.
29. Filter/view all non-admin users.
30. Suspend/reactivate a user; expect badge and access behavior to update.
31. View all active/closed jobs and remove spam; expect removal from every normal job list.
32. Verify moderation, status changes, logins, and downloads create audit entries.

### Responsive, accessibility, and resilience

33. Test landing, auth, dashboards, job board, tables, and forms at 1440, 1024, 768, and 375 px.
34. Complete login, job creation, search, and upload using keyboard only.
35. Verify visible focus, input labels, readable contrast, and non-color status text.
36. Stop backend while frontend is open; expect controlled errors, not blank screens.
37. Restart during processing; persisted status must remain diagnosable and safely retryable operationally.
38. Verify secrets, passwords, JWTs, and extracted resume text never appear in logs.

## Production release gate

- All automated suites pass.
- No critical/high dependency or application security finding remains unexplained.
- TLS, strong secret, allowed origins, persistent volumes, health checks, migration, backup, restore, rollback, and admin provisioning have been exercised in staging.
- Privacy owner approves resume consent, retention, deletion, and third-party AI policy.

