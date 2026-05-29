# Running on Qwen Cloud + Alibaba Cloud

The hackathon requires two things this guide covers: (1) the agent must call **Qwen
models on Qwen Cloud**, and (2) the backend must **run on Alibaba Cloud**, with a
short recording as proof of deployment.

## 1. Qwen model access (Qwen Cloud / DashScope)

1. Create an Alibaba Cloud account and enable **Model Studio (DashScope)**.
2. Create an API key. Export it:

   ```bash
   export DASHSCOPE_API_KEY="sk-..."
   ```

3. `QwenClient` already points at the DashScope OpenAI-compatible endpoint
   (`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`) and defaults to
   `qwen-plus`. Switch to `qwen-max` for the hardest reasoning by passing
   `QwenClient(model="qwen-max")`.

```bash
pip install -r requirements.txt   # installs the openai SDK for the live client
```

## 2. Deploy the backend on Alibaba Cloud

Wrap `AutopilotAgent` in a tiny HTTP service (FastAPI/Flask) that accepts an
incident string and returns the `RemediationReport` plus the audit JSONL. Any of
these Alibaba Cloud targets satisfies the "backend runs on Alibaba Cloud" rule:

- **Function Compute (FC)** — serverless; deploy the handler, set `DASHSCOPE_API_KEY`
  as an environment variable. Lowest-overhead option.
- **Serverless App Engine (SAE)** or **ACK (Kubernetes)** — container the repo,
  push to **Alibaba Cloud Container Registry (ACR)**, deploy.
- **ECS** — a single VM running the service behind nginx, simplest to screen-record.

Minimal container:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt fastapi uvicorn
ENV DASHSCOPE_API_KEY=""
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
```

Keep `allow_destructive=()` empty by default in any internet-facing deployment, and
keep `usd_cap` small. Add a real `ToolSpec.host` per tool so the egress allowlist is
meaningful against your actual Alibaba Cloud service endpoints.

## 3. Proof-of-deployment recording (required)

Record a short screen capture that clearly shows the backend running on Alibaba
Cloud, for example:

- the Alibaba Cloud console (FC function / SAE app / ECS instance) showing the
  service deployed and healthy, then
- a `curl` to the public endpoint returning a real `RemediationReport` + audit JSONL.

Upload it per the hackathon instructions alongside the ~3-minute demo video.

## 4. Submission checklist (Qwen Cloud hackathon)

- [x] Public code repo with an open-source license — this repo (MIT).
- [x] Architecture diagram — `docs/architecture.md`.
- [x] Text description of features — `README.md`.
- [ ] Uses Qwen models on Qwen Cloud — set `DASHSCOPE_API_KEY`, run `QwenClient`.
- [ ] Proof of Alibaba Cloud deployment recording — section 3 above (you record it).
- [ ] ~3-minute demo video on YouTube/Vimeo/Facebook — (you record it).
- [ ] Track: **Autopilot Agent**.
