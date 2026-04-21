import asyncio
import logging
import os
import sys
from datetime import datetime

import uvicorn

from .ari_controller import ARIController
from .models import CallSession, TranscriptChunk
from .rtp_receiver import start_rtp_server
from .summarizer import Summarizer
from .transcriber import Transcriber
from .web import app as web_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("lurker")


class Lurker:
    def __init__(self):
        self.ari_url = os.environ.get("ARI_URL", "http://asterisk-proxy:8088")
        self.ari_user = os.environ.get("ARI_USER", "lurker")
        self.ari_password = os.environ.get("ARI_PASS", "lurkerpass")
        self.app_name = os.environ.get("ARI_APP", "lurker")
        self.rtp_port = int(os.environ.get("RTP_LISTEN_PORT", "9999"))
        self.rtp_host = os.environ.get("RTP_LISTEN_HOST", "10.99.0.20")
        self.whisper_model = os.environ.get("WHISPER_MODEL", "base.en")
        self.ollama_url = os.environ.get("OLLAMA_URL", "http://ollama:11434")
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2:0.5b")
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        self.openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

        self.transcriber = Transcriber(self.whisper_model)
        self.summarizer = Summarizer(
            self.ollama_url, self.ollama_model,
            openai_api_key=self.openai_api_key,
            openai_model=self.openai_model,
        )

        self.controller = ARIController(
            ari_url=self.ari_url,
            ari_user=self.ari_user,
            ari_password=self.ari_password,
            app_name=self.app_name,
            rtp_listen_host=self.rtp_host,
            rtp_listen_port=self.rtp_port,
            on_chunk_ready=self.on_chunk_ready,
            on_call_ended=self.on_call_ended,
        )

    async def on_chunk_ready(self, call_id: str, pcm_data: bytes, timestamp: float, duration: float):
        logger.info("Transcribing chunk for call %s (%.1fs of audio)", call_id, duration)
        text = await self.transcriber.transcribe(pcm_data)
        if text:
            session = self.controller.sessions.get(call_id)
            if session:
                session.transcripts.append(
                    TranscriptChunk(text=text, timestamp=timestamp, duration=duration)
                )

    async def on_call_ended(self, session: CallSession):
        duration = (datetime.now() - session.started_at).total_seconds()
        transcript = session.full_transcript

        logger.info(
            "Call ended: %s -> %s (%.0fs, %d transcript chunks)",
            session.caller,
            session.callee,
            duration,
            len(session.transcripts),
        )

        if transcript:
            logger.info("Full transcript: %s", transcript)
            logger.info("Generating AI summary...")
            summary = await self.summarizer.summarize(transcript, session.caller, session.callee)
            print("\n" + "=" * 60)
            print(f"CALL SUMMARY — {session.caller} -> {session.callee}")
            print(f"Duration: {duration:.0f}s | {len(session.transcripts)} segments")
            print("-" * 60)
            print(summary)
            print("=" * 60 + "\n")
        else:
            logger.info("No speech detected in call, skipping summary")

    async def run(self):
        logger.info("Starting Lurker...")
        logger.info("ARI: %s (app=%s)", self.ari_url, self.app_name)
        logger.info("RTP: %s:%d", self.rtp_host, self.rtp_port)
        logger.info("Whisper model: %s", self.whisper_model)
        logger.info("Ollama: %s (model=%s)", self.ollama_url, self.ollama_model)

        # Start RTP receiver
        rtp_transport = await start_rtp_server(
            self.rtp_port, self.controller.route_audio
        )

        # Start web UI
        web_config = uvicorn.Config(web_app, host="0.0.0.0", port=8080, log_level="info")
        web_server = uvicorn.Server(web_config)
        web_task = asyncio.create_task(web_server.serve())
        logger.info("Web UI available at http://localhost:8080")

        # Start ARI controller (reconnects automatically)
        try:
            await self.controller.run()
        finally:
            web_server.should_exit = True
            await web_task
            rtp_transport.close()
            await self.transcriber.close()
            await self.summarizer.close()
            await self.controller.close()


def main():
    lurker = Lurker()
    asyncio.run(lurker.run())


if __name__ == "__main__":
    main()
