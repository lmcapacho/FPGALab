"""Protocol-neutral virtual-cycle scheduling for driven FPGA inputs."""

import pytest

from fpga_lab.edge_drive import TimedDriveScheduler


class FakeSimulation:
    def __init__(self):
        self.cycle = 20
        self.queued = []
        self.available = 20

    def drive_cycle(self):
        return self.cycle

    def enqueue_drive_events(self, events):
        if len(events) > self.available:
            raise ValueError("queue full")
        self.queued.append(events)


def test_multichannel_sequence_shares_start_and_reserves_only_its_channels():
    simulation = FakeSimulation()
    scheduler = TimedDriveScheduler(simulation)
    assert scheduler.enqueue([(1, 3, False), (0, 0, True), (1, 0, True)], 5, 3) == (21, 26)
    assert simulation.queued[-1] == [(0, 21, True), (1, 21, True), (1, 24, False)]
    assert scheduler.enqueue([(2, 0, True)], 4, 3) == (21, 25)
    assert scheduler.enqueue([(1, 0, True), (2, 2, False)], 4, 3) == (26, 30)
    scheduler.reset()
    assert scheduler.enqueue([(0, 0, False)], 1, 3) == (21, 22)


def test_rejected_sequence_does_not_reserve_virtual_cycles():
    simulation = FakeSimulation()
    scheduler = TimedDriveScheduler(simulation)
    with pytest.raises(ValueError, match="twice"):
        scheduler.enqueue([(0, 0, True), (0, 0, False)], 2, 2)
    with pytest.raises(ValueError, match="outside"):
        scheduler.enqueue([(0, 2, True)], 2, 2)
    with pytest.raises(ValueError, match="channel"):
        scheduler.enqueue([(2, 0, True)], 2, 2)
    with pytest.raises(ValueError, match="duration"):
        scheduler.enqueue([(0, 0, True)], 0, 2)
    simulation.available = 0
    with pytest.raises(ValueError, match="queue full"):
        scheduler.enqueue([(0, 0, True)], 10, 2)
    simulation.available = 20
    assert scheduler.enqueue([(0, 0, True)], 10, 2) == (21, 31)
