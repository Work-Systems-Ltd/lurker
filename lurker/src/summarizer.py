import logging

import httpx

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """Summarize this phone call transcript concisely. Include:
- Participants (if identifiable)
- Main topics discussed
- Key decisions or action items
- Outcome

Transcript:
{transcript}

Summary:"""


class Summarizer:
    def __init__(self, ollama_url: str, model: str = "phi3:mini"):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=300.0)

    async def summarize(self, transcript: str, caller: str, callee: str) -> str:
        if not transcript.strip():
            return "(No speech detected in this call)"

        prompt = SUMMARY_PROMPT.format(transcript=transcript)

        try:
            response = await self.client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except Exception as e:
            logger.error("Summarization failed: %s", e)
            return f"(Summarization failed: {e})"

    async def close(self):
        await self.client.aclose()
