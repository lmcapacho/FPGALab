"""Generación de la capa ABI C que enlaza Python con el modelo Verilator."""

from __future__ import annotations

from .profile import BoardProfile


def render_cpp_wrapper(profile: BoardProfile, model_class: str = "Vtop") -> str:
    """Crea una API sin mangling: init/reset/eval y lecturas/escrituras por puerto."""
    setters = "\n".join(
        f"void sim_set_{name}(uint64_t value) {{ if (g_top) g_top->{name} = value; }}"
        for name in profile.inputs
        if name != "clk"
    )
    getters = "\n".join(
        f"uint64_t sim_get_{name}() {{ return g_top ? static_cast<uint64_t>(g_top->{name}) : 0; }}"
        for name in profile.outputs
    )
    return f'''// Generado por FPGALab. No editar: cambie board_profile.json.
#include "{model_class}.h"
#include "verilated.h"
#include <cstdint>

static {model_class}* g_top = nullptr;
static VerilatedContext* g_context = nullptr;

extern "C" {{

void init_sim() {{
    if (g_top) return;
    g_context = new VerilatedContext;
    g_top = new {model_class}{{g_context}};
    g_top->clk = 0;
    g_top->eval();
}}

void reset_sim() {{
    if (!g_top) init_sim();
    g_top->final();
    delete g_top;
    delete g_context;
    g_top = nullptr;
    g_context = nullptr;
    init_sim();
}}

void close_sim() {{
    if (!g_top) return;
    g_top->final();
    delete g_top;
    delete g_context;
    g_top = nullptr;
    g_context = nullptr;
}}

void eval_sim() {{ if (g_top) g_top->eval(); }}
void sim_set_clk(uint8_t value) {{ if (g_top) g_top->clk = value ? 1 : 0; }}
uint8_t sim_get_clk() {{ return g_top ? static_cast<uint8_t>(g_top->clk) : 0; }}
void step_clock() {{
    if (!g_top) init_sim();
    g_top->clk = 1; g_top->eval();
    g_top->clk = 0; g_top->eval();
    g_context->timeInc(1);
}}
void run_cycles(uint64_t cycles) {{
    if (!g_top) init_sim();
    for (uint64_t cycle = 0; cycle < cycles; ++cycle) {{
        g_top->clk = 1; g_top->eval();
        g_top->clk = 0; g_top->eval();
        g_context->timeInc(1);
    }}
}}

{setters}

{getters}

}} // extern "C"
'''
