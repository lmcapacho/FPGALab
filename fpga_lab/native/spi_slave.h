// Reactive SPI byte source. Runs in virtual time, independently of GUI frames.
#pragma once
#include <cstdint>

struct SpiSlave {
    uint8_t response = 0xA5, mode = 0, index = 0, level = 0;
    bool lsb = false, selected = false, previous_clock = false;

    void reset() { index = level = 0; selected = false; previous_clock = bool(mode & 2); }
    uint8_t bit() const { return (response >> (lsb ? index : 7 - index)) & 1; }
    uint8_t update(bool clock, bool active) {
        if (!active) { reset(); previous_clock = clock; return level; }
        if (!selected) {
            selected = true;
            index = 0;
            level = (mode & 1) ? 0 : bit();
            previous_clock = clock;
            return level;
        }
        if (clock != previous_clock) {
            const bool leading = clock != bool(mode & 2);
            if (mode & 1) {
                if (leading) level = bit();
                else index = (index + 1) & 7;
            } else if (!leading) {
                index = (index + 1) & 7;
                level = bit();
            }
        }
        previous_clock = clock;
        return level;
    }
};
