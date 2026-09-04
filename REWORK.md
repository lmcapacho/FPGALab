# FPGALab rework: peripheral catalog and VGA workbench

This note is for the FPGALab maintainer. It is a concise review of an architectural change already in this tree, written so you can judge whether to take it: **peripherals are a bundled catalog instead of a closed Python list**, and the workbench can show a **cycle-accurate 640×480 VGA raster** next to the existing LED and seven-segment parts.

Existing labs for the original five kinds load unchanged. Icestudio still owns `main.v` as the Verilator top module. There is no extra native dependency (no SDL, no extra process, no second window).

Date: 2026-09-02.

---

## Why two changes together

A VGA monitor cannot be “one more `if kind ==`” in `peripherals_panel.py`. Reconstructing 640×480@60 needs a sample **every virtual pixel clock** (~25 MHz, 800×525 = 420 000 cycles per frame). The workbench path that reads HDL ports once per UI frame (60 Hz) or through the 1 MHz temporal probe cannot build a picture.

So the work is:

1. A **manifest catalog** so a new part is a directory, not a patch through `wiring.py` and the panel.
2. A **streaming sink** in C++, compiled into the existing Verilator shared library, bound at runtime from lab wiring.

VGA is the first streaming sink. UART, SPI displays, or I2S can follow the same hook.

---

## Architecture (after)

```text
.ice + ice-build/main.v + main.pcf
        │
        ▼
 VerilogInterface → BoardProfile          fpga_lab/verilog_interface.py
        │
        ▼
 render_cpp_wrapper + native/*.cpp        fpga_lab/cpp_wrapper.py
        │                                 fpga_lab/native/
        ▼
 Verilator --top-module <student main>
        │
        ▼
 ctypes VerilatorSimulation               fpga_lab/simulation.py
        │
        ▼
 SimulationWorker (QThread)               fpga_lab/simulation_worker.py
        │
        ├── BoardView                     on-board LEDs / switches
        └── PeripheralsPanel              catalog + workbench
                 ▲
                 │
          lab.json + PCF
          terminal → header pin → FPGA pin → HDL net
```

Unchanged properties of the engine:

- Virtual clock `--clock-hz` (12 MHz default), UI `--ui-refresh-hz` (60), LED probe `--observation-hz` (1 MHz).
- Batched `run_cycles` in C++; the GUI never ticks at FPGA rate.
- One global Verilator model per process.
- New C++ is **package data** compiled **into** the per-design `.so` / `.dylib` / `.dll` at Verilator time (PyInstaller already collects `fpga_lab` data). Not a prebuilt extra dylib.

---

## Decisions that shaped the patch

These are the constraints we treated as non-negotiable so the original engine stays intact.

| Choice | Why |
| --- | --- |
| Bundled `manifest.json` + optional QPainter renderer, not setuptools plugins | Deletes the `if kind ==` tax. A third-party plugin API can wait. |
| VGA capture in C++, always linked into the Verilator library, **bound at Play** | Lab pin changes must not force a rebuild. The cache fingerprint stays lab-free. |
| Student `main.v` remains `--top-module` | A Verilog wrapper around `main` would invent `sx`/`sy`/`de` ports and change discovery. Timing reconstruction lives in C++. |
| PyQt `QImage` on the workbench, not SDL | Same item model as seven-segment. No new packaging dependency. |
| Worker-side `memcpy` of the latest 640×480 ARGB frame (~1.23 MiB) into Python `bytes` | `run_cycles` releases the GIL. Qt never wraps a C++ pixel pointer, so Stop / `close_sim` cannot UAF the image. |
| Sample VGA every posedge; never through `g_observation_divisor` | The LED probe is 1 MHz. VGA is a pixel clock. Clockless tops reject a VGA part before Play. |
| `observed` = PCF-mapped `LED0`–`LED7` only | Lab-derived observation would rebuild on pin changes. Workbench LEDs stay end-of-frame booleans. |
| `SimulationFrame` instead of the leftover 4-tuple | `segments` / `gpio_out` were unused. A new sink must not extend a positional signal. |
| Do not silently raise `--clock-hz` | Physical Alhambra is 12 MHz. Warn in the status bar when a VGA part is present and the clock is still 12 MHz. |
| One monitor instance in this version | Twenty header pins. The ABI still takes a `sink_id` so a second monitor is not another ABI break. |

What we deliberately did **not** do: wrap `main.v`, add SDL or Chromium, put VGA bits on the 64-bit temporal probe, PWM-dim workbench LEDs, or auto-rewrite the CLI clock.

---

