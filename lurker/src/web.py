import asyncio
import logging

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

app = FastAPI()

PBX_ARI_URL = "http://asterisk-pbx:8088"
PBX_ARI_AUTH = ("lurker", "lurkerpass")
CALL_DURATION = 10


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html>
<head>
  <title>Lurker</title>
  <style>
    body { font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #111; color: #eee; }
    .card { text-align: center; }
    h1 { font-size: 2rem; margin-bottom: 1.5rem; }
    button { font-size: 1.5rem; padding: 1rem 3rem; border: none; border-radius: 8px; cursor: pointer; background: #2a6; color: #fff; transition: background 0.2s; }
    button:hover { background: #3b7; }
    button:disabled { background: #555; cursor: not-allowed; }
    #status { margin-top: 1.5rem; font-size: 1.1rem; min-height: 1.5em; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Lurker</h1>
    <button id="btn" onclick="startCall()">Start Call</button>
    <div id="status"></div>
  </div>
  <script>
    async function startCall() {
      const btn = document.getElementById('btn');
      const status = document.getElementById('status');
      btn.disabled = true;
      status.textContent = 'Starting call...';
      try {
        const res = await fetch('/api/call', { method: 'POST' });
        const data = await res.json();
        if (data.ok) {
          let secs = """ + str(CALL_DURATION) + """;
          status.textContent = `Call active — ${secs}s remaining`;
          const iv = setInterval(() => {
            secs--;
            if (secs <= 0) { clearInterval(iv); status.textContent = 'Call ended — check logs for summary'; btn.disabled = false; }
            else { status.textContent = `Call active — ${secs}s remaining`; }
          }, 1000);
        } else {
          status.textContent = 'Error: ' + (data.error || 'unknown');
          btn.disabled = false;
        }
      } catch(e) {
        status.textContent = 'Error: ' + e.message;
        btn.disabled = false;
      }
    }
  </script>
</body>
</html>"""


@app.post("/api/call")
async def start_call():
    try:
        async with httpx.AsyncClient(auth=PBX_ARI_AUTH, timeout=10.0) as client:
            # Originate a call: alice calls bob through the normal dialplan
            resp = await client.post(
                f"{PBX_ARI_URL}/ari/channels",
                params={
                    "endpoint": "PJSIP/alice",
                    "extension": "bob",
                    "context": "from-internal",
                    "priority": "1",
                    "app": "lurker-originate",
                    "callerId": "alice",
                },
            )
            resp.raise_for_status()
            channel = resp.json()
            channel_id = channel["id"]

            logger.info("Originated call %s, will hang up in %ds", channel_id, CALL_DURATION)

            # Schedule hangup after CALL_DURATION seconds
            asyncio.get_event_loop().call_later(
                CALL_DURATION,
                lambda: asyncio.ensure_future(_hangup(channel_id)),
            )

            return {"ok": True, "channel_id": channel_id}

    except Exception as e:
        logger.error("Failed to start call: %s", e)
        return {"ok": False, "error": str(e)}


async def _hangup(channel_id: str):
    try:
        async with httpx.AsyncClient(auth=PBX_ARI_AUTH, timeout=10.0) as client:
            await client.delete(f"{PBX_ARI_URL}/ari/channels/{channel_id}")
            logger.info("Hung up channel %s after %ds", channel_id, CALL_DURATION)
    except Exception as e:
        logger.warning("Hangup failed for %s (may have already ended): %s", channel_id, e)
