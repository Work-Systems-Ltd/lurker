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
    def __init__(self, ollama_url: str, model: str = "qwen2:0.5b", openai_api_key: str | None = None, openai_model: str = "gpt-4o-mini"):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.client = httpx.AsyncClient(timeout=300.0)

        if self.openai_api_key:
            logger.info("Summarizer using OpenAI API (model=%s)", self.openai_model)
        else:
            logger.info("Summarizer using local Ollama (model=%s)", self.model)

    async def summarize(self, transcript: str, caller: str, callee: str) -> str:
        if not transcript.strip():
            return "(No speech detected in this call)"

        if self.openai_api_key:
            return await self._summarize_openai(transcript)
        return await self._summarize_ollama(transcript)

    async def _summarize_openai(self, transcript: str) -> str:
        prompt = SUMMARY_PROMPT.format(transcript=transcript)
        try:
            response = await self.client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                },
                json={
                    "model": self.openai_model,
                    "messages": [
                        {"role": "system", "content": "You are a concise call summarizer."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 200,
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error("OpenAI summarization failed: %s", e)
            return f"(Summarization failed: {e})"

    async def _summarize_ollama(self, transcript: str) -> str:
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
            logger.error("Ollama summarization failed: %s", e)
            return f"(Summarization failed: {e})"

    async def close(self):
        await self.client.aclose()
