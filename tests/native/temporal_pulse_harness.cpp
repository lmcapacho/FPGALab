#include "temporal_pulse.h"

#include <cassert>

int main() {
    TemporalPulse probe;
    probe.sample(false);  // Establish a known low level before the rising edge.
    for (int i = 0; i < 500; ++i) probe.sample(true);
    assert(!probe.has_completed_pulse);  // The UI frame ended mid-pulse.
    for (int i = 0; i < 500; ++i) probe.sample(true);
    probe.sample(false);
    assert(probe.has_completed_pulse);
    assert(probe.last_completed_samples == 1000);
    for (int i = 0; i < 1500; ++i) probe.sample(true);
    assert(probe.last_completed_samples == 1000);  // Never publish partial width.
    probe.sample(false);
    assert(probe.last_completed_samples == 1500);
    probe = TemporalPulse{};
    assert(!probe.has_completed_pulse);
    probe.sample(true);  // Initial high level is an incomplete pulse.
    probe.sample(false);
    assert(!probe.has_completed_pulse);
    return 0;
}
