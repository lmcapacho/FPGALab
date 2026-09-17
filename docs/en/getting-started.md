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
2. Generate its Verilog output. The project must contain `ice-build/<design>/main.v` and its PCF file.
3. Open the `.ice` file from the **Browse** button in FPGALab.
4. Select or create a Lab.
5. Press **Run**. The first run may compile the native model; later runs reuse the incremental cache when possible.
6. Interact with board controls and external peripherals.
7. Press **Stop** before changing the project, Lab, or simulation settings.

FPGALab stores generated native models in the user cache, not in the Icestudio project.
