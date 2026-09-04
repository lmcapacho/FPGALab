#include "sim_streaming.h"
#include "vga_decoder.h"

#include <cstdlib>
#include <cstring>

extern "C" uint64_t sim_read_output(uint32_t index);

uint8_t g_sink_enabled = 0;

namespace {

struct Bind {
    int32_t port_index;
    uint8_t bit;
};

struct Sink {
    uint8_t used;
    SimVgaTiming timing;
    VgaDecoder *decoder;
    uint32_t *back;
    uint32_t *latest;
    uint32_t pixels;
    uint32_t seq;
    uint8_t have_frame;
    Bind binds[SIM_VGA_CHANNEL_COUNT];
    SimVgaStats stats;
};

Sink g_sink = {};

uint8_t read_channel(const Bind &bind) {
    if (bind.port_index < 0) {
        return 0;
    }
    return static_cast<uint8_t>((sim_read_output(static_cast<uint32_t>(bind.port_index)) >> bind.bit) & 1u);
}

uint8_t pack_color(const Bind *binds, uint8_t depth) {
    uint8_t value = 0;
    const uint8_t bits = (depth == 4) ? 4 : (depth == 2) ? 2 : 1;
    for (uint8_t i = 0; i < bits; ++i) {
        value |= static_cast<uint8_t>(read_channel(binds[i]) << i);
    }
    return value;
}

void free_buffers(Sink *sink) {
    std::free(sink->back);
    std::free(sink->latest);
    sink->back = nullptr;
    sink->latest = nullptr;
}

void clear_binds(Sink *sink) {
    for (uint32_t i = 0; i < SIM_VGA_CHANNEL_COUNT; ++i) {
        sink->binds[i].port_index = -1;
        sink->binds[i].bit = 0;
    }
}

}  // namespace

int sim_vga_create(uint32_t *out_id) {
    if (!out_id) {
        return -1;
    }
    if (g_sink.used) {
        return -1;
    }
    g_sink = {};
    clear_binds(&g_sink);
    g_sink.used = 1;
    g_sink.seq = 0;
    g_sink.have_frame = 0;
    *out_id = 0;
    return 0;
}

void sim_vga_destroy(uint32_t id) {
    if (id != 0 || !g_sink.used) {
        g_sink_enabled = 0;
        return;
    }
    vga_decoder_destroy(g_sink.decoder);
    free_buffers(&g_sink);
    g_sink = {};
    clear_binds(&g_sink);
    g_sink_enabled = 0;
}

int sim_vga_configure(uint32_t id, const SimVgaTiming *timing) {
    if (id != 0 || !g_sink.used || !timing) {
        return -1;
    }
    g_sink.timing = *timing;
    const uint32_t pixels = static_cast<uint32_t>(timing->h_active) * timing->v_active;
    if (pixels == 0) {
        return -1;
    }
    if (g_sink.pixels != pixels) {
        free_buffers(&g_sink);
        g_sink.back = static_cast<uint32_t *>(std::calloc(pixels, sizeof(uint32_t)));
        g_sink.latest = static_cast<uint32_t *>(std::calloc(pixels, sizeof(uint32_t)));
        if (!g_sink.back || !g_sink.latest) {
            free_buffers(&g_sink);
            return -1;
        }
        g_sink.pixels = pixels;
    }
    if (g_sink.decoder) {
        vga_decoder_destroy(g_sink.decoder);
    }
    g_sink.decoder = vga_decoder_create(timing);
    if (!g_sink.decoder) {
        return -1;
    }
    g_sink.have_frame = 0;
    g_sink.seq = 0;
    return 0;
}

int sim_vga_bind_bit(uint32_t id, uint32_t channel, int32_t port_index, uint8_t bit) {
    if (id != 0 || !g_sink.used || channel >= SIM_VGA_CHANNEL_COUNT || bit >= 64) {
        return -1;
    }
    g_sink.binds[channel].port_index = port_index;
    g_sink.binds[channel].bit = bit;
    return 0;
}

