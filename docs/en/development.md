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
                             SimulationEngine (Qt-free)
                                            │
                              SimulationWorker (Qt adapter)
                                            │  compact SimulationFrame updates
                         ┌──────────────────┴──────────────────┐
                         ▼                                     ▼
                 Board view and controls           Peripheral workbench
                 (SVG + layout JSON)               (Lab + catalog manifests)
                                                               │
                                             GPIO / temporal / VGA / edge streams

Lab connection: peripheral terminal → board endpoint → FPGA pin → HDL net
```

The native wrapper batches virtual FPGA cycles; `SimulationEngine` collects
results into `SimulationFrame` objects. GPIO inputs, sampled outputs, temporal
observations and streaming sinks such as VGA remain separate data paths.

The generated C++ wrapper exposes input setters, output getters, clock stepping,
batched execution, temporal measurements, and streaming hooks through a native
ABI. Python binds the per-design shared library (`.so`, `.dll`, or `.dylib`)
with `ctypes`; `SimulationEngine` owns execution and capture without Qt.
`SimulationWorker` schedules that engine off the GUI thread and delivers compact
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

### Framework-free core boundary

Board definitions/catalogs/layout data, profiles, constraints and wiring,
compiler/wrapper generation, build caching/toolchain resolution, native-model
bindings, temporal models and UART/SPI decoding/scheduling can be imported
without PyQt6 or a Qt application. These modules do not read Qt user preferences.
Use explicit build requests/profiles and toolchain paths/environment for headless
hosts. The package still installs PyQt6 for its desktop application; a separate
headless distribution is not provided.

`messages.py` formats English source messages by default, without loading locale
catalogs or preferences. A host may explicitly install a process-wide translation
callback with `set_translator`; `None` restores English. Importing the desktop
`i18n.py` adapter installs the active Qt language manager's translator, preserving
live language changes and catalog-formatting fallback. This callback is not a
per-request language setting: concurrent web clients should not switch it for
each request. A future server adapter must handle request-specific presentation.

For a precompiled native model and its matching profile:

```python
from fpga_lab.profile import BoardProfile
from fpga_lab.simulation import VerilatorSimulation

profile = BoardProfile.load("profile.json")
with VerilatorSimulation("./model.so", profile) as model:
    model.set_input("button", 1)  # Must be an input in this profile.
    model.ticks(1000)
    print(model.get_output("led"))  # Must be an output in this profile.
```

Use the appropriate library extension for the host. Native execution still
requires a compatible compiled model; removing Qt imports does not supply a
toolchain or sandbox native code. `SessionService` prepares, builds and opens
native sessions without Qt; workspace preferences, settings dialogs and visual
coordination remain desktop concerns. `SimulationWorker` is the timer/signals
adapter for the independent engine. No web server is provided.
Regression tests block Qt imports in a fresh process, prepare a native build and
exercise the generated C ABI with a synthetic model.

### Execution engine and host scheduling

`simulation_engine.py` owns model execution and frame data. It has no timer or
event loop: a host supplies elapsed wall time to `advance(seconds)`. `play()`
enables advancement; `pause()` suspends it without resetting the model.
`power_off()` stops and resets native capture/input queues and returns a blank
frame. `reset()` clears native state/queues while retaining whether execution
was running. `close()` closes the owned model once and disallows further use.
Keep all engine/model operations on one owner thread; it is not a thread-safe,
multi-client session manager and does not start a background thread.

```python
from fpga_lab.profile import BoardProfile
from fpga_lab.simulation import VerilatorSimulation
from fpga_lab.simulation_engine import SimulationEngine

profile = BoardProfile.load("profile.json")
engine = SimulationEngine(VerilatorSimulation("./model.so", profile), clock_hz=12_000_000)
try:
    engine.play()
    frame = engine.advance(1 / 60)  # Explicit elapsed time; not a sleep.
    print(frame.outputs)
    engine.reset()
    blank_frame = engine.power_off()
finally:
    engine.close()
