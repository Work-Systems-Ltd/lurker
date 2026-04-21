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
        self.pending_tasks: list[asyncio.Task] = []

    def feed(self, pcm_data: bytes):
        self.buffer.extend(pcm_data)

        while len(self.buffer) >= CHUNK_SIZE_BYTES:
            chunk = bytes(self.buffer[:CHUNK_SIZE_BYTES])
            self.buffer = self.buffer[CHUNK_SIZE_BYTES:]

            duration = CHUNK_DURATION_SECS
            timestamp = self.chunk_start_time
            self.chunk_start_time = time.time()

            task = asyncio.get_event_loop().create_task(
                self.on_chunk_ready(self.call_id, chunk, timestamp, duration)
            )
            self.pending_tasks.append(task)

    def flush(self):
        if len(self.buffer) > 0:
            chunk = bytes(self.buffer)
            self.buffer.clear()
            duration = len(chunk) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
            task = asyncio.get_event_loop().create_task(
                self.on_chunk_ready(self.call_id, chunk, self.chunk_start_time, duration)
            )
            self.pending_tasks.append(task)

    async def wait_pending(self):
        """Wait for all in-flight transcription tasks to complete."""
        if self.pending_tasks:
            logger.info("Waiting for %d pending transcription(s)...", len(self.pending_tasks))
            await asyncio.gather(*self.pending_tasks, return_exceptions=True)
            self.pending_tasks.clear()