void sim_vga_enable(uint32_t id, uint8_t enabled) {
    if (id != 0 || !g_sink.used) {
        g_sink_enabled = 0;
        return;
    }
    g_sink_enabled = enabled && g_sink.decoder && g_sink.back && g_sink.latest;
}

void sim_streaming_on_posedge(void) {
    if (!g_sink_enabled || !g_sink.used || !g_sink.decoder || !g_sink.back) {
        return;
    }
    const uint8_t hsync = read_channel(g_sink.binds[SIM_VGA_CHANNEL_HSYNC]);
    const uint8_t vsync = read_channel(g_sink.binds[SIM_VGA_CHANNEL_VSYNC]);
    const uint8_t red = pack_color(&g_sink.binds[SIM_VGA_CHANNEL_R], g_sink.timing.color_depth);
    const uint8_t green = pack_color(&g_sink.binds[SIM_VGA_CHANNEL_G], g_sink.timing.color_depth);
    const uint8_t blue = pack_color(&g_sink.binds[SIM_VGA_CHANNEL_B], g_sink.timing.color_depth);
    VgaPosedgeOut out{};
    vga_decoder_posedge(g_sink.decoder, hsync, vsync, red, green, blue, &out);
    if (out.pixel_valid && out.sx < g_sink.timing.h_active && out.sy < g_sink.timing.v_active) {
        g_sink.back[static_cast<uint32_t>(out.sy) * g_sink.timing.h_active + out.sx] = out.argb;
    }
    g_sink.stats.last_h_total = out.last_h_total;
    g_sink.stats.last_v_total = out.last_v_total;
    g_sink.stats.pixels_this_frame = out.pixels_this_frame;
    g_sink.stats.synced = out.synced;
    g_sink.stats.frames_complete = out.frames_complete;
    if (out.publish) {
        uint32_t *tmp = g_sink.latest;
        g_sink.latest = g_sink.back;
        g_sink.back = tmp;
        std::memset(g_sink.back, 0, g_sink.pixels * sizeof(uint32_t));
        g_sink.seq = out.frames_complete;
        g_sink.have_frame = 1;
        g_sink.stats.seq = g_sink.seq;
    }
}

void sim_streaming_reset(void) {
    if (!g_sink.used) {
        return;
    }
    if (g_sink.decoder) {
        vga_decoder_reset(g_sink.decoder);
    }
    g_sink.seq = 0;
    g_sink.have_frame = 0;
    g_sink.stats = {};
    if (g_sink.back && g_sink.pixels) {
        std::memset(g_sink.back, 0, g_sink.pixels * sizeof(uint32_t));
    }
}

void sim_streaming_close(void) {
    sim_vga_destroy(0);
}

uint32_t sim_vga_seq(uint32_t id) {
    if (id != 0 || !g_sink.used) {
        return 0;
    }
    return g_sink.seq;
}

int sim_vga_copy_front(uint32_t id, uint32_t *dst, uint32_t dst_bytes, SimVgaStats *stats) {
    if (id != 0 || !g_sink.used || !g_sink.have_frame || !g_sink.latest) {
        return -1;
    }
    const uint32_t needed = g_sink.pixels * static_cast<uint32_t>(sizeof(uint32_t));
    if (!dst || dst_bytes < needed) {
        return -1;
    }
    std::memcpy(dst, g_sink.latest, needed);
    if (stats) {
        *stats = g_sink.stats;
        stats->seq = g_sink.seq;
        stats->frames_complete = g_sink.seq;
    }
    return 0;
}

void sim_vga_stats(uint32_t id, SimVgaStats *out) {
    if (!out) {
        return;
    }
    if (id != 0 || !g_sink.used) {
        *out = {};
        return;
    }
    *out = g_sink.stats;
    out->seq = g_sink.seq;
}
