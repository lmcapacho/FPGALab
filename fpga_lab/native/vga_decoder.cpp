#include "vga_decoder.h"

#include <cstdlib>
#include <cstring>

/*
 * Timing spec copied from references/vga_sim_framework/vga_sink.v:
 *   localparam H_ACTIVE = 640;
 *   localparam H_FRONT_PORCH = 16;
 *   localparam H_SYNC_PULSE = 96;
 *   localparam H_BACK_PORCH = 48;
 *   localparam V_ACTIVE = 480;
 *   localparam V_FRONT_PORCH = 10;
 *   localparam V_SYNC_PULSE = 2;
 *   localparam V_BACK_PORCH = 33;
 *
 * de/sx/sy are registered from the previous cycle's counters (Verilog NBA).
 * RGB is combinational pass-through of the current post-eval() outputs.
 */

struct VgaDecoder {
    SimVgaTiming t;
    uint16_t hcount, vcount;
    uint8_t hsync_prev, vsync_prev;
    uint8_t de;
    uint16_t sx, sy;
    uint8_t synced;
    uint32_t frames_complete;
    uint32_t last_h_total, last_v_total;
    uint32_t h_since_sync;
    uint32_t lines_since_vsync;
    uint32_t pixels_this_frame;
    uint16_t h_total, v_total;
    uint16_t h_active_start, h_active_end;
    uint16_t v_active_start, v_active_end;
};

static uint8_t expand_component(uint8_t c, uint8_t depth) {
    if (depth == 1) {
        return c ? 0xFFu : 0u;
    }
    if (depth == 2) {
        c &= 0x03u;
        return static_cast<uint8_t>((c << 6) | (c << 4) | (c << 2) | c);
    }
    c &= 0x0Fu;
    return static_cast<uint8_t>((c << 4) | c);
}

static uint8_t is_active(uint8_t level, uint8_t active_low) {
    return active_low ? (level == 0) : (level != 0);
}

static void apply_timing(VgaDecoder *d, const SimVgaTiming *t) {
    d->t = *t;
    if (d->t.color_depth != 1 && d->t.color_depth != 2 && d->t.color_depth != 4) {
        d->t.color_depth = 1;
    }
    d->h_total = static_cast<uint16_t>(t->h_active + t->h_fp + t->h_sync + t->h_bp);
    d->v_total = static_cast<uint16_t>(t->v_active + t->v_fp + t->v_sync + t->v_bp);
    d->h_active_start = static_cast<uint16_t>(t->h_sync + t->h_bp);
    d->h_active_end = static_cast<uint16_t>(d->h_active_start + t->h_active);
    d->v_active_start = static_cast<uint16_t>(t->v_sync + t->v_bp);
    d->v_active_end = static_cast<uint16_t>(d->v_active_start + t->v_active);
}

void vga_decoder_reset(VgaDecoder *d) {
    if (!d) {
        return;
    }
    d->hcount = 0;
    d->vcount = 0;
    d->hsync_prev = 1;
    d->vsync_prev = 1;
    d->de = 0;
    d->sx = 0;
    d->sy = 0;
    d->synced = 0;
    d->frames_complete = 0;
    d->last_h_total = 0;
    d->last_v_total = 0;
    d->h_since_sync = 0;
    d->lines_since_vsync = 0;
    d->pixels_this_frame = 0;
}

VgaDecoder *vga_decoder_create(const SimVgaTiming *t) {
    if (!t) {
        return nullptr;
    }
    VgaDecoder *d = static_cast<VgaDecoder *>(std::calloc(1, sizeof(VgaDecoder)));
    if (!d) {
        return nullptr;
    }
    apply_timing(d, t);
    vga_decoder_reset(d);
    return d;
}

void vga_decoder_destroy(VgaDecoder *d) {
    std::free(d);
}

uint8_t vga_decoder_de(const VgaDecoder *d) {
    return d ? d->de : 0;
}

uint16_t vga_decoder_sx(const VgaDecoder *d) {
    return d ? d->sx : 0;
}

uint16_t vga_decoder_sy(const VgaDecoder *d) {
    return d ? d->sy : 0;
}

void vga_decoder_posedge(VgaDecoder *d,
                         uint8_t hsync, uint8_t vsync,
                         uint8_t red, uint8_t green, uint8_t blue,
                         VgaPosedgeOut *out) {
    if (!out) {
        return;
    }
    std::memset(out, 0, sizeof(*out));
    if (!d) {
        return;
    }

    const uint8_t allow_paint = d->synced || !d->t.skip_until_vsync;
    if (d->de && allow_paint && d->sx < d->t.h_active && d->sy < d->t.v_active) {
        out->pixel_valid = 1;
        out->sx = d->sx;
        out->sy = d->sy;
        const uint8_t r = expand_component(red, d->t.color_depth);
        const uint8_t g = expand_component(green, d->t.color_depth);
        const uint8_t b = expand_component(blue, d->t.color_depth);
        out->argb = 0xFF000000u | (static_cast<uint32_t>(r) << 16) |
                    (static_cast<uint32_t>(g) << 8) | b;
        d->pixels_this_frame += 1;
    }

    const uint8_t vsync_now = is_active(vsync, d->t.vsync_active_low);
    const uint8_t vsync_was = is_active(d->vsync_prev, d->t.vsync_active_low);
    const uint8_t hsync_now = is_active(hsync, d->t.hsync_active_low);
    const uint8_t hsync_was = is_active(d->hsync_prev, d->t.hsync_active_low);
    const uint8_t vsync_edge = static_cast<uint8_t>(vsync_now && !vsync_was);
    const uint8_t hsync_edge = static_cast<uint8_t>(hsync_now && !hsync_was);

    if (vsync_edge && d->synced) {
        out->publish = 1;
        d->frames_complete += 1;
        d->last_v_total = d->lines_since_vsync;
        d->lines_since_vsync = 0;
        d->pixels_this_frame = 0;
    }
    if (vsync_edge) {
        d->synced = 1;
    }

    d->h_since_sync += 1;
    if (hsync_edge) {
        d->last_h_total = d->h_since_sync;
        d->h_since_sync = 0;
        d->lines_since_vsync += 1;
    }

    const uint16_t old_h = d->hcount;
    const uint16_t old_v = d->vcount;

    d->hsync_prev = hsync;
    d->vsync_prev = vsync;

    if (hsync_edge) {
        d->hcount = 0;
        if (d->vcount < (d->v_total ? d->v_total - 1 : 0)) {
            d->vcount = static_cast<uint16_t>(d->vcount + 1);
        } else {
            d->vcount = 0;
        }
    } else {
        d->hcount = static_cast<uint16_t>(d->hcount + 1);
    }
    if (vsync_edge) {
        d->vcount = 0;
    }

    d->de = static_cast<uint8_t>(
        old_h >= d->h_active_start && old_h < d->h_active_end &&
        old_v >= d->v_active_start && old_v < d->v_active_end);
    d->sx = (old_h >= d->h_active_start) ? static_cast<uint16_t>(old_h - d->h_active_start) : 0;
    d->sy = (old_v >= d->v_active_start) ? static_cast<uint16_t>(old_v - d->v_active_start) : 0;

    out->de = d->de;
    out->synced = d->synced;
    out->hcount = d->hcount;
    out->vcount = d->vcount;
    out->last_h_total = d->last_h_total;
    out->last_v_total = d->last_v_total;
    out->frames_complete = d->frames_complete;
    out->pixels_this_frame = d->pixels_this_frame;
}
