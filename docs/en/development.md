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
server API. Workbench persistence and automatic per-renderer temporal/serial
binding plans still belong to the desktop; a headless host can use the resolved
wires to configure the engine's existing capture/drive APIs explicitly. There
is no HTTP transport, multi-user isolation or public-server sandbox in this API.

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
tests verify this ordering. Validate compositor compatibility on a real desktop;
a headless test alone does not establish it.

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
build. The Docker context contains compiler/probe and SDK packaging sources, project license
files, `pyproject.toml` and hashed provenance, not the checkout's virtual
environment, Git history or local secrets. Unexpected source-tree symlinks are
rejected instead of following paths outside those inputs.

The script relocates the SDK, prepares FPGALab's synthetic native ABI probe, and
runs it in the pinned clean Ubuntu image without network, host headers or build
tools. Containers run read-only except for the new output directory and temporary
storage. The native probe and final archiving are offline; a separate source
collection phase has network access to download from the same frozen repository.
Binary archives/checksums are generated only after the probe and source verification pass. Output
includes `toolchain.json`, `source-packages.json`, package copyright notices,
`REDISTRIBUTION.txt`, FPGALab adaptation license/notices and a separate `validation.json` receipt. Partial output is
retained on failure for diagnosis; retry with a new directory.

The manual **Experimental Linux SDK** GitHub Actions workflow runs this same
process and retains separate binary/source experimental artifacts for seven days. It does
not create a release or modify normal application packaging. Run the relocated,
offline native ABI probe after recipe changes; unit tests alone do not qualify
a new toolchain.

This probe qualifies the SDK/native model, not the complete PyQt application in
a clean desktop. GUI packaging, other distributions and corresponding-source
redistribution obligations remain separate gates before public distribution.

### SDK sources and redistribution review

The SDK ID and frozen build inputs are defined in
`packaging/linux_toolchain/recipe.json`. Published IDs are immutable.
The build context limits local inputs to the compiler/probe import
closure, native `.cpp`/`.h` files, SDK packaging scripts and project notices.
Desktop artwork, board packages, peripheral packages and translations are not
build inputs. The source companion copies only provenance-listed files. This
does not change the licensing review of those resources in the desktop package.
The source collector uses the SDK's actual
`source-packages.json` inventory and deduplicates identical source/version pairs.
It enables signed `deb-src` indexes from the same snapshot, selects the exact
version (never the newest substitute), then uses `apt-get source --download-only`.
The `.dsc`, original archives and Debian/Ubuntu packaging/patch archives are
retained without unpacking or executing package build scripts. Every downloaded
file's size and SHA-256 must match the authenticated APT source record; the `.dsc`
must identify that same source/version and cover the remaining files.

The separate `sdk-sources/` directory includes:

- `packages/<source>/<version>/`: original source files and retained APT records
  (epochs use `_` instead of `:` in directory names only).
- `notices/` and `common-licenses/`: retained package notices and license texts.
- `fpgalab/`: exact compiler/probe/build/relocation inputs and project license,
  sufficient to rerun the controlled builder with Docker and network access.
- `source-manifest.json`: binary-to-source coverage, checksums, recipe and local
  input provenance. The Git revision and dirty state are recorded when available;
  file hashes describe the actual working tree even before a commit.

Successful output adds `fpgalab-linux-sdk-sources.tar.gz` and its `.sha256` beside
the normal SDK archive. The SDK metadata links that companion by SHA-256;
`source-bundle.json` links the binary/source archive digests. Source versions,
coverage, notices, license texts and local inputs are checked again offline before
archiving. Missing versions, network errors or checksum mismatches abort rather
than producing a successful binary package. Retry failed builds in a new output
directory; source downloads may require several GB of temporary disk space.

Actions uploads the companion separately as `experimental-linux-sdk-sources`;
the existing `experimental-linux-sdk` artifact remains usable by the offline
assembler. Students download only the binary SDK, not the source companion.

The manifest deliberately says **collected, not legally approved**. A complete
file collection is not an automatic determination of Corresponding Source or
component-specific compliance. Before publishing, review licenses, adaptations,
rebuild instructions and source completeness, and provide clear, durable access
to the matching sources alongside binaries. Seven-day Actions artifacts or a
generic upstream homepage are not a permanent source distribution mechanism.
Do not remove the experimental redistribution warning based on unit tests alone.

