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

## Portable graphical runtime

Build the Linux application on Ubuntu 24.04 with PyInstaller and the existing
`packaging/pyinstaller/FPGALab.spec`. Install the XCB build libraries listed by
`packaging/pyinstaller/linux_runtime.py` (also installed by the release workflow).
The spec explicitly collects these libraries and fails if any is unavailable,
instead of producing an executable that requires users to install them later.
PyInstaller resolves their transitive dependencies. Keep the entire portable
directory, including `_internal`, together when distributing it.

Native Wayland remains enabled. Startup maps the window normally and waits for
its first exposure before requesting maximization; X11 and other platforms
maximize directly. No global `QT_QPA_PLATFORM` override is applied. Automated
tests verify this ordering; default startup also passed on a clean Ubuntu 24.04
desktop without forcing X11. Other compositor configurations require separate
validation; a headless test alone does not establish compositor compatibility.

## Experimental self-contained Linux toolchain

`packaging/linux_toolchain/build.py` is a **maintainer prototype**, not the
first-run downloader or a new installation requirement. It snapshots installed
Debian/Ubuntu packages into a private SDK: Verilator, GNU Make, GCC/G++, binutils,
Perl, Python and build utilities, including headers, libraries and copyrights.
It installs no host packages and leaves existing FPGALab discovery unchanged.
The package list and exact versions, build OS and glibc are recorded in
`toolchain.json`. Only Linux x86-64 is supported at this stage; the first local
baseline is Ubuntu 24.04/glibc 2.39. This is not a universal Linux binary.

### Private SDK discovery

`private_toolchain.py` owns SDK locations and format-1 compatibility checks;
`toolchain.py` integrates them into the existing compiler resolver. Frozen
applications search `toolchains/<sdk-id>/` beside `sys.executable`, not the
working directory or PyInstaller's temporary `_MEIPASS`. Per-user Linux SDKs
live in `$XDG_DATA_HOME/FPGALab/toolchains/` (default `~/.local/share/`).
The compiler cache remains independent; discovery does not install or modify SDKs.

