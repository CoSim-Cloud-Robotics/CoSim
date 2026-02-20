from __future__ import annotations

import asyncio
import json
from fractions import Fraction
import contextlib
import io
from typing import Any, Awaitable, Callable

import numpy as np
from PIL import Image
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, MediaStreamTrack
from av import VideoFrame
import websockets


class FrameBuffer:
    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._frame: np.ndarray | None = None
        self._sequence = 0

    async def update(self, frame: np.ndarray) -> None:
        async with self._condition:
            self._frame = frame
            self._sequence += 1
            self._condition.notify_all()

    async def next_frame(self, last_sequence: int) -> tuple[np.ndarray, int]:
        async with self._condition:
            await self._condition.wait_for(
                lambda: self._frame is not None and self._sequence != last_sequence
            )
            return self._frame, self._sequence


class BroadcastVideoTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, buffer: FrameBuffer, fps: int) -> None:
        super().__init__()
        self._buffer = buffer
        self._fps = fps
        self._last_sequence = 0
        self._time_base = Fraction(1, max(1, fps))

    async def recv(self) -> VideoFrame:
        frame_array, sequence = await self._buffer.next_frame(self._last_sequence)
        self._last_sequence = sequence
        frame = VideoFrame.from_ndarray(frame_array, format="rgb24")
        frame.pts = sequence
        frame.time_base = self._time_base
        return frame


class WebRTCBroadcaster:
    def __init__(
        self,
        signaling_url: str,
        room_id: str,
        fps: int,
        on_peer_count: Callable[[int], Awaitable[None] | None] | None = None,
    ) -> None:
        self._signaling_url = signaling_url
        self._room_id = room_id
        self._fps = fps
        self._on_peer_count = on_peer_count
        self._buffer = FrameBuffer()
        self._peers: dict[str, RTCPeerConnection] = {}
        self._socket: websockets.WebSocketClientProtocol | None = None
        self._task: asyncio.Task | None = None
        self._client_id: str | None = None

    @property
    def peer_count(self) -> int:
        return len(self._peers)

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._signaling_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._socket:
            await self._socket.close()
            self._socket = None
        await self._close_all_peers()

    async def publish_frame(self, frame_bytes: bytes) -> None:
        image = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
        frame_array = np.array(image)
        await self._buffer.update(frame_array)

    async def _close_all_peers(self) -> None:
        peers = list(self._peers.values())
        self._peers.clear()
        for peer in peers:
            await peer.close()
        await self._notify_peer_count()

    async def _notify_peer_count(self) -> None:
        if not self._on_peer_count:
            return
        result = self._on_peer_count(self.peer_count)
        if asyncio.iscoroutine(result):
            await result

    async def _signaling_loop(self) -> None:
        async with websockets.connect(self._signaling_url) as websocket:
            self._socket = websocket
            async for message in websocket:
                payload = json.loads(message)
                await self._handle_signal(payload)

    async def _handle_signal(self, payload: dict[str, Any]) -> None:
        message_type = payload.get("type")
        if message_type == "welcome":
            self._client_id = payload.get("clientId")
            await self._send(
                {
                    "type": "join",
                    "roomId": self._room_id,
                    "role": "broadcaster",
                }
            )
            return

        if message_type == "offer":
            await self._handle_offer(payload)
            return

        if message_type == "ice-candidate":
            await self._handle_ice(payload)
            return

        if message_type == "peer-left":
            peer_id = payload.get("peerId")
            if peer_id in self._peers:
                await self._peers[peer_id].close()
                self._peers.pop(peer_id, None)
                await self._notify_peer_count()

    async def _handle_offer(self, payload: dict[str, Any]) -> None:
        peer_id = payload.get("fromId")
        offer = payload.get("offer")
        if not peer_id or not offer:
            return

        pc = RTCPeerConnection()
        self._peers[peer_id] = pc
        await self._notify_peer_count()

        pc.addTrack(BroadcastVideoTrack(self._buffer, self._fps))

        @pc.on("icecandidate")
        async def on_icecandidate(candidate: RTCIceCandidate | None) -> None:
            if candidate is None:
                return
            await self._send(
                {
                    "type": "ice-candidate",
                    "targetId": peer_id,
                    "candidate": {
                        "candidate": getattr(candidate, "candidate", None) or candidate.to_sdp(),
                        "sdpMid": candidate.sdpMid,
                        "sdpMLineIndex": candidate.sdpMLineIndex,
                    },
                }
            )

        await pc.setRemoteDescription(RTCSessionDescription(sdp=offer["sdp"], type=offer["type"]))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await self._send(
            {
                "type": "answer",
                "targetId": peer_id,
                "answer": {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp},
            }
        )

        @pc.on("connectionstatechange")
        async def on_connection_change() -> None:
            if pc.connectionState in ("failed", "closed", "disconnected"):
                await pc.close()
                self._peers.pop(peer_id, None)
                await self._notify_peer_count()

    async def _handle_ice(self, payload: dict[str, Any]) -> None:
        peer_id = payload.get("fromId")
        candidate_payload = payload.get("candidate") or {}
        if not peer_id or not candidate_payload:
            return
        pc = self._peers.get(peer_id)
        if not pc:
            return
        ice = RTCIceCandidate(
            sdpMid=candidate_payload.get("sdpMid"),
            sdpMLineIndex=candidate_payload.get("sdpMLineIndex"),
            candidate=candidate_payload.get("candidate"),
        )
        await pc.addIceCandidate(ice)

    async def _send(self, message: dict[str, Any]) -> None:
        if not self._socket:
            return
        await self._socket.send(json.dumps(message))
