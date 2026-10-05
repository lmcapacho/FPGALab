# Toolchain and troubleshooting

FPGALab needs Verilator 5 or newer, GNU Make-compatible build tools, and a C++17 compiler. Python 3.10 or newer and PyQt6 are also needed when running from source; packaged applications include their Python runtime. Use the terminal-with-check icon in the status bar to see the exact resolved paths.

## Resolution order

FPGALab searches for:

1. The OSS CAD Suite installed by Apio or Icestudio.
2. A suite configured through `FPGALAB_OSS_CAD_SUITE`.
3. Verilator on the system `PATH`.

Use `FPGALAB_VERILATOR` to select a specific executable and `MSYS2_ROOT` for a non-standard MSYS2 location.

FPGALab also recognizes the older `tools-oss-cad-suite` package name. Common
OSS CAD Suite locations include `~/.apio/packages/oss-cad-suite` on Linux and
macOS and `%USERPROFILE%\.icestudio\apio\packages\oss-cad-suite` on Windows.
Some Icestudio installations use `AppData` or another location; point
`FPGALAB_OSS_CAD_SUITE` to the directory containing the suite's `bin` and
`share` folders. An explicit `FPGALAB_VERILATOR` path takes precedence.

For a standalone suite on Linux or macOS, for example, set
`FPGALAB_OSS_CAD_SUITE=/path/to/oss-cad-suite` before running `fpga-lab`.
OSS CAD Suite provides Verilator, but it does not remove the need for Make and
a C++17 compiler. On Windows, FPGALab detects a standard `C:\msys64`
installation; set `MSYS2_ROOT` when MSYS2 lives elsewhere.

## Linux

Install Verilator, Make, and a C++ compiler through the distribution package manager, or use the OSS CAD Suite bundled by Apio. For Debian- or Ubuntu-based systems, a typical system installation is:

```bash
sudo apt install verilator make g++
```

## Windows

Icestudio may provide Verilator but not the complete native build environment. Install MSYS2 and run this command in its UCRT64 terminal:

```bash
pacman -S --needed make python mingw-w64-ucrt-x86_64-gcc
```

Do not run the executable directly from a ZIP file: extract the complete package so its `_internal` directory remains beside the executable.

The standalone `windows-x64.exe` is the simpler download. The
`windows-x64-portable.zip` alternative must be fully extracted. Until the
application is Authenticode-signed and builds reputation, Windows SmartScreen
may report an unknown publisher.

## macOS

Install Xcode Command Line Tools and Verilator. Homebrew is one supported option:

```bash
xcode-select --install
brew install verilator
```

FPGALab provides separate application bundles for Intel (`x86_64`) and Apple Silicon (`arm64`). Both still require these external compilation tools when running an Icestudio design.

The bundles are ad-hoc signed for integrity but not Apple-notarized. Use
**Control-click → Open** on `FPGALab.app` on first launch if macOS blocks it.

## A build appears stuck

Some valid Verilog designs expose optimizer limitations in particular Verilator versions. Open Simulation Settings and enable compatibility optimization, then run again. FPGALab also terminates active build and simulation processes when the application closes.
