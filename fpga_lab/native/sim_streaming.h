#ifndef FPGA_LAB_SIM_STREAMING_H
#define FPGA_LAB_SIM_STREAMING_H

#include "sim_streaming_abi.h"

#ifdef __cplusplus
extern "C" {
#endif

extern uint8_t g_sink_enabled;

uint64_t sim_read_output(uint32_t index);

#ifdef __cplusplus
}
#endif

#endif