SDK metadata must identify a controlled build, matching directory/recipe ID,
Linux x86-64 platform, Verilator 5+ and the required package versions. The resolver
also checks host glibc compatibility, executable resources and the sysroot.
Candidates rejected during automatic discovery are reported by toolchain
diagnostics; explicit SDK selection errors are not silently ignored. This is
compatibility validation, not authentication of native executable packages.
The selected SDK supplies a private build environment without modifying the
GUI's loader environment or falling back to host build tools. See the
[resolution order and installation layout](troubleshooting.md#resolution-order).

### Controlled Ubuntu build

The preferred experimental build uses `container_build.py`. Docker is required
**only on the maintainer/CI machine**, with access to its service; end users do
not need Docker. No host packages or Docker permissions are changed by the script.

```bash
python3 packaging/linux_toolchain/container_build.py --output /tmp/fpgalab-controlled-sdk
```

`packaging/linux_toolchain/recipe.json` pins the official Ubuntu 24.04 amd64
image by digest and an [Ubuntu package snapshot](https://snapshot.ubuntu.com/)
timestamp. The image is upgraded and tools installed from that signed, frozen
repository, not from the developer's installed packages or the current mirror.
Changing the base or tool versions requires reviewing and updating the recipe;
exact resolved binary/source package versions are recorded in the output.
This controls build inputs, but does not claim bit-identical archives.
HTTPS trust is bootstrapped with `ca-certificates=20240203` from Noble's original
signed release pocket over HTTP, before enabling the HTTPS snapshot. TLS and
APT signature checks remain enabled; any repository download failure aborts the
build. Only the application and SDK scripts are sent as the Docker build context,
not the checkout's virtual environment, Git history or local configuration files.

The script relocates the SDK, prepares FPGALab's synthetic native ABI probe, and
runs it in the pinned clean Ubuntu image without network, host headers or build
tools. Containers run read-only except for the new output directory and temporary
storage. An archive/checksum is generated only after the probe passes. Output
includes `toolchain.json`, `source-packages.json`, package copyright notices,
`REDISTRIBUTION.txt` and a separate `validation.json` receipt. Partial output is
retained on failure for diagnosis; retry with a new directory.

The manual **Experimental Linux SDK** GitHub Actions workflow runs this same
process and retains successful experimental artifacts for seven days. It does
not create a release or modify normal application packaging. The controlled
Ubuntu recipe has passed the relocated, offline native ABI probe. Re-run that
probe after recipe changes; unit tests alone do not qualify a new toolchain.

This probe qualifies the SDK/native model, not the complete PyQt application in
a clean desktop. GUI packaging, other distributions and corresponding-source
redistribution obligations remain separate gates before public distribution.

### Local snapshot and isolated probe

The earlier local snapshot builder remains useful for diagnosis, but is not the
controlled distribution route:

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
compatibility need separate qualification. First-run download, signing and
installers are later steps, not provided by these scripts.

## Experimental offline Linux bundle

`assemble.py` combines a **clean, current PyInstaller onedir build** and an
existing controlled SDK archive; the SDK is not rebuilt for each application
change. Run with Python 3.12+ in the application's build environment:

```bash
.venv/bin/python packaging/linux_toolchain/assemble.py \
  --app dist/FPGALab --sdk-archive /path/to/fpgalab-linux-sdk.tar.gz \
  --sdk-sha256 <expected-sha256-from-trusted-sdk-build> \
  --output /tmp/fpgalab-offline --app-version development
```

The new output directory contains a runnable `FPGALab/`,
`FPGALab-linux-x86_64-offline.tar.gz` and its `.sha256` sidecar. The assembler
checks the SDK digest before safe extraction, validates SDK metadata and
relocatable links, rejects existing outputs/toolchains, and preserves executable
modes and license/source inventories. `bundle.json` records the declared app
version/revision and SDK ID/digest. No SDK installation or user-data changes occur.
The portable layout is:

```text
FPGALab/
├── FPGALab
├── _internal/
├── bundle.json
├── OFFLINE-README.txt
└── toolchains/<sdk-id>/
    ├── bin/
    ├── rootfs/
    ├── toolchain.json
    ├── source-packages.json
    └── REDISTRIBUTION.txt
```

Extract the complete archive to a new location and verify the built executable,
not a source run:

```bash
.venv/bin/python packaging/linux_toolchain/smoke_offline.py \
  --bundle /path/to/extracted/FPGALab --work-dir /tmp/fpgalab-offline-probe
```

This maintainer probe launches the packaged app from another directory with an
empty host PATH, no SDK overrides and fresh application data/cache. It builds a
synthetic Icestudio-style design, then checks combinational logic, clock stepping
and Reset through the generated native ABI in the probe process. It retains an
application log and writes a success receipt only after all checks. Headless Qt
does not validate desktop rendering; empty PATH is not filesystem/network
isolation. Finally test the extracted package on a clean Ubuntu 24.04 desktop:
open the executable directly, verify its toolchain points inside `toolchains/`,
then load a Lab/design, simulate, Stop/Run, close and reopen without variables.
The VM does not need Docker, Python or build tools, but designs must include
their generated `ice-build` files.

The complete bundle was validated on a clean Ubuntu 24.04 VM: direct startup,
automatic bundled-tool discovery, Lab/design loading, compilation, simulation
and reopening worked without manual toolchain paths. This does not establish
compatibility with other distributions or prove network isolation.

The manual **Experimental Linux offline package** workflow builds the app and
downloads `experimental-linux-sdk` from a specified successful SDK workflow run
on this repository's `main` branch. Supply that run ID and the trusted SDK archive
SHA-256; it verifies origin/integrity, assembles, extracts/relocates and probes the
bundle before uploading a seven-day test artifact. Expired SDK artifacts require
a new SDK run; longer-lived versioned SDK distribution is not implemented yet.
Normal release workflows remain unchanged. SDK source/license obligations must
be completed before public distribution; these experimental artifacts are not
an approved SDK release. Initial support is Ubuntu 24.04 x86-64 desktop, not
universal Linux compatibility or an installer.

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