## 1. Generalised components

### Before

`fpga_lab/wiring.py` owned a closed dict (`led`, `traffic_light`, `seven_segment`, `button`, `sensor`). Adding a part meant editing that dict, `PeripheralConfigDialog`, `WorkbenchPeripheralItem.paint()`, mouse handlers, and locales. `SimulationWorker.state_changed` was a positional tuple `(leds, segments, gpio_out, outputs)` of which the panel only used the last field.

### After

Each part is:

```text
fpga_lab/peripherals/<id>/manifest.json
fpga_lab/peripherals/renderers/<name>.py   # optional; reuse lamp/button/…
```

`load_catalog()` loads every `*/manifest.json`. The directory name must match `id`. `wiring.py` still owns `PeripheralInstance`, `ResolvedWire`, and `VirtualLabProject`; `PERIPHERAL_TERMINALS` / `PERIPHERAL_LABELS` are **aliases** computed from the catalog.

Direction in the manifest is **from the FPGA** (LED `anode` is an FPGA output; a button `signal` is an FPGA input). Resolution is unchanged:

**terminal → board endpoint (D0–D13, DD0–DD5) → PCF pin → HDL net**

Unknown `type` still raises `Unknown peripheral type`.

### Manifest (example)

```json
{
  "id": "led",
  "label": "LED",
  "category": "output",
  "simulation": { "class": "gpio_sampled" },
  "terminals": [
    { "name": "anode", "direction": "output", "width": 1, "required": true }
  ],
  "properties": {
    "color": { "type": "color", "default": "#b6ff00", "label": "Color" }
  },
  "visual": { "renderer": "lamp", "size": [120, 88] }
}
```

`simulation.class`:

| Class | Role |
| --- | --- |
| `gpio_sampled` | FPGA outputs, painted from the end-of-frame port snapshot |
| `gpio_driven` | Workbench writes HDL inputs (button, sensor) |
| `streaming_sink` | Cycle-accurate C++ capture (`sink_kind`: `vga`) |

Property types drive a **generic** config dialog: `color`, `color_map`, `enum`, `boolean`, `string`. `position` is reserved (drag on the canvas) and must not be dropped on save.

The five original kinds keep the same lab JSON (`type`, `connections`, `properties.color` / `common` / `colors`). Workbench LEDs remain end-of-frame booleans (on-board LEDs still use `LedModel` PWM).

`SimulationWorker` now emits a `SimulationFrame` (`led_brightness`, `outputs`, `sinks`, `virtual_hz`, `cycles`) instead of the leftover 4-tuple.

### How to add a GPIO part

1. `fpga_lab/peripherals/<id>/manifest.json` (`id` = folder name).
2. Reuse a renderer or add `renderers/<name>.py` and register it in `renderers/__init__.py`.
3. Spanish label in `fpga_lab/locales/es.json` (English is the `t()` source string).
4. A lab fixture under `tests/fixtures/labs/` and a `VirtualLabProject.resolve` test.

Do not touch `cpp_wrapper.py` unless the part needs a new **simulation class**.

---

## 2. VGA integration

### Capture path

`fpga_lab/native/vga_decoder.cpp` is Verilator-free: `create` / `destroy` / `reset` / `posedge`. It reconstructs `sx`/`sy`/`de` from HSYNC/VSYNC edges (640/16/96/48 and 480/10/2/33, origin = start of sync pulse). RGB is the current post-`eval()` value; `de`/`sx`/`sy` are registered from the **previous** counters (Verilog NBA). Colour expand: 1-bit → 0x00/0xFF; 2-bit → 0x00/0x55/0xAA/0xFF; 4-bit → `(c<<4)|c`. Pixels are `0xAARRGGBB` with A = 0xFF (Qt `Format_ARGB32`).

`sim_streaming.cpp` owns a double buffer (`back` / `latest`). The generated clocked loop, after the rising `eval()`, does:

```cpp
if (g_sink_enabled) sim_streaming_on_posedge();
```

Clockless designs do not call the hook; a VGA part on a combinational top is rejected before Play.

After `ticks()` returns, the **worker thread** copies `latest` with `sim_vga_copy_front` into Python `bytes` (~1.23 MiB). The UI never wraps a C++ pointer. The item keeps a `bytearray` as the `QImage` backing store. The active image is **640×480, 1:1** (plus a thin bezel).

`pixels is None` keeps the last image (reset / waiting for VSYNC). `pixels == b""` blanks the CRT (Stop). Bindings are re-collected on **every Play**, so Stop → add/rewire monitor → Run does not require a rebuild.

