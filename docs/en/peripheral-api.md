# External peripheral API v1

An external peripheral is a folder containing `manifest.json` and, when needed, SVG files. FPGALab reads it at startup or when installed from the catalog. A package does not execute its own Python code. This reference covers the declarative API available in FPGALab 0.1.0rc4.

## Start from an example

The [simple relay](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/simple_relay) is the smallest digital output package. The [button](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/simple_button), [LED bar](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/led_bar), [PWM meter](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pwm_meter), and [servo](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pulse_servo) demonstrate the other reusable behaviors.

```text
simple_relay/
├── manifest.json
├── icon.svg
├── off.svg
└── on.svg
```

`id` must match the folder name and be unique among bundled and installed peripherals. For new shareable packages, a namespaced ID such as `your_name.relay` is a good choice; the API does not yet enforce this format. `label` is the user-facing name.

## `manifest.json` fields

| Field | Type | Purpose |
| --- | --- | --- |
| `api_version` | optional integer | Format version. Only `1` is supported; omission defaults to `1`. |
| `id` | required string | Stable identifier matching the folder name. |
| `label` | required string | Name displayed in the catalog. |
| `category` | optional string | Catalog category, defaulting to `output`; new categories are allowed. |
| `description` | optional string | Description shown in search and the catalog. |
| `keywords` | optional string list | Additional search terms. |
| `icon` | optional relative path | Catalog SVG such as `icon.svg`; this is not the workbench artwork. |
| `simulation` | required object | Signal class and optional temporal observation. |
| `terminals` | optional list | Logical pins connected to the board. |
| `properties` | optional object | Editable fields on each instance. |
| `visual` | required object | Renderer, size, and artwork configuration. |
| `package` | optional object | Version, attribution, license, and compatibility for sharing and updating. |

### `package`: distribution and updates

When `package` is present, it requires `version` (a semantic version such as `1.0.0`), `author.name`, `license` (an SPDX-style identifier), and `compatibility.minimum_fpgalab` (for example `0.1.0rc4`). `author.url` and `repository` are optional HTTP(S) URLs.

`contributors` and `maintainers` are optional lists of objects with a required `name` and optional HTTP(S) `url`. `author` identifies the original creator; list other people only after they have contributed. To update an installed package, keep its `id`, increment `package.version`, and install it again. FPGALab validates the replacement and asks for confirmation; it rejects changed files with the same or an older version.

### `terminals`: connections

Each terminal has `name` and `direction`. `input` means **into the FPGA** (for example, a button); `output` means **from the FPGA** (for example, an LED). `width` is a positive integer defaulting to `1`; `required` is a boolean defaulting to `true`. Optional `supplies` may contain only `GND` or `VCC`. Names must be unique.

### `simulation`: available signals

| `class` | Purpose |
| --- | --- |
| `gpio_driven` | An interaction drives an FPGA input. |
| `gpio_sampled` | The latest output level is read at each interface update. |
| `gpio_temporal` | Outputs are observed over simulated cycles. External examples use `"temporal": {"mode": "per_terminal"}`. |
| `streaming_sink` | Specialized path used by VGA; it is not yet a general declarative API for UART, I²C, or SPI. |

A temporal terminal can expose `duty_cycle` (fraction from 0 to 1), `edge_rate_hz`, and `pulse_high_seconds` (seconds of the last **completed** high pulse). Measurements use virtual time and the configured sampling rate; faster signals may alias. `pulse_high_seconds` becomes available only after a falling edge. The `display_common` mode exists for bundled displays but is not the recommended starting point for external packages.

### `properties`: editable fields

Each property declares `type` and may add `label` and `default`. Supported types are `color`, `color_map`, `enum`, `boolean`, `string`, and `key_sequence`. A `color_map` uses `keys` and a color `default` for each key; an `enum` uses `values` and may declare `presets`. Declare only properties used by the selected renderer. The name `position` is reserved by the workbench.

## `visual`: reusable renderers

All renderers require `renderer` and `size: [width, height]` with positive integers. `chrome: "compact"` removes the card frame and places the instance name below the artwork. SVG and interaction coordinates refer to the artwork area; normally the last 24 pixels of height are reserved for the name.

| Renderer | Driving data | Main fields |
| --- | --- | --- |
| `state_svg` | Digital levels and interactive inputs | `states`, `default_state`, `state_rules`, `interactions` |
| `led_array` | Brightness of several outputs | `terminals`, `orientation`, `indicator_shape`, `show_labels`, `color_property` |
| `measured_svg` | Duty cycle or pulse width | `terminal`, `measurement`, ranges, transform, and two SVGs |

`state_svg` maps state names to SVG files in `states`, for example `{"off": "off.svg", "on": "on.svg"}`. `default_state` selects the initial state. Each `state_rules` entry has `state` and `when: {"terminal": "signal", "equals": 1}`; rules run in order. For controls, each `interaction` declares `terminal`, `region: [x, y, width, height]`, and one `event`/`action` pair: `click`/`toggle` or `press_release`/`momentary`. The region must fit within the artwork.

`led_array` lists unique output terminals in `visual.terminals`. `orientation` can be `horizontal` or `vertical`; `indicator_shape`, `circle` or `rectangle`; `show_labels` is boolean. `color_property` must refer to a `color` property (default name `color`).

`measured_svg` composes a fixed `base_svg` and a movable `moving_svg`. Both SVGs use the artwork size and coordinate system. `terminal` names a one-bit output; `measurement` is `duty_cycle` or `pulse_high_seconds`; `input_range` and `output_range` are numeric pairs mapping the measurement to the visual position. `transform` supports `rotate` (degrees) or `scale_x` (horizontal scale); `origin: [x, y]` sets the transform point. Measurements are clamped to the input range. For duty cycle with output `[0, 1]`, `value_label: {"format": "percent", "rect": [x, y, width, height]}` displays a percentage. The [servo](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pulse_servo) rotates; the [PWM meter](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pwm_meter) scales horizontally.

The earlier `signal_meter` and `pulse_servo` renderers remain available for existing packages. Their artwork is defined in FPGALab; use `measured_svg` for new designs with packaged graphics.

## Validate, install, and share

From the repository root, validate one or more folders:

```bash
python -m fpga_lab.peripherals.validate examples/peripherals/simple_relay
```

The command checks the manifest, renderer, SVG resources, folder name, and minimum FPGALab version without installing anything. In the application, open the catalog and use the install icon beside search. Choose a folder or a ZIP containing **one root folder** with `manifest.json` and its resources; SVG files must stay inside the package. The catalog can uninstall user packages without deleting their Lab instances. See [Architecture and contribution](development.md) to integrate new renderers into the core.

You can also copy the complete folder and restart FPGALab. The user catalog lives at `~/.local/share/FPGALab/peripherals/` (Linux), `%APPDATA%\FPGALab\peripherals\` (Windows), or `~/Library/Application Support/FPGALab/peripherals/` (macOS). For development and testing, `FPGALAB_PERIPHERALS_DIR` temporarily selects a different catalog folder. Labs keep their instances and connections when a package is uninstalled; a missing type appears unavailable until reinstalled.
