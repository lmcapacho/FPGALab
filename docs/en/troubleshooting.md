# Toolchain and troubleshooting

FPGALab needs Verilator 5 or newer, GNU Make-compatible build tools, and a C++17 compiler. Python 3.10 or newer and PyQt6 are also needed when running from source; packaged applications include their Python runtime. Use the terminal-with-check icon in the status bar to see the exact resolved paths.

## Obtain Verilator

If Icestudio/Apio already provides Verilator, you can reuse it. Otherwise,
download [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases)
for your operating system and architecture and extract the archive completely.
Use `FPGALAB_OSS_CAD_SUITE` if it is outside the automatically detected locations
described below. A standalone suite provides Verilator, **not the complete
build environment**: also follow the Make/compiler instructions for your
system. Linux and macOS can alternatively install Verilator through the
package managers described in their sections.

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

### The application runs but no window appears

If this happens under Wayland, close the previous process and launch the
portable executable from a terminal. For diagnosis only, try
`QT_QPA_PLATFORM=xcb ./FPGALab`. If it opens, report the Ubuntu/GNOME and Qt
versions and terminal output; this isolates the graphical backend, not the
simulation toolchain. Development builds defer maximization until Wayland has
exposed the initial window. Default startup was validated on a clean Ubuntu
24.04 desktop without forcing X11; other compositor configurations need their own checks.

For an `xcb` plugin error, use `QT_DEBUG_PLUGINS=1 QT_QPA_PLATFORM=xcb ./FPGALab`
and retain the full output. The cursor-library message alone does not identify
every missing dependency. New builds require the XCB utility libraries during
packaging; extract the complete application directory rather than copying only
the executable. Older packages may lack those libraries.

### Simulation tools

Install Make and a C++ compiler through the distribution package manager.
For Verilator, use a version 5+ system package or the suite supplied by Apio.
Using Apio's Verilator does not replace Make and the compiler. On Debian or
Ubuntu, a typical installation of all three is:

```bash
sudo apt install verilator make g++
```

## Windows

First [obtain Verilator](#obtain-verilator) if Icestudio/Apio does not provide it.
Verilator alone is not the complete native build environment. Install MSYS2
and run this command in its UCRT64 terminal:

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
