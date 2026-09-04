#ifndef FPGA_LAB_VGA_DECODER_H
#define FPGA_LAB_VGA_DECODER_H

#include "sim_streaming_abi.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct VgaDecoder VgaDecoder;  /* incomplete; allocate only via create */

VgaDecoder *vga_decoder_create(const SimVgaTiming *t);
void        vga_decoder_destroy(VgaDecoder *d);
void        vga_decoder_reset(VgaDecoder *d);

typedef struct VgaPosedgeOut {
    uint8_t  pixel_valid;
    uint16_t sx, sy;
    uint32_t argb;
    uint8_t  publish;
    uint8_t  de, synced;
    uint16_t hcount, vcount;
    uint32_t last_h_total, last_v_total;
    uint32_t frames_complete;
    uint32_t pixels_this_frame;
} VgaPosedgeOut;

void vga_decoder_posedge(VgaDecoder *d,
                         uint8_t hsync, uint8_t vsync,
                         uint8_t red, uint8_t green, uint8_t blue,
                         VgaPosedgeOut *out);
uint8_t  vga_decoder_de(const VgaDecoder *d);
uint16_t vga_decoder_sx(const VgaDecoder *d);
uint16_t vga_decoder_sy(const VgaDecoder *d);

#ifdef __cplusplus
}
#endif

#endif
