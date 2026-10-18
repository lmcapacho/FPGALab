# Architecture and contribution

## Simulation architecture

```text
Icestudio design (.ice)
        │
        ├── ice-build/<design>/main.v ──► Verilog interface + board profile
        └── ice-build/<design>/main.pcf or main.xdc
                  │                         │
                  └── HDL nets ↔ FPGA pins ↔ board endpoints
                                            │
                                            ▼
                       Verilator incremental build cache
                                            │
                       generated C++ wrapper + native capture
                                            │
                                            ▼
                    per-design library (.so / .dll / .dylib)
                                            │
                                      ctypes binding
                                            │
                                            ▼
                              SimulationWorker (Qt thread)
                                            │  compact SimulationFrame updates
                         ┌──────────────────┴──────────────────┐
                         ▼                                     ▼
                 Board view and controls           Peripheral workbench
                 (SVG + layout JSON)               (Lab + catalog manifests)
                                                               │
                                             GPIO / temporal / VGA / edge streams

Lab connection: peripheral terminal → board endpoint → FPGA pin → HDL net
```

The native wrapper batches virtual FPGA cycles and publishes `SimulationFrame` objects. GPIO inputs, sampled outputs, temporal observations, and streaming sinks such as VGA remain separate data paths.

The generated C++ wrapper exposes input setters, output getters, clock stepping,
batched execution, temporal measurements, and streaming hooks through a native
ABI. Python binds the per-design shared library (`.so`, `.dll`, or `.dylib`)
with `ctypes`; `SimulationWorker` runs it off the GUI thread and delivers compact
frames to the board and workbench. Qt does not refresh at the FPGA clock rate.
Incremental builds are kept in a managed user cache, outside Icestudio's
`ice-build` directory.

GPIO inputs, sampled outputs, temporal observations for LEDs and displays,
cycle-accurate VGA streaming, and edge streams/timed input for the development
UART/SPI API are distinct paths within that runtime flow.
The basic SPI MISO responder is a native reactive byte source configured through
the worker; it observes SCK/CS every virtual cycle without per-cycle Python work.
Its protocol state is separate from the bounded edge queue used by the monitor.

Project constraints map generated HDL names to physical board endpoints, so
LEDs and controls work even when the HDL net is not named after its visual
label. A peripheral may stay physically connected in a Lab when the current
HDL does not use that board pin.

## Main modules

- `app.py`: application orchestration and build lifecycle.
- `compiler.py` and `build_cache.py`: Verilator generation and incremental native builds.
- `simulation.py` and `simulation_worker.py`: native binding and background execution.
- `virtual_lab.py`: board/workbench composition.
- `peripherals/catalog.py` and `peripherals/manifest.py`: declarative catalog.
- `workbench/view.py` and `workbench/item.py`: canvas interaction and rendered instances.
- `wiring.py`: Lab terminal-to-board-to-HDL resolution.

Board assets live together in `fpga_lab/assets/boards/<board-id>/`. Each board
directory keeps its definition, pin constraints, profile, layout, and SVG in
one place. The Alhambra II directory is the reference layout for future boards.

| File | Purpose |
| --- | --- |
| `board.json` | Board identity, physical endpoints, clock, and integrated controls. |
| `pinout.pcf` or `pinout.xdc` | Reference pin constraints; include exactly one. |
| `profile.json` | Native-model input and output port profile. |
| `layout.json` | Interactive controls, placement, and SVG reference. |
| `board.svg` | Scalable artwork. |

FPGALab consumes the project-specific `main.pcf` or `main.xdc` in the Icestudio
project's `ice-build` directory; a board package provides exactly one
`pinout.pcf` or `pinout.xdc` as its pinout reference. For XDC, FPGALab reads
literal `set_property PACKAGE_PIN <pin> [get_ports {<port>}]` assignments,
including bus bits and the `-dict` form. Other XDC commands are not evaluated.
Unsupported `PACKAGE_PIN` expressions produce an error rather than an empty map.
`BoardCatalog` discovers these directories and validates their required files,
definition, layout, profile, and pin constraints. Invalid packages are skipped with a
diagnostic. Its `board_id` is the directory name (for example, `alhambra_ii`);
the `id` in `board.json` remains the board's public identifier.
Labs store the public identifier in `metadata.board_id`. The GUI resolves it to
the package directory ID when opening a Lab; changing the board selector updates
that Lab metadata. Labs without this field use the default Alhambra II board.
An optional positive `metadata.virtual_clock_hz` overrides the board's `clock_hz`
for that Lab. Changing the board clears the override. Interface refresh and
temporal sampling are user-wide settings; `--clock-hz` is a session override.
In `layout.json`, a board LED may declare `"role": "power"` and a board button
may declare `"role": "reset"`. These optional roles control the simulation
indicator and reset action without depending on the elements' signal names.
Select the element in Edit layout to assign its role; each role can belong to
only one element.
The selected element's Board signal field lists logical endpoint identifiers
from `board.json`, not physical FPGA pin numbers or project-specific HDL nets.
LEDs list output/inout endpoints; buttons list input/inout endpoints, excluding
the clock. Special power/reset roles allow internal signal names. Existing
unavailable values remain marked and preserved; empty signals cannot be saved.
The editor sidebar separates selected-component properties and actions from
component creation, whole-board appearance (rotation/mirroring), and editor
view controls. Save and Close remain at the bottom of the panel.
The window geometry and canvas/properties divider are remembered per user.
New components use a single form containing role, identifier and signal;
invalid or duplicate identifiers remain in the form for correction.
Component creation starts with the role. Normal controls select a board signal;
power indicators and simulation reset buttons use an internal identifier
(suggested defaults: `PWR` and `RESET`) without requiring an FPGA pin. The role,
not the identifier's spelling, determines the behavior. Assigning an existing
role to another element transfers it to that element.
The `controls.leds` order in `board.json` determines the order of LED samples
published by the worker. Each endpoint name selects the corresponding visual
LED in `layout.json`; a board may declare any number of LEDs, including none.

