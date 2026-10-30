<<<<<<< HEAD
# MphasisUtility
X011 Automation
=======
# AppDef to ABL Converter

Full-stack utility that converts AppDefinition/BotDefinition ZIP archives into ABL artifacts for Artemis, with a React/Vite frontend and a FastAPI backend.

## Repo Structure

- backend: FastAPI service for uploads, generation, and SSE progress
- frontend: React/Vite UI for upload, intent selection, and downloads

## Prerequisites

- Python 3.10+
- Node.js 18+

## Backend Setup

1. Create a virtual environment and install dependencies:

   ```bash
   cd backend
   python -m venv .venv
   .\.venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Create a backend/.env file with the required variables:

   ```env
   LLM_API_KEY=your_api_key
   AZURE_OPENAI_DOMAIN=your_azure_openai_domain
   AZURE_OPENAI_API_VERSION=your_api_version
   LLM_MODEL_NAME=your_model_name
   # Optional overrides
   LLM_COOKIE=
   ABL_MODEL=
   REASONING_MODEL=
   FLOW_MODEL=
   MAX_CONCURRENT_LLM_CALLS=4
   SESSION_TTL_SECONDS=86400
   VERIFY_ENABLED=true
   # Shared-password access control
   APP_PASSWORD_HASH=your_bcrypt_hash
   # Optional: separate admin password
   APP_ADMIN_PASSWORD_HASH=
   # Session signing secret
   SESSION_SECRET=your_random_secret
   AUTH_SESSION_TTL_SECONDS=28800
   AUTH_COOKIE_NAME=app_session
   AUTH_COOKIE_SAMESITE=lax
   AUTH_COOKIE_SECURE=
   SHARED_USER_EMAIL=team@local
   SHARED_ADMIN_EMAIL=admin@local
   ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
   RATE_LIMIT_PER_MINUTE=60
   ```

   Generate a bcrypt hash for the shared password:

   ```bash
   python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt'], deprecated='auto').hash('your-shared-password'))"
   ```

3. Start the API server:

   ```bash
   uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
   ```

- Health check: http://localhost:8000/health
- API base: http://localhost:8000/api

## Frontend Setup

1. Install dependencies:

   ```bash
   cd frontend
   npm install
   ```

2. Start the Vite dev server:

   ```bash
   npm run dev
   ```
## Backend
1. Run the virtual env
2. uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload


Frontend runs at http://localhost:5173 and is configured to call the backend on http://localhost:8000.

## Shared Password Notes

- Shared Password Key: "mphasis_kore_automation"


## Build

- Frontend production build:

  ```bash
  cd frontend
  npm run build
  ```

## Tests

- Backend tests:

  ```bash
  cd backend
  pytest
  ```

## Notes

- Uploads must be .zip archives containing appDefinition.json or botDefinition.json near the root of the archive.
- The backend keeps in-memory sessions with a configurable TTL.
>>>>>>> 3343583 (Initial commit)
