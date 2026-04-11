"""Microphone manager — exclusive access to the audio input device.

Coordinates hand-off between the Activation layer (clap detection in
PASSIVE_LISTEN mode) and the Ears layer (STT recording in ACTIVE_LISTEN
mode).  Only one consumer may hold the microphone at a time.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import AsyncIterator

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_SAMPLE_RATE = 16_000
CHANNELS = 1
BLOCK_SIZE = 1024  # ~64 ms at 16 kHz — good balance for STT chunking
ACTIVE_LISTEN_TIMEOUT_S = 5.0  # return to passive if no speech within this


class MicState(Enum):
    """Microphone ownership state."""

    PASSIVE_LISTEN = "passive_listen"  # clap detector owns the mic
    ACTIVE_LISTEN = "active_listen"  # STT / Ears owns the mic


class AudioStream:
    """Async wrapper around a ``sounddevice.InputStream``.

    Yields ``numpy.ndarray`` chunks (float32, mono) via ``async for``.
    The stream is opened on construction and closed when :meth:`close`
    is called (or the async-for exits).
    """

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        block_size: int = BLOCK_SIZE,
        device_index: int | None = None,
    ) -> None:
        self._sample_rate = sample_rate
        self._block_size = block_size
        self._device_index = device_index
        self._queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue()
        self._stream: "sounddevice.InputStream | None" = None
        self._closed = False
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the underlying PortAudio stream."""
        import sounddevice

        self._loop = asyncio.get_event_loop()
        self._closed = False

        self._stream = sounddevice.InputStream(
            samplerate=self._sample_rate,
            channels=CHANNELS,
            dtype="float32",
            blocksize=self._block_size,
            callback=self._audio_callback,
            device=self._device_index,
        )
        self._stream.start()
        logger.debug("AudioStream opened (rate=%d, block=%d)", self._sample_rate, self._block_size)

    def close(self) -> None:
        """Stop and close the underlying stream."""
        self._closed = True
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                logger.exception("Error closing AudioStream")
            finally:
                self._stream = None
        # Unblock anyone waiting on the queue
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        logger.debug("AudioStream closed")

    # ------------------------------------------------------------------
    # Async iteration
    # ------------------------------------------------------------------

    def __aiter__(self) -> AsyncIterator[np.ndarray]:
        return self

    async def __anext__(self) -> np.ndarray:
        if self._closed and self._queue.empty():
            raise StopAsyncIteration
        chunk = await self._queue.get()
        if chunk is None:
            raise StopAsyncIteration
        return chunk

    # ------------------------------------------------------------------
    # PortAudio callback (runs on audio thread)
    # ------------------------------------------------------------------

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        if self._closed:
            return
        data = indata.copy()
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._queue.put_nowait, data)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def is_open(self) -> bool:
        return self._stream is not None and not self._closed


class MicManager:
    """Manage exclusive ownership of the system microphone.

    Usage::

        mgr = MicManager()
        stream = await mgr.acquire("ears")
        async for chunk in stream:
            ...
        await mgr.release("ears")

    Only one requester may hold the mic at a time.  A second
    ``acquire`` call while the mic is held will raise
    ``MicConflictError``.
    """

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, device_index: int | None = None) -> None:
        self._sample_rate = sample_rate
        self._device_index = device_index
        self._owner: str | None = None
        self._stream: AudioStream | None = None
        self._lock = asyncio.Lock()
        self._state = MicState.PASSIVE_LISTEN
        self._timeout_task: asyncio.Task | None = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(self, requester: str) -> AudioStream:
        """Acquire exclusive mic access for *requester*.

        Returns an :class:`AudioStream` that yields audio chunks.

        Raises :class:`MicConflictError` if another requester already
        holds the microphone.
        """
        async with self._lock:
            if self._owner is not None:
                raise MicConflictError(
                    f"Mic already held by {self._owner!r}; "
                    f"{requester!r} cannot acquire"
                )

            stream = AudioStream(sample_rate=self._sample_rate, device_index=self._device_index)
            stream.open()

            self._owner = requester
            self._stream = stream
            self._state = MicState.ACTIVE_LISTEN
            logger.info("Mic acquired by %r", requester)

            # Start inactivity timeout
            self._cancel_timeout()
            self._timeout_task = asyncio.ensure_future(
                self._inactivity_timeout(requester)
            )

            return stream

    async def release(self, requester: str) -> None:
        """Release the mic previously acquired by *requester*.

        Raises :class:`MicConflictError` if *requester* is not the
        current owner.
        """
        async with self._lock:
            if self._owner != requester:
                raise MicConflictError(
                    f"{requester!r} cannot release — current owner is "
                    f"{self._owner!r}"
                )
            self._do_release()

    @property
    def current_owner(self) -> str | None:
        """Return the name of the current mic owner, or ``None``."""
        return self._owner

    @property
    def state(self) -> MicState:
        """Current mic state."""
        return self._state

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _do_release(self) -> None:
        """Release without re-acquiring the lock (caller must hold it)."""
        self._cancel_timeout()
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        prev_owner = self._owner
        self._owner = None
        self._state = MicState.PASSIVE_LISTEN
        logger.info("Mic released by %r → PASSIVE_LISTEN", prev_owner)

    def _cancel_timeout(self) -> None:
        if self._timeout_task is not None:
            self._timeout_task.cancel()
            self._timeout_task = None

    async def _inactivity_timeout(self, requester: str) -> None:
        """Auto-release the mic if the holder doesn't release within timeout."""
        try:
            await asyncio.sleep(ACTIVE_LISTEN_TIMEOUT_S)
        except asyncio.CancelledError:
            return
        async with self._lock:
            if self._owner == requester:
                logger.warning(
                    "Inactivity timeout (%.1f s) — auto-releasing mic from %r",
                    ACTIVE_LISTEN_TIMEOUT_S,
                    requester,
                )
                self._do_release()


class MicConflictError(RuntimeError):
    """Raised when a mic acquire/release violates ownership rules."""