```

Use the board/session's configured clock rather than assuming the example's
12 MHz. The desktop worker supplies actual monotonic elapsed time from its Qt
timer. Catch-up stays capped at 100 ms per call, with fractional-cycle carry;
speed measurement uses uncapped wall time. Frames retain native-cycle timestamps
and report dropped edges, discarding an incomplete edge batch on overflow.
Pulse widths and LED persistence use virtual time, not host refresh intervals.
UART scheduling and native SPI/VGA configuration belong to the same engine.
Exceptions propagate to a headless host; the Qt adapter maps them to the existing
failure/notice signals and stops its timer on execution failure. After power-off,
combinational input changes do not publish fresh output frames until Run.

### Session preparation, build and ownership

`session.py` exposes a synchronous `SessionService` shared by the desktop and
headless hosts. It does not open dialogs, read QSettings, start threads or choose
a language. `prepare(ice_file, lab_file=..., board_id=..., profile=..., clock_hz=...)`
reads the existing Icestudio export, resolves the board/profile and PCF/XDC,
and returns a `PreparedSession` with integrated-control mappings, peripheral
wires, the unmodified `lab_document` (including metadata/annotations) and
compatibility warnings. Treat the preparation's nested dictionaries as read-only.
Unknown peripheral instances/connections
remain preserved in the source Lab; preparation never imports or rewrites it.
An explicit board/clock takes precedence over Lab metadata; otherwise the Lab's
board and clock override apply, falling back to the default board and its clock.
The optional manual profile is a `BoardProfile`, not a filename.

`build(prepared, verilator=..., optimization_mode=..., cancel_requested=...)`
uses the managed exact/incremental cache and checks cancellation before/after
the build as well as forwarding it to the compiler. It does not replace the
active session. `open(prepared, artifact, observation_hz=...)` stops/closes the
service's previous session before native initialization, then creates a paused
engine with integrated-control idle levels (including active-low buttons).
The host receives a `SimulationSession` containing the preparation, artifact,
native binding and engine. `close()` is idempotent; setup failures close a model
that was already loaded. Keep prepared results paired with their own artifacts.

```python
from fpga_lab.session import SessionService

service = SessionService(cache_dir="/path/to/managed-cache")
prepared = service.prepare("design.ice", lab_file="example.lab")
artifact = service.build(prepared, verilator="/path/to/sdk/bin/verilator")
session = service.open(prepared, artifact)
try:
    session.engine.play()
    frame = session.engine.advance(1 / 60)
    print(frame.outputs, prepared.wires, prepared.warnings)
    session.engine.reset()
    session.engine.power_off()
finally:
    service.close()
