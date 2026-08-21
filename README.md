# FPGALab

FPGALab is an interactive virtual FPGA laboratory for Verilog designs. It turns an Icestudio export into a native Verilator model and connects that model to a PyQt6 desktop interface, so learners can interact with a virtual board and peripherals without requiring physical hardware.

The first supported board is **Alhambra II**. The architecture is board-profile driven, allowing additional boards and visual peripherals to be added over time.

## What it does

- Opens an Icestudio `.ice` design and finds its generated `main.v` and PCF file in `ice-build`.
- Builds the design with Verilator only when the HDL, PCF, profile, or build settings have changed.
- Runs the compiled model through a native C ABI and Python `ctypes`, without VCD-based interaction.
- Emulates a configurable virtual clock (12 MHz by default) while refreshing the GUI at a human-friendly rate.
- Maps Alhambra II LEDs, switches, reset, and GPIO endpoints through the design PCF.
- Provides a reusable laboratory workspace for external LEDs, push buttons, digital sensors, traffic lights, and seven-segment displays.
- Keeps physical board artwork and interactive element placement in SVG and JSON assets.
- Offers an English interface by default, with Spanish available from the `EN / ES` language selector.

## Architecture

```text
Icestudio design (.ice)
        │
        ├── ice-build/<design>/main.v
        └── ice-build/<design>/main.pcf
        │
        ▼
Project discovery + Verilog interface + PCF mapping
        │
        ▼
Verilator build cache ──► C++ simulation wrapper ──► shared library
                                                          │
                                                       ctypes
                                                          │
                                                          ▼
                                                VerilatorSimulation
                                                          │
                                                 QThread + QTimer
                                                          │
                                                          ▼
                                      Virtual board and peripheral workbench
```

The C++ wrapper exposes native getters, setters, clock stepping, and batched cycle execution. Python sends inputs to the model and receives sampled outputs; the GUI never has to refresh at the FPGA clock rate.

## Requirements

- Python 3.10 or newer
- [Verilator](https://www.veripool.org/verilator/) 5.x or newer
- A C++17 compiler and GNU Make-compatible build tools
  - Linux: GCC or Clang with `make`
  - Windows: MSYS2/MinGW64 is recommended
- PyQt6 (installed automatically with the Python package)

## Installation

```bash
git clone <your-repository-url>
cd FPGALab

python -m venv .venv
source .venv/bin/activate       # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e .

verilator --version
```

## Run FPGALab

Start the desktop application:

```bash
fpga-lab
```

Or open an Icestudio design directly:

```bash
fpga-lab --ice /path/to/design.ice
```

Use the top bar to select a design, select or create a laboratory, and start the simulation. The Run and Stop controls are located at the bottom-right of the application window.

### Icestudio workflow

1. Create or open a design in Icestudio.
2. Generate the Verilog output so that Icestudio produces `ice-build/<design>/main.v` and its PCF file.
3. Open the `.ice` file in FPGALab.
4. Press Run. FPGALab automatically determines whether the cached native model can be reused or needs rebuilding.
5. Interact with the board and peripherals while the model is running.

FPGALab does not write Verilator artifacts into `ice-build`. Compiled models are stored in the user cache.

## Virtual time and visual refresh

The virtual FPGA advances according to elapsed host time and `--clock-hz` (12 MHz by default). The native wrapper batches many FPGA cycles in C++ for each visual frame, avoiding a Python-to-C boundary crossing per cycle.

The interface is refreshed at `--ui-refresh-hz` (60 Hz by default). Fast signals are sampled independently at `--observation-hz` (1 MHz by default), allowing LEDs and other visual peripherals to represent duty cycle, transitions, and final state without depending on Qt timer phase.

If the host cannot sustain the requested virtual frequency, use a lower `--clock-hz` value for a slower instructional mode.

## Board mapping and GPIO

For Icestudio projects, the PCF is used to relate generated HDL net names to physical Alhambra II endpoints. This allows board LEDs and switches to work even when Icestudio-generated signal names differ from labels such as `LED0` or `SW1`.

External peripherals are configured from the virtual workbench. Their terminals are assigned to board GPIO endpoints, and FPGALab resolves those endpoints through the PCF when the HDL connects them. A peripheral may remain physically connected even if the current HDL does not use that pin.

## Laboratories

Laboratories are reusable configurations independent from Icestudio project folders. They store the external peripherals, their settings, pin assignments, and positions on the virtual workbench.

Default locations are:

- Linux: `~/FPGALab/labs`
- Windows: `Documents/FPGALab/labs`

Set `FPGALAB_WORKSPACE` to use a different workspace root.

## Board assets and extensibility

A board is described by reusable assets:

- `fpga_lab/assets/boards/alhambra_ii.svg` — scalable board artwork
- `fpga_lab/assets/board_layouts/alhambra_ii.json` — interactive controls, geometry, colours, and HDL signals
- `boards/alhambra_ii.json` — physical endpoints and board capabilities

This separation makes it possible to calibrate controls visually, add new integrated controls, or introduce another FPGA board without changing the simulation engine.

## Command-line options

```text
--ice PATH                 Icestudio design to open
--library PATH             Prebuilt simulation library (advanced mode)
--profile PATH             Manual board profile (advanced mode)
--cache-dir PATH           Override the Verilator build cache
--clock-hz INTEGER         Target virtual clock frequency
--ui-refresh-hz INTEGER    Maximum GUI refresh frequency
--observation-hz INTEGER   Signal sampling frequency
```

## Project status

FPGALab is under active development. The Alhambra II workflow and the initial external peripheral set are the current focus.

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).
