# LiteLLM proxy onboarding — Quantum Readiness chatbot

This project routes **all** backend LLM calls through LiteLLM (`core/model_gateway.py`).
When `LITELLM_BASE_URL` and `LITELLM_API_KEY` are set, calls go to the shared proxy
`litellm-quantumchatbots` instead of direct provider SDKs.

## Prerequisites

| Environment | Proxy URL |
|-------------|-----------|
| VM (backend on same host) | `http://litellm-quantumchatbots:4000` |
| Local dev (off-VM) | `https://litellm-quantumchatbots.hybridintelligence.eu` |

Docker network on the VM: `litellm-quantumchatbots-net`.

## Step 1 — Virtual key

One virtual key per chatbot (usage/cost per bot). Request from Alexis Vrielynck or create in:

- UI: https://litellm-quantumchatbots.hybridintelligence.eu/ui/
- Admin credentials: see the proxy project `.env` on the VM

## Step 2 — Backend `.env`

```bash
cp backend/env.example backend/.env
```

```env
LITELLM_BASE_URL=http://litellm-quantumchatbots:4000
LITELLM_API_KEY=sk-<virtual-key>
LITELLM_DEFAULT_MODEL=claude-haiku-4-5
```

Use the **internal hostname** on the VM; use the **public HTTPS URL** when developing locally.

`backend/.env` is gitignored. Never commit keys.

## Step 3 — VM deploy (`docker-compose.vm.yml`)

The VM compose file attaches the backend to `caddy` and `litellm-quantumchatbots-net`:

```bash
./scripts/launch_docker.sh docker-compose.vm.yml
```

Or manually:

```bash
docker compose -f docker-compose.vm.yml up -d --build --force-recreate backend
```

## Step 4 — How the backend calls the proxy

No OpenAI SDK swap required: `litellm.acompletion()` is used with `api_base` + `api_key`
when proxy env vars are set. Model names must match `model_name` entries in the proxy
`config.yaml` (e.g. `claude-haiku-4-5`, `claude-sonnet-4-6`, `gpt-4o-mini`).

Local dev **without** the proxy: leave `LITELLM_BASE_URL` unset and set e.g. `MISTRAL_API_KEY`.

## Step 5 — Smoke test

```bash
docker exec qreadiness-backend getent hosts litellm-quantumchatbots
docker logs -f qreadiness-backend
docker logs -f litellm-quantumchatbots
```

Send a chat message from the UI and confirm a 200 in proxy logs.

## Common pitfalls

| Symptom | Fix |
|---------|-----|
| `ECONNREFUSED` | Backend not on `litellm-quantumchatbots-net`; restart container after joining network |
| `401 Unauthorized` | Wrong or revoked `LITELLM_API_KEY` |
| `400` / unknown model | `LITELLM_DEFAULT_MODEL` not in proxy `config.yaml` |
| Provider quota errors | Provider key on the **proxy** hit its cap — switch model or raise quota |

## Local docker-compose (optional embedded LiteLLM)

`docker-compose.yml` still includes a local `litellm` service for offline prototyping.
Production on the VM should use `docker-compose.vm.yml` and the shared proxy only.