```

Existing exports in `ice-build` and a compatible toolchain remain required.
Build calls block their caller: the desktop's `BuildWorker` runs them outside
the GUI thread. Only immutable/read-only preparation/build data cross that
boundary; opening and model operations stay with the model owner. The desktop
closes its old worker before `open`, then transfers the new engine to its Qt
worker; do not call service/model operations concurrently from another thread.
Separate services do not isolate the process-global C ABI: the same shared
library must not have multiple live owners in one process.

This is the native session foundation, not a headless renderer of a Lab or a
server API. There is no HTTP transport, multi-user isolation or public-server
sandbox in this API.

### Peripheral channel planning

`peripherals.channel_plan.build_channel_plan(project, wires, profile, catalog=...)`
builds an immutable `ChannelPlan` without Qt. Pass a `VirtualLabProject`, its
board/constraint-resolved wires and the native model's `BoardProfile`. The
optional catalog is a mapping of type identifiers to `PeripheralSpec`; omission
loads the bundled/user catalog. Preparation does not change the Lab or configure
the engine.

The plan includes temporal predicates, capture/drive channels and native SPI
response configuration. Bindings identify `(peripheral_id, terminal)` rather
than widgets. Channel indices follow project/manifest order; output indices
follow profile order. Unavailable types and unmapped or invalid HDL references
allocate no channels. Display common polarity/gating and SPI response warnings
retain the desktop behavior.

Hosts can pass `plan.temporal_probes`, `plan.edge_channels`,
`plan.drive_channels` and `plan.spi_slaves` to the engine's corresponding
configuration methods on its owner thread. Preserve tuple order when routing
frames and send results back to bindings. The desktop maps identifiers to
workbench items and emits its existing Qt configuration signals. Presentation
and frame routing remain desktop concerns; this plan is not a complete Lab runtime.

### Serial peripheral state

`peripherals.serial_runtime.UartTerminalRuntime` and `SpiMonitorRuntime` own
receive decoding, bounded text history, error counters and partial-frame state
without Qt. Construct either with its validated manifest `visual` configuration;
artwork and size are not needed by these classes. Feed the matching
`PeripheralInstance` and virtual-cycle events through `feed_edges(...)` (UART)
or `feed_edge_frame(...)` (SPI, terminal/event pairs). Each call returns the text
appended to history. The immutable `state` snapshot exposes `text`, `dropped`,
`configured`, `framing_errors` and `invalid_baud` for presentation.

`suspend_stream()` discards partial decoding and counters while retaining output
(desktop Stop). `reset_stream()` clears receive state and output for a fresh
monitor; `preserve_output=True` keeps history. A cycle rollback or changed protocol
settings also discards partial state while keeping history. `clear_output()`
clears only text, not protocol alignment. Damaged overflow frames are discarded,
not decoded; previous history remains. Apply these operations on one owner thread.

The Qt renderers delegate to these runtimes and paint snapshots; workbench
widgets retain their scroll/copy controls and route lifecycle calls. Another host
can instantiate the runtimes directly without importing renderers. SPI's
`response_enabled` reflects a successfully bound native responder; the runtime
only labels the configured response, it does not drive MISO. UART transmission
and SPI responses still execute through the engine/native layer. GPIO interaction,
temporal presentation and whole-Lab orchestration are not covered by these two
serial runtimes. External packages remain declarative and need no format changes.

### Module map

- `app.py`: desktop coordination and asynchronous build presentation.
- `session.py`: GUI-independent preparation, cached builds and native-session ownership.
- `compiler.py` and `build_cache.py`: Verilator generation and incremental native builds.
- `simulation.py`: native binding; `simulation_engine.py`: execution and frame contracts.
- `simulation_worker.py`: Qt timer, thread-lifecycle and signal adapter.
- `virtual_lab.py`: board/workbench composition.
- `peripherals/catalog.py` and `peripherals/manifest.py`: declarative catalog.
- `workbench/view.py` and `workbench/item.py`: canvas interaction and rendered instances.
- `wiring.py`: Lab terminal-to-board-to-HDL resolution.

## Board packages

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

### Project constraints versus reference pinout

These files have different roles:

- **Project `main.pcf` or `main.xdc`:** read from the Icestudio project's
  `ice-build/<design>/` directory. Maps that design's HDL nets to FPGA pins.
- **Board `pinout.pcf` or `pinout.xdc`:** included in the board package as its
  reference pinout. Include exactly one; it does not replace the project's file.

For XDC, FPGALab reads literal `set_property PACKAGE_PIN <pin>
[get_ports {<port>}]` assignments, including bus bits and the `-dict` form.
Other Tcl commands are not evaluated. Unsupported `PACKAGE_PIN` expressions
produce an error rather than an empty map.

### Discovery and identifiers

`BoardCatalog` discovers board directories and validates the required files,
definition, layout, profile and pin constraints. Invalid packages are skipped
with a diagnostic.

| Identifier | Where it is used |
| --- | --- |
| Directory name, such as `alhambra_ii` | Internal package `board_id` used to locate resources. |
| `id` in `board.json`, such as `alhambra-ii` | Public board identifier. |
| `metadata.board_id` in a Lab | Stores the public identifier of the selected board. |

Opening a Lab resolves its public identifier to the package directory. Changing
the board selector updates the Lab metadata; Labs without `metadata.board_id`
use Alhambra II by default.

### Clock and sampling settings

- A board's `clock_hz` supplies its default virtual clock.
- A positive `metadata.virtual_clock_hz` overrides it for one Lab. Changing the
  board clears that override; `--clock-hz` overrides only the current session.
- Interface refresh and temporal sampling are user-wide settings.

### Integrated controls

Optional roles in `layout.json` distinguish simulation controls from FPGA I/O:

| Element | Role | Behavior |
| --- | --- | --- |
| Board LED | `power` | Simulation power indicator, without requiring an FPGA pin. |
| Board button | `reset` | Resets the simulation, without requiring an FPGA pin. |

Assign roles in **Edit layout**. Each role belongs to at most one element;
assigning it to another transfers it. Suggested internal identifiers are `PWR`
and `RESET`, but the role, not the name, determines the behavior.

For ordinary LEDs, `controls.leds` in `board.json` determines the order of
samples published by the worker. Endpoint names select the corresponding
visual LEDs in `layout.json`; any number of LEDs is allowed, including none.

### Layout editor

- **Board signal** selects logical endpoints from `board.json`, not FPGA pin
  numbers or project HDL nets. LEDs list output/inout endpoints; buttons list
  input/inout endpoints, excluding the clock. Power/reset roles allow internal
  names. Unavailable existing signals are preserved; empty signals cannot be saved.
- **Component creation** uses one form, starting with the role, followed by
  identifier and signal. Invalid or duplicate identifiers stay available for
  correction rather than closing the form.
- **Sidebar sections** separate component properties/actions, creation,
  whole-board rotation/mirroring and view controls. Save and Close stay at the bottom.
- **Persistence** remembers window geometry and the canvas/properties divider
  per user.

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

## Distribution and toolchains

The [packaging guide](packaging.md) covers PyInstaller runtime collection,
controlled SDK builds, source companions, download testing and offline bundles.
It separates reproducible maintainer procedures from application development.
Artifact-specific evidence and publication checks stay in the repository's
[SDK compliance records](https://github.com/lmcapacho/FPGALab/tree/main/packaging/linux_toolchain/compliance).

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

See [Contribute a translation](translations.md) for catalog metadata, templates,
validation and English-reference maintenance. New language catalogs need no code changes.