A 512×480 active region on an 800×525 frame still measures H total ≈ 800, so the “unexpected H total” overlay stays quiet. The picture looks shifted; that is expected. The supported mode is 640×480.

### Binding

Students name Icestudio nets arbitrarily. The only stable path is the one the workbench already uses:

```text
lab connections["r0"] = "D2"
  → BoardDefinition.pin("D2").fpga_pin
  → PCF net (e.g. vga_r[0] or v6a65cd[3])
  → signal_reference(net, profile.outputs)
  → (port_name, bit) → index in profile.outputs
```

`fpga_lab/sink_bind.py` distinguishes unconstrained pins (not in the PCF) from nets that exist but are not outputs (inout/clock). Required terminals missing show an overlay instead of crashing.

`sim_read_output(index)` walks `profile.outputs` in **insertion order** (not sorted). Cache format is **3**; native sources are hashed so a decoder fix invalidates the cache. `observed` is LED-only (full width of PCF-mapped `LED0`–`LED7` ports), lab-independent.

### Catalog parts

Each colour depth is a **separate** part (fixed terminals, no depth dropdown):

| Part | Bits / colour | Pins (incl. sync) | Suggested header |
| --- | --- | --- | --- |
| `vga_monitor` (VGA 1-bit) | 1 | 5 | D0–D4 |
| `vga_6bit` | 2 | 8 | D0–D7 |
| `vga_12bit` | 4 | 14 | D0–D13 |

`r0`/`g0`/`b0` are LSBs. Sync default is active-low (configurable). One sink instance in this version (`sim_vga_create` fails if a second monitor is enabled).

Example labs (copy into `~/FPGALab/labs` if needed):

- `fpga_lab/assets/labs/vga_640x480_1bit.lab.json`
- `fpga_lab/assets/labs/vga_640x480_6bit.lab.json`
- `fpga_lab/assets/labs/vga_640x480_12bit.lab.json`

### Clock

Physical Alhambra II is 12 MHz. 640×480@60 wants ~25.175 MHz as **pixel clock**. `--clock-hz` is already “virtual Hz”. VGA-ok values: `25000000` and `25175000`. If a VGA part is present and the clock is still `12000000`, Play emits a status warning. The CLI flag is never rewritten.

A host that cannot sustain 25 MHz still shows the latest **complete** frame (the worker already caps a pause at 100 ms of virtual time). Do not expect locked 60 FPS laptop playback.

### Tests

`pip install -e ".[dev]"` then `pytest`. Catalog, wiring, property schema, profile policy, wrapper symbols, sink bind, `SimulationFrame`, and a `g++` harness for `vga_decoder.cpp` (`tests/native/vga_decoder_harness.cpp`). Verilator is not required for those unit tests. There was no pytest suite in the tree before this work.

---

## How to evaluate

Python 3.10+ (the package requires `>=3.10`). From the FPGALab checkout:

```bash
python3.14 -m venv .venv   # do not use a 3.9 system python
source .venv/bin/activate
pip install -e ".[dev]"
pytest
fpga-lab --clock-hz 25000000
```

Open an Icestudio design that drives VGA, pick a lab with a matching monitor (`VGA 1-bit` / `VGA 6-bit` / `VGA 12-bit`), assign every terminal, Run. The first complete frame appears after VSYNC.

Existing LED / traffic-light / seven-segment / button / sensor labs should look and behave as before (workbench LEDs still boolean, on-board LEDs still PWM).

---

## Files to review first

| Area | Paths |
| --- | --- |
| Catalog | `fpga_lab/peripherals/`, `fpga_lab/wiring.py` |
| Native sink | `fpga_lab/native/`, `fpga_lab/cpp_wrapper.py`, `fpga_lab/compiler.py`, `fpga_lab/build_cache.py` |
| Bind + worker | `fpga_lab/sink_bind.py`, `fpga_lab/simulation.py`, `fpga_lab/simulation_worker.py`, `fpga_lab/virtual_lab.py` |
| Workbench | `fpga_lab/peripherals_panel.py`, `fpga_lab/app.py` |
| Tests | `tests/` |

---

## Compatibility

- Existing labs with `led` / `traffic_light` / `seven_segment` / `button` / `sensor` load as before.
- A lab with `vga_monitor` / `vga_6bit` / `vga_12bit` on an older binary fails `resolve()` with `Unknown peripheral type` (same closed-catalog behaviour as today).
- Cached libraries from format 2 are not reused (format 3 + native hash).

---

**Author:** Carlos Venegas  
**Email:** carlos@magnitude.es  
**@cavearr**