## Board integration: iCEBreaker Bitsy

A pin in `board.json` may declare `"active_low": true` (default: false).
Integrated LED measurements are inverted before visual persistence, and an
active-low button drives 1 when released and 0 when pressed. Button idle levels
are restored before Run and after a board reset. Physical pin aliases remain
mapped to the same HDL net; reverse lookup prefers a header endpoint.

The `icebreaker_bitsy_v1/` package integrates a second board through the same
definition, pinout, profile, layout and artwork structure used by Alhambra II.
It uses Icestudio's `iCEBreaker-bitsy1` identifier. Validated support covers the
12 MHz clock, active-low user LEDs, integrated button, external GPIO and
per-Lab board selection. USB, flash, PSRAM and RGB hard IP are not modeled.
The artwork is cropped from the upstream iCEBreaker information card; see
the board package's `ATTRIBUTION.md` for source and credits.
When switching boards, connections to unavailable pins remain in the Lab,
inactive with a compatibility notice. Assignments are not automatically
translated between boards; switching back restores their resolution without
losing connections.

## Experimental self-contained Linux toolchain

`packaging/linux_toolchain/build.py` is a **maintainer prototype**, not the
first-run downloader or a new installation requirement. It snapshots installed
Debian/Ubuntu packages into a private SDK: Verilator, GNU Make, GCC/G++, binutils,
Perl, Python and build utilities, including headers, libraries and copyrights.
It installs no host packages and leaves existing FPGALab discovery unchanged.
The package list and exact versions, build OS and glibc are recorded in
`toolchain.json`. Only Linux x86-64 is supported at this stage; the first local
baseline is Ubuntu 24.04/glibc 2.39. This is not a universal Linux binary.

```bash
python3 packaging/linux_toolchain/build.py \
  --output /tmp/fpgalab-sdk \
  --archive /tmp/fpgalab-sdk.tar.gz
.venv/bin/python packaging/linux_toolchain/probe.py \
  --sdk /tmp/fpgalab-sdk --work-dir /tmp/fpgalab-sdk-probe --isolated
```

Use new, nonexistent output/work directories without whitespace. The optional
archive contains the SDK plus a SHA-256 sidecar; a checksum alone is not proof
of trusted provenance. The builder refuses to overwrite existing outputs.
Generate release candidates on a controlled build machine, not from arbitrary
developer installations. Binary redistribution and corresponding-source/license
obligations still require review before publishing; included copyrights do not
complete that review. Do not commit SDK binaries to the repository.

The isolated probe requires **bubblewrap on the maintainer machine only**.
It mounts the SDK and a temporary work directory, with only the host shell,
`env`, loader and libc as OS plumbing; host compilers, headers, Apio and network
are unavailable. It uses FPGALab's generated C ABI, compiles synthetic Verilog,
loads the shared library and verifies combinational logic, clock cycles and
Reset. Make is run again to check the completed build. Move the SDK to another
directory and run a fresh probe to verify relocation; do not reuse generated
Makefiles referring to its old path. Without `--isolated`, only PATH isolation
is checked, which is not evidence of independence from host headers/libraries.

Tools use their packaged loader/libraries and a private PATH. GCC uses the
packaged sysroot; Python and Perl use their private standard libraries. This
prototype still relies on the Linux kernel and basic shell plumbing. Generated
models are loaded into the application's process and must match its host ABI;
older glibc, other distributions/architectures, whitespace paths and GUI runtime
compatibility need separate qualification. First-run download, automatic SDK
selection, signing and installers are later steps, not provided by these scripts.

## External peripherals

The [external peripheral API v1](peripheral-api.md) documents the manifest fields, reusable renderers, package metadata, examples, validation, and installation. Use it when creating a shareable package. FPGALab does not load Python code from user peripheral folders.

There are two different locations:

```text
# Bundled with FPGALab (core repository; may use an internal renderer)
fpga_lab/peripherals/<peripheral-id>/
├── manifest.json
└── icon.svg
fpga_lab/peripherals/renderers/<renderer>.py

# External/installable package (declarative; no Python code)
examples/peripherals/<peripheral-id>/
├── manifest.json
├── icon.svg
└── artwork SVG files referenced by the manifest
```

Add a bundled peripheral only when its behavior belongs in the core catalog.
For a shareable component, start in `examples/peripherals/`, validate the
folder, and install it from the catalog or package it as a ZIP. External
packages must use one of the renderers already provided by FPGALab.

## Add a bundled peripheral

Create `fpga_lab/peripherals/<id>/manifest.json` and its licensed SVG resources. Define terminal direction, required connections, properties, visual renderer, size, and simulation mode. Reuse a generic renderer when possible; add a renderer class under `fpga_lab/peripherals/renderers/` only when the behavior cannot be described by existing primitives.

See the [API reference](peripheral-api.md#visual-reusable-renderers) for the available renderers and their manifest fields.

Run the tests before opening a pull request:

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest -q
```

Keep source code, identifiers, and developer comments in English. User-visible text must pass through the translation layer.
