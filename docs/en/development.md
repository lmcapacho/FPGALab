# Architecture and contribution

## Simulation path

```text
Icestudio .ice project
  -> generated main.v and PCF
  -> Verilog interface and board profile
  -> cached Verilator native model
  -> ctypes simulation binding
  -> SimulationWorker
  -> board view and peripheral workbench
```

The native wrapper batches virtual FPGA cycles and publishes `SimulationFrame` objects. GPIO inputs, sampled outputs, temporal observations, and streaming sinks such as VGA remain separate data paths.

## Main modules

- `app.py`: application orchestration and build lifecycle.
- `compiler.py` and `build_cache.py`: Verilator generation and incremental native builds.
- `simulation.py` and `simulation_worker.py`: native binding and background execution.
- `virtual_lab.py`: board/workbench composition.
- `peripherals/catalog.py` and `peripherals/manifest.py`: declarative catalog.
- `workbench/view.py` and `workbench/item.py`: canvas interaction and rendered instances.
- `wiring.py`: Lab terminal-to-board-to-HDL resolution.

## Install an external peripheral

FPGALab discovers no-code peripheral folders at startup from:

- Linux: `~/.local/share/FPGALab/peripherals/`
- Windows: `%APPDATA%\FPGALab\peripherals\`
- macOS: `~/Library/Application Support/FPGALab/peripherals/`

Copy a complete peripheral directory into that location and restart FPGALab. For example, copy `examples/peripherals/simple_relay` so the resulting path ends in `peripherals/simple_relay/manifest.json`. The relay then appears in the catalog and switches between its packaged `off.svg` and `on.svg` without modifying or rebuilding FPGALab.

Before installing a package, run `python -m fpga_lab.peripherals.validate path/to/peripheral`. The command checks the manifest, renderer, referenced SVGs, directory name, and minimum FPGALab version; it exits with status 0 when ready. You may pass multiple folders. Validation neither installs nor executes package code.

You can also open the workbench catalog and choose “Install peripheral…” to import a folder or ZIP. The ZIP must contain a single root folder with `manifest.json` and its resources, such as `simple_relay/manifest.json`. FPGALab validates before copying to the user catalog. Packages requiring a newer FPGALab version are rejected.

If the ID is already installed, identical files leave it unchanged. An update needs a higher `package.version`; FPGALab asks for confirmation and restores the previous package if replacement fails. A changed package with the same or a lower version is rejected. Labs and their connections are not modified.

The install button sits beside search. Each user-installed peripheral has its own uninstall icon in the catalog; bundled peripherals do not. Uninstallation preserves Labs that use it; those elements appear unavailable until the package is reinstalled.

External peripherals are currently declarative: they may use supported manifest properties, simulation classes, and generic renderers, but FPGALab does not execute Python code from these folders. Set `FPGALAB_PERIPHERALS_DIR` to use a different catalog folder while developing or testing a peripheral.

Shareable manifests may include an optional `package` object with a semantic `version`, author name and optional URL, SPDX-style license identifier, optional repository URL, and `compatibility.minimum_fpgalab`. Legacy and bundled manifests remain valid without this object. The external examples include complete package metadata as the reference for future distribution tooling.

`package.author` identifies the original package creator. For later contributions or ongoing maintenance, optional `package.contributors` and `package.maintainers` accept lists of `{"name": "Name", "url": "https://…"}` objects; `url` is optional. List only people who have actually contributed. Existing packages need no changes.

### Declarative peripheral API v1

A package is one directory containing `manifest.json` and local SVG resources. The manifest fixes terminal names and directions, editable properties, a simulation class, and a stock renderer. No user Python is loaded. `gpio_sampled` observes the last output level at each interface update; `gpio_temporal` with `temporal.mode: per_terminal` observes the fraction of virtual cycles high and edge count between updates. A temporal renderer receives each terminal's `duty_cycle` (0–1) and `edge_rate_hz` separately from the LED-specific, visually smoothed `brightness`. The interval is virtual simulation time, not wall-clock time. These observations are not a decoded serial bus or an exact pulse-by-pulse waveform.

The external [`pwm_meter`](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pwm_meter) demonstrates this contract: one FPGA output, a temporal probe, and `measured_svg` display the high-time percentage. `body.svg` defines the housing and `fill.svg` the bar that grows with duty cycle. Install its folder or ZIP from the catalog. The earlier `signal_meter` renderer remains available for existing packages. Protocol decoding (UART/I²C/SPI) and user-defined Python renderers are not part of v1.

The `measured_svg` renderer keeps artwork in the package: `base_svg` stays fixed while `moving_svg` rotates (`rotate`) or scales horizontally (`scale_x`) according to `duty_cycle` or `pulse_high_seconds`. The manifest declares the terminal, input/output ranges, and transform origin. An optional `value_label` shows a percentage for 0–1 duty output. The `pulse_servo` example supplies `body.svg` and `arm.svg`; its artwork no longer needs servo-specific Python drawing. The earlier `pulse_servo` renderer remains available for existing packages.

For position-style controls, each temporal terminal also exposes `pulse_high_seconds`: the latest **completed** high pulse measured in virtual time. It remains unavailable until a falling edge completes a pulse, and the measurement continues across interface updates. Its resolution is the configured temporal sampling interval; signals faster than that can alias. The external [`pulse_servo`](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pulse_servo) maps 1,000–2,000 µs to −90°…90° through `measured_svg`. It visualizes the commanded angle, not mechanical dynamics or position feedback. This package requires a FPGALab version supporting `measured_svg`.

## Add a bundled peripheral

Create `fpga_lab/peripherals/<id>/manifest.json` and its licensed SVG resources. Define terminal direction, required connections, properties, visual renderer, size, and simulation mode. Reuse a generic renderer when possible; add a renderer class only when the behavior cannot be described by existing primitives.

The generic `led_array` renderer accepts `visual.terminals`, `visual.orientation`, and `visual.color_property`. See `examples/peripherals/led_bar` for a complete API version 1 manifest.

The generic `state_svg` renderer selects packaged SVG resources through ordered `visual.state_rules`. Each rule currently compares one declared terminal with `0` or `1`; `visual.default_state` is used when no rule matches. See `examples/peripherals/simple_relay` for the smallest no-code example. Resource paths must be relative, remain inside the peripheral directory, and end in `.svg`.

For digital inputs, `state_svg` also supports bounded `click` interactions with the `toggle` action. The interaction must target a declared input terminal. Its latched value is restored whenever simulation starts. See `examples/peripherals/simple_switch` for a complete interactive example requiring no Python code.

Momentary inputs use the `press_release` event with the `momentary` action. They stay active while held, release even when the pointer leaves the active region, and return to a safe low level when simulation stops. See `examples/peripherals/simple_button`.

Run the tests before opening a pull request:

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest -q
```

Keep source code, identifiers, and developer comments in English. User-visible text must pass through the translation layer.
