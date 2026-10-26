# Deploying the Trial of the Nine Realms console

One process, standard library only (Python 3.12), no database, no build step: the console is committed pre-built in `web/`. State lives in one folder (`DATA_DIR`): runs, each agent's private memory, and the spend ledger.

## What you need

1. **The Runemark pack** (`dev_pack_E5/`). It is not in git. Mount it read-only at `/app/dev_pack_E5`, or bake it into a private image with `Dockerfile.with-pack`. Do not publish an image that contains it.
2. **A password**: `CONSOLE_PASSWORD`. The server refuses to listen beyond localhost without one, because anyone who can reach it could start runs on your API key.
3. **A model**: an API key, or Ollama.
4. **A persistent volume** at `/data` (or wherever `DATA_DIR` points). Without it, runs and memory are lost on every restart.

## Environment

Set these in the platform's secret store (or a local, gitignored `.env`; the platform's values win). Names only here; see `.env.example`.

| Variable | Meaning |
|---|---|
| `CONSOLE_PASSWORD` | HTTP Basic password for everything except `/api/health`. Any user name. **Required** when `HOST` is not localhost |
| `ANTHROPIC_API_KEY` | Claude. Metered |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | An OpenAI-compatible API. Metered unless the URL is localhost |
| `OLLAMA_HOST` | Where Ollama listens (default `http://127.0.0.1:11434`) |
| `LIVE=1`, `BUDGET_OWNER=<name>` | The budget owner's switches. A metered provider refuses to start without them |
| `PRICES_VERIFIED=1` | Set **only after** checking the prices in `config/runtime_config.json` against the provider's price page |
| `FINAL_ROUND=1` | Raises the ledger ceiling from $1.50 (development) to the $4 project cap. Leave unset until the final run |
| `DATA_DIR` | Volume path (the image sets `/data`) |
| `HOST`, `PORT` | Bind address and port. The image sets `0.0.0.0` and `8000`; platforms inject `PORT` |
| `MAX_QUEUED_RUNS` | Trials queued or running at once (default 3); more get a 429 |

Money rules that travel with the deployment: one $4 key for everything, $2.50 final-round reserve, $0.50 per case, Odin's briefing reserve protected on every call, and `data/ledger.json` refusing a run that could pass the ceiling. All of it applies to a run started from the console.

## Docker

```sh
# 1. with the pack beside the repo
docker compose up --build                       # http://localhost:8000, sign in with CONSOLE_PASSWORD
docker compose --profile local-models up --build   # also an Ollama container (then: docker compose exec ollama ollama pull qwen2.5:14b)

# 2. or one image with the pack inside (private registry only)
docker build -f Dockerfile.with-pack -t nine-realms .
docker run -p 8000:8000 -v nine-realms-data:/data \
  -e CONSOLE_PASSWORD=... -e ANTHROPIC_API_KEY=... -e LIVE=1 -e BUDGET_OWNER=... -e PRICES_VERIFIED=1 nine-realms
```

Health: `GET /api/health` (no password) returns `{"status": "ok", ...}`; the image's `HEALTHCHECK` uses it.

## Platforms

- **Render**: `render.yaml` is a blueprint (Docker, a 1 GB disk at `/data`, secrets entered in the dashboard). It builds `Dockerfile.with-pack`, so the repository you connect must be private and contain `dev_pack_E5/` (or switch to `Dockerfile` and upload the pack to a disk).
- **Fly.io / Railway / any Docker host**: build the image above, mount a volume at `/data`, set the variables, expose port 8000. TLS is the platform's job; Basic auth must only be used over HTTPS.
- **A plain VM**: `python server.py` behind Caddy or nginx with TLS and `HOST=127.0.0.1`; keep the server on localhost and let the proxy listen publicly.

A platform without a GPU cannot run useful local models: use an API provider there, and Ollama on your own machine.

## Before the real run

1. `python scripts/live_check.py` shows which providers are ready, the worst case of one case and the ledger.
2. Verify the prices (`config/runtime_config.json`, then `PRICES_VERIFIED=1`).
3. Open the console, pick the provider, run the E5 sample question once; read the Audit tab (spend, send-back, replay hash).
4. `python scripts/export_logs.py <case_id>` and commit `logs/` for the submission.

## Not covered

TLS termination, user accounts (one shared password), and horizontal scaling: runs are serialized in one process and the state is files on one volume.
