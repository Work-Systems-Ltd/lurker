import logging

import librosa
import numpy as np
from fastapi import FastAPI, Request, Response
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whisper-server")

app = FastAPI()

logger.info("Loading faster-whisper model (base.en, int8)...")
model = WhisperModel("base.en", device="cpu", compute_type="int8")
logger.info("Model loaded")


@app.post("/transcribe")
async def transcribe(request: Request):
    pcm_bytes = await request.body()
    sample_rate = int(request.headers.get("X-Sample-Rate", "8000"))

    if len(pcm_bytes) < 1600:  # Less than 0.1s of audio
        return {"text": ""}

    # Convert raw 16-bit PCM to float32 array
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    # Resample to 16kHz if needed (Whisper expects 16kHz)
    if sample_rate != 16000:
        audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)

    segments, info = model.transcribe(audio, language="en")
    text = " ".join(segment.text for segment in segments)

    logger.info("Transcribed %.1fs audio: %s", info.duration, text[:100] if text else "(empty)")
    return {"text": text.strip()}


@app.get("/health")
async def health():
    return {"status": "ok"}
