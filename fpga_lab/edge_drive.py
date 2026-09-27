"""Protocol-independent scheduling of input transitions in virtual FPGA time."""

from __future__ import annotations

from collections.abc import Iterable

from .i18n import t


class TimedDriveScheduler:
    """Reserve a shared time window for one or more driven input channels.

    Protocol encoders supply (channel, relative cycle, level) transitions and a
    duration. The sequence is submitted atomically to the native queue; channel
    reservations advance only after the queue accepts every transition.
    """

    def __init__(self, simulation):
        self._simulation = simulation
        self._next_cycle: dict[int, int] = {}

    def reset(self) -> None:
        self._next_cycle.clear()

    def enqueue(
        self,
        transitions: Iterable[tuple[int, int, bool]],
        duration_cycles: int,
        channel_count: int,
    ) -> tuple[int, int]:
        """Return (start, exclusive end) after queueing a relative sequence."""
        if not isinstance(duration_cycles, int) or isinstance(duration_cycles, bool) or duration_cycles < 1:
            raise ValueError(t("Timed input sequence duration must be positive."))
        normalized = []
        for channel, offset, level in transitions:
            if not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel < channel_count:
                raise ValueError(t("Invalid timed input channel."))
            if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset < duration_cycles:
                raise ValueError(t("Timed input transition is outside the sequence duration."))
            normalized.append((offset, channel, bool(level)))
        if not normalized:
            raise ValueError(t("Timed input sequence has no transitions."))
        ordered = sorted(normalized)
        channels: set[int] = set()
        previous: tuple[int, int] | None = None
        for offset, channel, _level in ordered:
            if (offset, channel) == previous:
                raise ValueError(t("A timed input channel changes twice in one virtual cycle."))
            previous = (offset, channel)
            channels.add(channel)
        start = max(self._simulation.drive_cycle() + 1, *(self._next_cycle.get(channel, 0) for channel in channels))
        self._simulation.enqueue_drive_events(
            [(channel, start + offset, bool(level)) for offset, channel, level in ordered]
        )
        end = start + duration_cycles
        for channel in channels:
            self._next_cycle[channel] = end
        return start, end
