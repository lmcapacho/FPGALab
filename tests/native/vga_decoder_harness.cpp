#include "vga_decoder.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

static SimVgaTiming standard_timing() {
    SimVgaTiming t{};
    t.h_active = 640;
    t.h_fp = 16;
    t.h_sync = 96;
    t.h_bp = 48;
    t.v_active = 480;
    t.v_fp = 10;
    t.v_sync = 2;
    t.v_bp = 33;
    t.hsync_active_low = 1;
    t.vsync_active_low = 1;
    t.color_depth = 4;
    t.skip_until_vsync = 1;
    return t;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: vga_decoder_harness TRACE.jsonl\n");
        return 2;
    }
    FILE *fp = std::fopen(argv[1], "r");
    if (!fp) {
        std::perror(argv[1]);
        return 2;
    }
    SimVgaTiming timing = standard_timing();
    VgaDecoder *decoder = vga_decoder_create(&timing);
    if (!decoder) {
        return 3;
    }
    char line[256];
    while (std::fgets(line, sizeof(line), fp)) {
        int hsync = 1, vsync = 1, red = 0, green = 0, blue = 0;
        if (std::sscanf(line, "%d %d %d %d %d", &hsync, &vsync, &red, &green, &blue) != 5) {
            continue;
        }
        VgaPosedgeOut out{};
        vga_decoder_posedge(decoder, static_cast<uint8_t>(hsync), static_cast<uint8_t>(vsync),
                            static_cast<uint8_t>(red), static_cast<uint8_t>(green),
                            static_cast<uint8_t>(blue), &out);
        std::printf("%u %u %u %u %08x %u %u %u\n",
                    out.pixel_valid, out.sx, out.sy, out.publish, out.argb,
                    out.last_h_total, out.synced, out.frames_complete);
    }
    vga_decoder_destroy(decoder);
    std::fclose(fp);
    return 0;
}
