#pragma once

#include <cstdint>

// Observe one sampled digital predicate across UI frame boundaries.
// Only a completed rising-to-falling pulse is published.
struct TemporalPulse {
    uint64_t high_samples = 0;
    uint64_t last_completed_samples = 0;
    bool previous = false;
    bool has_baseline = false;
    bool has_rising_edge = false;
    bool has_completed_pulse = false;

    void sample(bool active) {
        if (!has_baseline) {
            has_baseline = true;
            previous = active;
            high_samples = active ? 1 : 0;
            return;
        }
        if (active) {
            if (!previous) {
                high_samples = 0;
                has_rising_edge = true;
            }
            ++high_samples;
        } else if (previous) {
            if (has_rising_edge) {
                last_completed_samples = high_samples;
                has_completed_pulse = true;
            }
            high_samples = 0;
            has_rising_edge = false;
        }
        previous = active;
    }
};
