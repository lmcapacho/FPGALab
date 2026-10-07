# Getting started

## Install FPGALab

Download the package for Linux, Windows, or macOS from [GitHub Releases](https://github.com/lmcapacho/FPGALab/releases). Extract portable archives completely before opening the application.

- **Linux:** extract `linux-x86_64.tar.gz` and run the `FPGALab` executable inside the extracted directory.
- **Windows:** use the self-contained `windows-x64.exe`, or fully extract `windows-x64-portable.zip` before running `FPGALab.exe`.
- **macOS Intel:** extract `macos-x86_64.zip`.
- **macOS Apple Silicon:** extract `macos-arm64.zip`.

The macOS application is ad-hoc signed but not Apple-notarized. On first launch, macOS may require **Control-click → Open** on `FPGALab.app`.

To run from source:

```bash
git clone https://github.com/lmcapacho/FPGALab.git
cd FPGALab
python -m venv .venv
source .venv/bin/activate
pip install -e .
fpga-lab
```

The activation command above applies to Linux and macOS. On Windows PowerShell, use `.venv\Scripts\Activate.ps1`.

## Run a design

1. Open the design in Icestudio.
2. Generate its Verilog output. The project must contain `ice-build/<design>/main.v` and a PCF or XDC pin-constraint file.
3. Open the `.ice` file from the **Browse** button in FPGALab.
4. Select or create a Lab. Its saved board appears in the top-bar selector and determines which packaged board definition is used for pin mapping and simulation. Changing the selector updates the current Lab. Alhambra II is the validated board; iCEBreaker Bitsy v1.1c is available as an experimental second-board package in development builds.
5. Press **Run**. The first run may compile the native model; later runs reuse the incremental cache when possible.
6. Interact with board controls and external peripherals.
7. Press **Stop** before changing the project, board, Lab, or simulation settings.

FPGALab stores generated native models in the user cache, not in the Icestudio project.

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

FPGALab checks GitHub Releases after startup and from the update button in the
status bar. Stable builds check stable releases; release-candidate builds also
consider release candidates. Updates open the release page for download rather
than replacing the running application automatically.
