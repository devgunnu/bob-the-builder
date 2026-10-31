# Bob the Builder

Bob builds datasets from source material. Give it a goal and sources, review the proposed coverage plan, and run a build to generate and inspect rows. The app shows build progress, verification results, and a report with exports.

Sources include websites, uploaded files, and connected apps. The backend uses Amazon Bedrock for model calls and integrates with services including Firecrawl, Composio, Jev, and ScaleDown.

## Local setup

You need Python 3.12 or newer, Node.js and npm, and AWS credentials with access to the configured Bedrock models. The AWS deployment uses Node.js 22. Real builds also need the provider credentials required by the services and sources you use; these calls can incur charges.

1. Copy `.env.example` to `.env` in the repository root. Set your AWS region and the relevant provider keys there. See the comments in `.env.example` for model defaults and other settings. Never commit `.env`.

2. Start the backend from a terminal. In PowerShell:

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e ".[dev]"
   python -m uvicorn bob.api.app:app --host 127.0.0.1 --port 8000 --reload --env-file ../.env
   ```

   On macOS or Linux, activate the environment with `source .venv/bin/activate`; after installing dependencies, `./run.sh` starts the same server.

3. In a second terminal, start the frontend:

   ```sh
   cd frontend
   npm ci
   npm run dev
   ```

Open [http://localhost:5173](http://localhost:5173). Vite forwards `/api` requests to the backend on port 8000; set `BOB_API_PROXY` when starting Vite to use a different backend. The API documentation is at [http://localhost:8000/api/docs](http://localhost:8000/api/docs).

Local data is stored under `backend/runs` by default when the backend starts from that directory. Model settings can also be changed in the app's Account screen. Some services or features may be unavailable until their credentials are configured.

## Checks

From `backend`, with the development dependencies installed:

```sh
python -m pytest
```

From `frontend`:

```sh
npm run lint
npm run build
```

## Project layout

- `backend/` — FastAPI application, dataset pipeline, integrations, and tests.
- `frontend/` — React and Vite application; see [its README](frontend/README.md).
- `infra/` — AWS CDK stacks and deployment scripts; see the [deployment instructions](infra/README.md).
- `demo/` — example source material and scripts.

The AWS deployment instructions describe a shared, publicly reachable app without sign-in, as well as the deployment permissions and costs. Review them before deploying.
