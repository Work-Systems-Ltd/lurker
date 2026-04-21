import asyncio
import audioop
import logging

logger = logging.getLogger(__name__)


class RTPReceiver(asyncio.DatagramProtocol):
    def __init__(self, on_audio_callback):
        self.on_audio = on_audio_callback
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        logger.info("RTP receiver listening")

    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        if len(data) < 12:
            return

        # Strip 12-byte RTP header, extract ulaw payload
        payload = data[12:]
        try:
            pcm = audioop.ulaw2lin(payload, 2)
        except audioop.error:
            logger.warning("Failed to decode ulaw from %s", addr)
            return

        self.on_audio(addr, pcm)

    def error_received(self, exc):
        logger.error("RTP receiver error: %s", exc)


async def start_rtp_server(port: int, on_audio_callback) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: RTPReceiver(on_audio_callback),
        local_addr=("0.0.0.0", port),
    )
    logger.info("RTP server started on port %d", port)
    return transport
