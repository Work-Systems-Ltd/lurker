import asyncio
import json
import logging
import uuid

import httpx
import websockets

from .audio_buffer import AudioBuffer
from .models import CallSession, TranscriptChunk

logger = logging.getLogger(__name__)


class ARIController:
    def __init__(
        self,
        ari_url: str,
        ari_user: str,
        ari_password: str,
        app_name: str,
        rtp_listen_host: str,
        rtp_listen_port: int,
        on_chunk_ready,
        on_call_ended,
    ):
        self.ari_url = ari_url.rstrip("/")
        self.ari_user = ari_user
        self.ari_password = ari_password
        self.app_name = app_name
        self.rtp_listen_host = rtp_listen_host
        self.rtp_listen_port = rtp_listen_port
        self.on_chunk_ready = on_chunk_ready
        self.on_call_ended = on_call_ended

        self.http = httpx.AsyncClient(
            base_url=self.ari_url,
            auth=(self.ari_user, self.ari_password),
            timeout=10.0,
        )

        # call_id -> CallSession
        self.sessions: dict[str, CallSession] = {}
        # (addr, port) -> call_id for routing RTP
        self.addr_to_call: dict[tuple[str, int], str] = {}
        # channel_id -> call_id
        self.channel_to_call: dict[str, str] = {}

    async def run(self):
        ws_url = self.ari_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ari/events?app={self.app_name}&api_key={self.ari_user}:{self.ari_password}"

        while True:
            try:
                logger.info("Connecting to ARI WebSocket at %s", self.ari_url)
                async with websockets.connect(ws_url) as ws:
                    logger.info("Connected to ARI")
                    async for message in ws:
                        try:
                            event = json.loads(message)
                            await self._handle_event(event)
                        except Exception as e:
                            logger.error("Error handling ARI event: %s", e, exc_info=True)
            except Exception as e:
                logger.warning("ARI connection lost (%s), reconnecting in 5s...", e)
                await asyncio.sleep(5)

    async def _handle_event(self, event: dict):
        event_type = event.get("type", "")

        if event_type == "StasisStart":
            await self._on_stasis_start(event)
        elif event_type == "StasisEnd":
            await self._on_stasis_end(event)
        elif event_type == "ChannelDestroyed":
            await self._on_channel_destroyed(event)

    async def _on_stasis_start(self, event: dict):
        channel = event.get("channel", {})
        channel_id = channel.get("id", "")
        args = event.get("args", [])

        # Ignore snoop and external media channels entering stasis
        if channel_id in self.channel_to_call:
            return

        # Parse dialed extension from args: ["dialed=bob"]
        dialed = ""
        for arg in args:
            if arg.startswith("dialed="):
                dialed = arg.split("=", 1)[1]

        if not dialed:
            logger.warning("StasisStart with no dialed extension, ignoring channel %s", channel_id)
            return

        caller_name = channel.get("caller", {}).get("name", "unknown")
        call_id = str(uuid.uuid4())

        logger.info("New call %s: %s -> %s (channel: %s)", call_id, caller_name, dialed, channel_id)

        session = CallSession(
            call_id=call_id,
            caller=caller_name,
            callee=dialed,
        )
        self.sessions[call_id] = session
        self.channel_to_call[channel_id] = call_id

        try:
            # 1. Create a snoop channel on the incoming channel
            snoop_id = f"snoop-{call_id[:8]}"
            resp = await self.http.post(
                f"/ari/channels/{channel_id}/snoop",
                params={
                    "app": self.app_name,
                    "spy": "both",
                    "whisper": "none",
                    "snoopId": snoop_id,
                },
            )
            resp.raise_for_status()
            session.snoop_channel_id = snoop_id
            self.channel_to_call[snoop_id] = call_id
            logger.info("Created snoop channel %s for call %s", snoop_id, call_id)

            # 2. Create external media channel pointing at lurker RTP receiver
            ext_id = f"extmedia-{call_id[:8]}"
            resp = await self.http.post(
                "/ari/channels/externalMedia",
                params={
                    "app": self.app_name,
                    "external_host": f"{self.rtp_listen_host}:{self.rtp_listen_port}",
                    "format": "ulaw",
                    "channelId": ext_id,
                },
            )
            resp.raise_for_status()
            session.external_media_channel_id = ext_id
            self.channel_to_call[ext_id] = call_id
            logger.info("Created external media channel %s -> %s:%d", ext_id, self.rtp_listen_host, self.rtp_listen_port)

            # 3. Create a bridge and add snoop + external media
            bridge_id = f"bridge-{call_id[:8]}"
            resp = await self.http.post(
                "/ari/bridges",
                params={"type": "mixing", "bridgeId": bridge_id},
            )
            resp.raise_for_status()
            session.bridge_id = bridge_id

            resp = await self.http.post(
                f"/ari/bridges/{bridge_id}/addChannel",
                params={"channel": f"{snoop_id},{ext_id}"},
            )
            resp.raise_for_status()
            logger.info("Bridged snoop + external media in bridge %s", bridge_id)

            # 4. Originate the outbound leg back through PBX to reach the callee
            outbound_id = f"outbound-{call_id[:8]}"
            resp = await self.http.post(
                "/ari/channels",
                params={
                    "endpoint": f"PJSIP/{dialed}@pbx-trunk",
                    "app": self.app_name,
                    "channelId": outbound_id,
                },
            )
            resp.raise_for_status()
            self.channel_to_call[outbound_id] = call_id
            logger.info("Originated outbound call to %s via pbx-trunk", dialed)

            # 5. Bridge the original incoming channel with the outbound channel
            call_bridge_id = f"callbridge-{call_id[:8]}"
            resp = await self.http.post(
                "/ari/bridges",
                params={"type": "mixing", "bridgeId": call_bridge_id},
            )
            resp.raise_for_status()

            resp = await self.http.post(
                f"/ari/bridges/{call_bridge_id}/addChannel",
                params={"channel": f"{channel_id},{outbound_id}"},
            )
            resp.raise_for_status()
            logger.info("Bridged caller + callee in bridge %s", call_bridge_id)

        except Exception as e:
            logger.error("Failed to set up interception for call %s: %s", call_id, e, exc_info=True)

    async def _on_stasis_end(self, event: dict):
        channel_id = event.get("channel", {}).get("id", "")
        call_id = self.channel_to_call.get(channel_id)
        if not call_id:
            return

        session = self.sessions.get(call_id)
        if not session:
            return

        logger.info("Call %s ended (channel %s hung up)", call_id, channel_id)
        await self._cleanup_call(call_id)

    async def _on_channel_destroyed(self, event: dict):
        channel_id = event.get("channel", {}).get("id", "")
        call_id = self.channel_to_call.pop(channel_id, None)
        if call_id and call_id in self.sessions:
            await self._cleanup_call(call_id)

    async def _cleanup_call(self, call_id: str):
        session = self.sessions.pop(call_id, None)
        if not session:
            return

        # Clean up ARI resources
        for channel_id in [session.snoop_channel_id, session.external_media_channel_id]:
            if channel_id:
                try:
                    await self.http.delete(f"/ari/channels/{channel_id}")
                except Exception:
                    pass
                self.channel_to_call.pop(channel_id, None)

        if session.bridge_id:
            try:
                await self.http.delete(f"/ari/bridges/{session.bridge_id}")
            except Exception:
                pass

        # Remove addr mapping
        if session.source_addr:
            self.addr_to_call.pop(session.source_addr, None)

        # Notify that call ended for summarization
        await self.on_call_ended(session)

    def route_audio(self, addr: tuple[str, int], pcm_data: bytes):
        """Route incoming RTP audio to the correct call session's buffer."""
        call_id = self.addr_to_call.get(addr)

        if not call_id:
            # First packet from this address — try to find unmatched session
            for cid, session in self.sessions.items():
                if session.source_addr is None:
                    session.source_addr = addr
                    self.addr_to_call[addr] = cid
                    call_id = cid
                    logger.info("Mapped RTP source %s to call %s", addr, cid)
                    break

        if not call_id:
            return

        session = self.sessions.get(call_id)
        if not session:
            return

        if not hasattr(session, "_audio_buffer"):
            session._audio_buffer = AudioBuffer(call_id, self.on_chunk_ready)

        session._audio_buffer.feed(pcm_data)

    async def close(self):
        await self.http.aclose()
