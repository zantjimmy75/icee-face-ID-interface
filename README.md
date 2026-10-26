# ICEE — Intelligent Camera-based Entry and Examination

A consent-based, operator-supervised identity verification starter. It is designed for controlled enrollment and check-in—not covert, public-space, or unattended surveillance. Face similarity is not proof of identity and must not alone determine access.

## What is included
- React/Vite responsive operator UI with dashboard, live scanner (camera permission via `getUserMedia`), enrollment, record search, reports, and settings.
- Django REST Framework API with MongoDB data repositories, Django password hashing, short-lived JWT access/refresh tokens, role checks, audit/verification logs, throttling, and API endpoints.
- Backend facial embeddings using InsightFace (ArcFace model) and cosine comparison. Embeddings are encrypted at rest with Fernet. Raw scan frames are processed in memory and not persisted.
- Compose file for MongoDB; the frontend/backend run separately.

## Development setup
1. Copy `backend/.env.example` to `backend/.env`, set a long random `BIOMETRIC_ENCRYPTION_KEY` (generate using `Fernet.generate_key()`), `DJANGO_SECRET_KEY`, and Mongo settings.
2. Start MongoDB: `docker compose up -d mongodb`.
3. Backend: `cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python manage.py migrate && python manage.py createsuperuser && python manage.py runserver 0.0.0.0:8000`.
4. Frontend: `cd frontend && npm install && npm run dev -- --host 0.0.0.0`.

Set `VITE_API_BASE=http://localhost:8000/api` in `frontend/.env.local` if needed. Camera access requires HTTPS except on localhost. InsightFace downloads model weights on first initialization; use only approved, pinned model assets in production.

## API overview
- `POST /api/auth/login/` — username/password, returns short-lived JWT access and refresh tokens
- `POST /api/auth/refresh/` — rotate/refresh an access token
- `POST /api/individuals/` — create a consented individual record (multipart form)
- `GET /api/individuals/`, `GET/PATCH/DELETE /api/individuals/{id}/`
- `POST /api/face/enroll/` — image + `individual_id`, consent affirmed
- `POST /api/face/verify/` — image + `individual_id` (1:1)
- `POST /api/face/identify/` — image (1:N)
- `POST /api/checkins/` — `individual_id`, event, verified status
- `GET /api/reports/attendance/` — JSON report; append `?format=csv` for authorized CSV export

## Safety, deployment and limitations
This is a starter, not a certified identity product. Conduct a privacy impact assessment, establish a lawful basis and retention schedule, provide an equally usable non-biometric path, obtain informed consent, validate accuracy and demographic performance in the real environment, and use independent security review before any real deployment. Keep the matching threshold calibrated to your use case; this code defaults to conservative review rather than automatic allow/deny. Liveness is deliberately not represented as implemented: integrate and validate a dedicated presentation-attack detection (PAD) service before relying on it, and show its result separately from identity matching. Do not interpret similarity as calibrated confidence. Use TLS, managed secrets/KMS, private networking, strict CORS, backups/deletion procedures, monitoring, and production-grade rate limits in deployment.

Mongo stores personal records, encrypted embeddings, and minimized logs. Django's user/auth tables use SQLite in development and can be moved to PostgreSQL for production. Browser code never receives the face database or embeddings. Uploaded enrollment images are not persisted by this API. Implement a reviewed retention/deletion schedule before production.
