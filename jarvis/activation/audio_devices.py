"""Helpers for selecting and describing audio input devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InputDevice:
    index: int | None
    name: str
    max_input_channels: int = 0
    default_samplerate: float = 0.0


def list_input_devices() -> list[InputDevice]:
    """Return all available input devices."""
    import sounddevice

    devices = sounddevice.query_devices()
    results: list[InputDevice] = []
    for index, device in enumerate(devices):
        if device.get("max_input_channels", 0) <= 0:
            continue
        results.append(
            InputDevice(
                index=index,
                name=str(device.get("name", f"Input {index}")),
                max_input_channels=int(device.get("max_input_channels", 0)),
                default_samplerate=float(device.get("default_samplerate", 0.0)),
            )
        )
    return results


def resolve_input_device(
    preferred_index: int | None = None,
    preferred_name: str = "",
    auto_detect: bool = True,
) -> InputDevice:
    """Resolve the best input device for the current runtime."""
    import sounddevice

    inputs = list_input_devices()
    if not inputs:
        return InputDevice(index=None, name="System default")

    by_index = {device.index: device for device in inputs}

    if preferred_index is not None and preferred_index in by_index:
        return by_index[preferred_index]

    preferred_name = preferred_name.strip().lower()
    if preferred_name:
        for device in inputs:
            if preferred_name == device.name.lower():
                return device
        for device in inputs:
            if preferred_name in device.name.lower():
                return device

    if auto_detect:
        try:
            default_device = sounddevice.default.device[0]
        except Exception:
            default_device = None
        if default_device in by_index:
            return by_index[default_device]

    return inputs[0]


def stream_device_kwargs(device: InputDevice) -> dict:
    """Build sounddevice.InputStream kwargs for the selected device."""
    if device.index is None:
        return {}
    return {"device": device.index}


def selected_device_changed(
    current_index: int | None,
    *,
    preferred_index: int | None = None,
    preferred_name: str = "",
    auto_detect: bool = True,
) -> bool:
    """Return True when the currently selected input device has changed."""
    resolved = resolve_input_device(
        preferred_index=preferred_index,
        preferred_name=preferred_name,
        auto_detect=auto_detect,
    )
    changed = resolved.index != current_index
    if changed:
        logger.info(
            "Active input device changed from %s to %s",
            current_index,
            resolved.index,
        )
    return changed