Maintainer-only artifact evidence and publication checks are kept in the
[SDK compliance record](https://github.com/lmcapacho/FPGALab/blob/main/packaging/linux_toolchain/compliance/sdk-licenses.en.md),
separate from this development procedure.

### Experimental SDK download

`python -m fpga_lab.sdk_install` provides an opt-in download/install path for
maintainer testing, not an automatic first-run downloader or public SDK service.
It accepts a trusted catalog URL and an explicit SDK ID. Installation is in
the per-user `FPGALab/toolchains/<sdk-id>/` data directory described above,
not the application folder or build cache. Existing SDK IDs are never updated
in place; publish changed contents under a new ID.

Catalog format 1 contains an `sdks` list. Each entry requires `id`, `platform`
(currently `linux-x86_64`), `url` (absolute or relative to the catalog), `size`
(exact compressed bytes), and lowercase `sha256`. The installer requires HTTPS,
including redirects. A checksum verifies the archive against the catalog; it
does not authenticate an untrusted catalog. Use a controlled catalog origin.
Signatures and automatic update selection are not implemented.

For a local exercise, serve an already validated, trusted SDK archive from
the repository root (replace the archive path with your build output):

```bash
python3 packaging/linux_toolchain/serve_sdk.py \
  --archive /path/to/fpgalab-linux-sdk.tar.gz \
  --sdk-id ubuntu24.04-x86_64-sdk3
```

This generates the catalog in memory and serves only it and the archive on
`127.0.0.1:8765`; it neither copies the archive nor publishes it externally.
Keep that terminal running. In another terminal, from the repository root:

```bash
python -m fpga_lab.sdk_install \
  --catalog http://127.0.0.1:8765/catalog.json \
  --sdk-id ubuntu24.04-x86_64-sdk3 --allow-local-http
python -m fpga_lab.app
```

Use the project's Python environment. `--allow-local-http` is a test-only
exception restricted to loopback and literal RFC 1918 private IPv4 addresses
(`10/8`, `172.16/12`, `192.168/16`). It does not allow public HTTP addresses,
arbitrary DNS names or link-local metadata endpoints. Only use it with a trusted
local/VM test server: HTTP is unencrypted, and a checksum from the same catalog
cannot protect against network tampering. No network
access is initiated by application startup. Stop the test server with Ctrl+C.
The application discovers the installed SDK on its next toolchain resolution;
explicit tool settings and a bundled SDK retain their normal precedence.

Downloads have size limits, a timeout and progress reporting. Size and SHA-256
must match before extraction. Extraction limits reject escaping paths/links
and special files; metadata, platform, host glibc, required tools and inventories
are validated before the version directory becomes visible. Cancellation and
ordinary failures remove staging files. A per-ID lock blocks concurrent installs;
after a forced process kill, inspect hidden staging/lock files before removing
them, and ensure no installer is running. The API supports a progress callback
that may raise to cancel; future GUI integration must run it off the GUI thread.
Python must include `tarfile.data_filter` (Python 3.12+ or a patched older version).
Public redistribution licensing remains a separate prerequisite.

The GUI exposes the same installer from **Check simulation toolchain → Download
SDK…** on Linux x86-64. Enter the trusted catalog URL and explicitly load it;
for the local server above, enable **Allow HTTP for trusted local/VM tests**. Choose an SDK,
review its compressed size/checksum and installation folder, then select
**Download and install**. Catalog loading, downloading and extraction run on a
background thread; the dialog shows progress and installation stages. Cancel,
Escape or closing the dialog requests cancellation and retains the thread until
it stops safely. A pending network operation may take up to its socket timeout
to respond. Errors stay in the dialog for correction/retry. Success reopens the
toolchain diagnostic with fresh resolution; existing explicit settings or a
bundled SDK may still take precedence. Changing the catalog URL/test option
invalidates its selection, and an entry changed on the server must be reloaded
before installation. No catalog URL is bundled or fetched automatically.

With Quickemu's default QEMU user networking, the VM normally reaches the host
at `10.0.2.2`. Keep the test server running on the host and enter
`http://10.0.2.2:8765/catalog.json` in the VM with the HTTP test option enabled.
The loopback URL `127.0.0.1` refers to the VM itself unless a tunnel is in use.
The supplied server speaks plain HTTP, not HTTPS; changing the URL scheme to
HTTPS causes a TLS protocol error, not a certificate problem. Rebuild the
application package after source changes before copying it to the VM.
The toolchain diagnostic is resizable, with selectable and scrollable text so
long errors and paths remain accessible.
When tools are ready, Close is the primary/default action; otherwise Download
SDK is primary where supported. Initial focus stays on that button, not the
read-only diagnostic text. Escape always closes without starting a download.

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
