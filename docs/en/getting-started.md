# Getting started

To run your first design, you need **FPGALab**, an **Icestudio design with
generated Verilog**, and a **simulation toolchain**. No physical FPGA board
is required. Follow the three steps below in order.

## 1. Install FPGALab

Download the package for Linux, Windows, or macOS from [GitHub Releases](https://github.com/lmcapacho/FPGALab/releases). Extract portable archives completely before opening the application.

- **Linux:** extract `linux-x86_64.tar.gz` and run the `FPGALab` executable inside the extracted directory.
- **Windows:** use the self-contained `windows-x64.exe`, or fully extract `windows-x64-portable.zip` before running `FPGALab.exe`.
- **macOS Intel:** extract `macos-x86_64.zip`.
- **macOS Apple Silicon:** extract `macos-arm64.zip`.

The macOS application is ad-hoc signed but not Apple-notarized. On first launch, macOS may require **Control-click → Open** on `FPGALab.app`.

Published application packages include Python and PyQt, **not the complete simulation
toolchain**. This also applies to the standalone Windows `.exe`: continue with
step 2 before attempting to run a design.

The experimental `linux-x86_64-offline.tar.gz` test package is different: it
includes the private Linux SDK. Extract its entire `FPGALab` folder to a path
without spaces and run `FPGALab` directly; no tool installation or environment
variables are needed. In step 2, check the tools rather than installing them.

## 2. Prepare and check the simulation tools

FPGALab compiles each design using **Verilator 5+, GNU Make and a C++17
compiler**. Install these separately if they are not already available;
the current releases do not download or configure them automatically.

| System | What to prepare | Installation instructions |
| --- | --- | --- |
| Linux | Verilator, Make and G++; Verilator may also come from Icestudio/Apio. | [Linux toolchain](troubleshooting.md#linux) |
| Windows | Verilator from Icestudio/Apio or OSS CAD Suite, plus MSYS2 with Make, Python and a MinGW-w64 C++ compiler. | [Windows toolchain](troubleshooting.md#windows) |
| macOS | Verilator and Xcode Command Line Tools for Make and the C++ compiler. | [macOS toolchain](troubleshooting.md#macos) |

Having Icestudio installed does not necessarily provide every build tool.
After installation, open FPGALab and use the **terminal-with-check icon in the
status bar** to check the toolchain. Confirm that Verilator, Make and the
compiler have resolved paths before continuing. If a tool is missing, follow
the corresponding guide above; non-standard locations are explained under
[Resolution order](troubleshooting.md#resolution-order).

## 3. Run your first design

1. Open the design in Icestudio.
2. Generate its Verilog output. The project must contain `ice-build/<design>/main.v` and a PCF or XDC pin-constraint file.
3. Open the `.ice` file from the **Browse** button in FPGALab.
4. Select or create a **Lab**, which stores the virtual board and peripheral arrangement. Check that the board in the top-bar selector matches your Icestudio design.
5. Press **Run**. The first run may compile the native model; later runs reuse the incremental cache when possible.
6. Interact with board controls and external peripherals.
7. Press **Stop** before changing the project, board, Lab, or simulation settings.

FPGALab stores generated native models in the user cache, not in the Icestudio project.

For adding peripherals, pin assignments and sharing Labs, continue with
[Labs and workbench](labs-and-workbench.md). Board integration details and
Bitsy limitations are in the [development guide](development.md#board-integration-icebreaker-bitsy).

## How pin mapping works

FPGALab reads the design's PCF or XDC file from `ice-build` to match generated
HDL net names to physical FPGA pins and board endpoints. This is why an
on-board LED or switch can work even if its HDL net is not named `LED0` or
`SW1`. Connect a workbench peripheral terminal to a board endpoint in its
configuration; FPGALab then finds the corresponding HDL net through the same
constraints. A peripheral can remain connected in the Lab when the current
design does not use that pin, but it will not exchange a signal with the HDL.

Use **Connections** to inspect those assignments. XDC support covers literal
`PACKAGE_PIN` assignments, not arbitrary Tcl expressions; see
[Architecture and contribution](development.md) for the supported forms.

## Open from the command line

Start the desktop application with `fpga-lab`, or open a design directly with
`fpga-lab --ice /path/to/design.ice`. Advanced launch options include
`--library` and `--profile` for a prebuilt model, `--cache-dir` for a custom
build cache, and `--clock-hz`, `--ui-refresh-hz`, and `--observation-hz` for
session-only simulation overrides. Run `fpga-lab --help` for the complete list.

## Optional: run from source

This alternative requires Python 3.10+ in addition to the toolchain from step 2:

```bash
git clone https://github.com/lmcapacho/FPGALab.git
cd FPGALab
python -m venv .venv
source .venv/bin/activate
pip install -e .
fpga-lab
```

The activation command applies to Linux and macOS. On Windows PowerShell,
use `.venv\Scripts\Activate.ps1` instead.
