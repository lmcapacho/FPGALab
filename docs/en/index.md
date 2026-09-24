# FPGALab

FPGALab is a desktop virtual FPGA laboratory for Icestudio and Verilog designs. It compiles the generated HDL with Verilator and connects the resulting native model to an interactive board and peripheral workbench.

## Start here

- Follow [Getting started](getting-started.md) to run your first design.
- Learn how to create, import, and share [Labs](labs-and-workbench.md).
- Use [Toolchain and troubleshooting](troubleshooting.md) when FPGALab cannot find Verilator or a compiler.
- Use the [external peripheral API](peripheral-api.md) to create and install your own components.
- Read [Architecture and contribution](development.md) to extend the project.

## Current scope

The first supported board is Alhambra II. The catalog includes LEDs, buttons, toggle and DIP switches, a vehicle-presence sensor, traffic lights, seven-segment and BCD displays, and VGA monitors.

FPGALab is released under the GNU Affero General Public License, version 3 or later.
