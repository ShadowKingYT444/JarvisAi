"""Tests for the Face layer (HUD state manager, tray, overlay).

GUI widget tests are limited since we can't run a real QApplication in CI.
We test the StateManager and event-driven logic thoroughly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from jarvis.face.hud import StateManager
from jarvis.shared.events import EventBus
from jarvis.shared.types import JarvisState


class TestStateManager:
    @pytest.fixture
    def event_bus(self):
        return EventBus()

    @pytest.fixture
    def manager(self, event_bus):
        return StateManager(event_bus=event_bus)

    def test_initial_state_is_idle(self, manager):
        assert manager.current_state == JarvisState.IDLE

    def test_set_state_updates_current(self, manager):
        manager.set_state(JarvisState.LISTENING)
        assert manager.current_state == JarvisState.LISTENING

    def test_set_state_with_metadata(self, manager):
        manager.set_state(JarvisState.FOCUS_MODE, {"goal": "coding"})
        assert manager.current_state == JarvisState.FOCUS_MODE
        assert manager.metadata == {"goal": "coding"}

    def test_metadata_defaults_to_empty(self, manager):
        manager.set_state(JarvisState.PROCESSING)
        assert manager.metadata == {}

    def test_emits_state_changed_event(self, event_bus, manager):
        received = []
        event_bus.on("state_changed", lambda d: received.append(d))

        manager.set_state(JarvisState.LISTENING)

        assert len(received) == 1
        state, meta = received[0]
        assert state == JarvisState.LISTENING
        assert meta == {}

    def test_subscribe_callback(self, manager):
        calls = []
        manager.subscribe(lambda s, m: calls.append((s, m)))

        manager.set_state(JarvisState.SPEAKING)

        assert len(calls) == 1
        assert calls[0][0] == JarvisState.SPEAKING

    def test_unsubscribe(self, manager):
        calls = []
        cb = lambda s, m: calls.append(s)
        manager.subscribe(cb)
        manager.set_state(JarvisState.LISTENING)
        assert len(calls) == 1

        manager.unsubscribe(cb)
        manager.set_state(JarvisState.PROCESSING)
        assert len(calls) == 1  # no new call

    def test_subscriber_exception_doesnt_crash(self, manager):
        def bad_callback(s, m):
            raise ValueError("boom")

        manager.subscribe(bad_callback)
        # Should not raise
        manager.set_state(JarvisState.ERROR)
        assert manager.current_state == JarvisState.ERROR

    def test_multiple_subscribers(self, manager):
        calls_a = []
        calls_b = []
        manager.subscribe(lambda s, m: calls_a.append(s))
        manager.subscribe(lambda s, m: calls_b.append(s))

        manager.set_state(JarvisState.SPEAKING)
        assert len(calls_a) == 1
        assert len(calls_b) == 1

    def test_full_state_cycle(self, manager):
        states = [
            JarvisState.IDLE,
            JarvisState.LISTENING,
            JarvisState.PROCESSING,
            JarvisState.SPEAKING,
            JarvisState.IDLE,
        ]
        for state in states:
            manager.set_state(state)
        assert manager.current_state == JarvisState.IDLE
