import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import librosa
import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


class Transcriber:
    def __init__(self, model_size: str = "base.en"):
        logger.info("Loading whisper model '%s'...", model_size)
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        logger.info("Whisper model loaded")

    def _transcribe_sync(self, pcm_data: bytes, sample_rate: int) -> str:
        if len(pcm_data) < 1600:
            return ""

        audio = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0

        if sample_rate != 16000:
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)

        segments, info = self.model.transcribe(audio, language="en")
        text = " ".join(s.text for s in segments).strip()

        if text:
            logger.info("Transcribed %.1fs: %s", info.duration, text[:100])
        return text

    async def transcribe(self, pcm_data: bytes, sample_rate: int = 8000) -> str:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                _executor, self._transcribe_sync, pcm_data, sample_rate
            )
        except Exception as e:
            logger.error("Transcription failed: %s", e)
            return ""

    async def close(self):
        pass
