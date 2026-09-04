#ifndef FPGA_LAB_SIM_STREAMING_ABI_H
#define FPGA_LAB_SIM_STREAMING_ABI_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Pixel format: ARGB8888 packed as uint32 0xAARRGGBB, A = 0xFF.
   Qt: QImage.Format_ARGB32. Little-endian memory is B,G,R,A — matching Qt.
   sim_main.cpp omits alpha ((r<<16)|(g<<8)|b). 0xFF000000 is a deliberate
   Qt-only addition. Decoder unit tests compare (px & 0x00FFFFFF). */

#define SIM_VGA_MAX_COLOR_BITS 4
#define SIM_VGA_CHANNEL_HSYNC  0
#define SIM_VGA_CHANNEL_VSYNC  1
#define SIM_VGA_CHANNEL_R      2  /* + bit 0..3 */
#define SIM_VGA_CHANNEL_G      6
#define SIM_VGA_CHANNEL_B      10
#define SIM_VGA_CHANNEL_COUNT  14

typedef struct SimVgaTiming {
    uint16_t h_active, h_fp, h_sync, h_bp;   /* 640, 16, 96, 48 */
    uint16_t v_active, v_fp, v_sync, v_bp;   /* 480, 10,  2, 33 */
    uint8_t  hsync_active_low;               /* 1 = VGA standard */
    uint8_t  vsync_active_low;
    uint8_t  color_depth;                    /* bits per channel: 1, 2, or 4 */
    uint8_t  skip_until_vsync;               /* 1 = warmup like sim_main.cpp */
} SimVgaTiming;

typedef struct SimVgaStats {
    uint32_t frames_complete;
    uint32_t seq;
    uint32_t last_h_total;
    uint32_t last_v_total;
    uint32_t pixels_this_frame;
    uint8_t  synced;
    uint8_t  _pad[3];
} SimVgaStats;

int      sim_vga_create(uint32_t *out_id);
void     sim_vga_destroy(uint32_t id);
int      sim_vga_configure(uint32_t id, const SimVgaTiming *timing);
int      sim_vga_bind_bit(uint32_t id, uint32_t channel, int32_t port_index, uint8_t bit);
void     sim_vga_enable(uint32_t id, uint8_t enabled);
void     sim_streaming_on_posedge(void);
void     sim_streaming_reset(void);
void     sim_streaming_close(void);
uint32_t sim_vga_seq(uint32_t id);
int      sim_vga_copy_front(uint32_t id, uint32_t *dst, uint32_t dst_bytes, SimVgaStats *stats);
void     sim_vga_stats(uint32_t id, SimVgaStats *out);

#ifdef __cplusplus
}
#endif

#endif
