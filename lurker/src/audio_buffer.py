import asyncio
import logging
import time

logger = logging.getLogger(__name__)

# 10 seconds of 8kHz 16-bit mono PCM = 160,000 bytes
CHUNK_DURATION_SECS = 10
SAMPLE_RATE = 8000
BYTES_PER_SAMPLE = 2
CHUNK_SIZE_BYTES = CHUNK_DURATION_SECS * SAMPLE_RATE * BYTES_PER_SAMPLE


class AudioBuffer:
    def __init__(self, call_id: str, on_chunk_ready):
        self.call_id = call_id
        self.on_chunk_ready = on_chunk_ready
        self.buffer = bytearray()
        self.chunk_start_time = time.time()

    def feed(self, pcm_data: bytes):
        self.buffer.extend(pcm_data)

        while len(self.buffer) >= CHUNK_SIZE_BYTES:
            chunk = bytes(self.buffer[:CHUNK_SIZE_BYTES])
            self.buffer = self.buffer[CHUNK_SIZE_BYTES:]

            duration = CHUNK_DURATION_SECS
            timestamp = self.chunk_start_time
            self.chunk_start_time = time.time()

            asyncio.get_event_loop().create_task(
                self.on_chunk_ready(self.call_id, chunk, timestamp, duration)
            )

    def flush(self):
        if len(self.buffer) > 0:
            chunk = bytes(self.buffer)
            self.buffer.clear()
            duration = len(chunk) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
            asyncio.get_event_loop().create_task(
                self.on_chunk_ready(self.call_id, chunk, self.chunk_start_time, duration)
            )
