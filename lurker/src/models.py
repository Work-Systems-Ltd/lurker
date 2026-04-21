from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TranscriptChunk:
    text: str
    timestamp: float
    duration: float


@dataclass
class CallSession:
    call_id: str
    caller: str
    callee: str
    started_at: datetime = field(default_factory=datetime.now)
    pcm_buffer: bytearray = field(default_factory=bytearray)
    transcripts: list[TranscriptChunk] = field(default_factory=list)
    snoop_channel_id: str | None = None
    external_media_channel_id: str | None = None
    bridge_id: str | None = None
    source_addr: tuple[str, int] | None = None

    @property
    def full_transcript(self) -> str:
        return " ".join(t.text for t in self.transcripts if t.text.strip())
