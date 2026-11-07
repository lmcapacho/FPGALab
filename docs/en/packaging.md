# Packaging and controlled SDKs

This guide is for maintainers building application artifacts and testing the
experimental Ubuntu 24.04 x86-64 SDK. It is not an installation prerequisite
for end users; see [Toolchain and troubleshooting](troubleshooting.md) for using
the application. Architecture and core API contracts are in
[Architecture and contribution](development.md).

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
that may raise to cancel; GUI adapters must run it off the GUI thread.
Python must include `tarfile.data_filter` (Python 3.12+ or a patched older version).
Public redistribution licensing remains a separate prerequisite.

The desktop uses the installer on a background thread and retains the worker
until cancellation finishes. A pending operation can take up to its socket
timeout to stop. It re-resolves toolchain priorities after installation rather
than assuming the downloaded SDK is selected. User-facing steps are in
[Toolchain and troubleshooting](troubleshooting.md#optional-sdk-download-development-builds).

### VM networking for SDK tests

With Quickemu's default QEMU user networking, the VM normally reaches the host
at `10.0.2.2`. Keep the test server running on the host and enter
`http://10.0.2.2:8765/catalog.json` in the VM with the HTTP test option enabled.
The loopback URL `127.0.0.1` refers to the VM itself unless a tunnel is in use.
The supplied server speaks plain HTTP, not HTTPS; changing the URL scheme to
HTTPS causes a TLS protocol error, not a certificate problem. Rebuild the
application package after source changes before copying it to the VM.
### Local snapshot and isolated probe

The local snapshot builder is a diagnostic tool, not the
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
