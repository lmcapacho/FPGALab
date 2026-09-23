# Arquitectura y contribución

## Ruta de simulación

```text
Proyecto .ice de Icestudio
  -> main.v y PCF generados
  -> interfaz Verilog y perfil de tarjeta
  -> modelo nativo de Verilator en caché
  -> enlace de simulación con ctypes
  -> SimulationWorker
  -> vista de tarjeta y mesa de periféricos
```

El wrapper nativo agrupa ciclos virtuales de FPGA y publica objetos `SimulationFrame`. Las entradas GPIO, salidas muestreadas, observaciones temporales y destinos de streaming como VGA permanecen como rutas de datos independientes.

## Módulos principales

- `app.py`: coordinación de la aplicación y ciclo de compilación.
- `compiler.py` y `build_cache.py`: generación con Verilator y compilación incremental.
- `simulation.py` y `simulation_worker.py`: enlace nativo y ejecución en segundo plano.
- `virtual_lab.py`: composición de tarjeta y mesa.
- `peripherals/catalog.py` y `peripherals/manifest.py`: catálogo declarativo.
- `workbench/view.py` y `workbench/item.py`: interacción con el lienzo e instancias visuales.
- `wiring.py`: resolución terminal del Lab → tarjeta → HDL.

## Instalar un periférico externo

FPGALab descubre al iniciar carpetas de periféricos sin código en:

- Linux: `~/.local/share/FPGALab/peripherals/`
- Windows: `%APPDATA%\FPGALab\peripherals\`
- macOS: `~/Library/Application Support/FPGALab/peripherals/`

Copia allí el directorio completo del periférico y reinicia FPGALab. Por ejemplo, copia `examples/peripherals/simple_relay` de modo que la ruta final termine en `peripherals/simple_relay/manifest.json`. El relé aparecerá en el catálogo y alternará entre sus archivos `off.svg` y `on.svg` sin modificar ni recompilar FPGALab.

Por ahora los periféricos externos son declarativos: pueden usar las propiedades, clases de simulación y renderizadores genéricos admitidos por el manifiesto, pero FPGALab no ejecuta código Python desde esas carpetas. Usa `FPGALAB_PERIPHERALS_DIR` para seleccionar otra carpeta de catálogo durante el desarrollo o las pruebas.

Los manifiestos compartibles pueden incluir un objeto opcional `package` con `version` semántica, nombre del autor y URL opcional, identificador de licencia con formato SPDX, URL opcional del repositorio y `compatibility.minimum_fpgalab`. Los manifiestos antiguos e integrados siguen siendo válidos sin este objeto. Los ejemplos externos incluyen metadatos completos como referencia para las futuras herramientas de distribución.

### API declarativa de periféricos v1

Un paquete es una carpeta con `manifest.json` y recursos SVG locales. El manifiesto define nombres y direcciones de terminales, propiedades editables, clase de simulación y renderizador integrado. No se carga código Python del usuario. `gpio_sampled` observa el último nivel de salida en cada actualización de interfaz; `gpio_temporal` con `temporal.mode: per_terminal` observa la fracción de ciclos virtuales en alto y la cantidad de transiciones entre actualizaciones. El renderizador temporal recibe `duty_cycle` (0–1) y `edge_rate_hz` por terminal, separados de `brightness`, que tiene persistencia visual propia de un LED. El intervalo usa tiempo virtual de simulación, no tiempo real. Estos datos no equivalen a un bus serie decodificado ni a la forma de onda exacta de cada pulso.

El ejemplo externo [`pwm_meter`](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pwm_meter) prueba ese contrato: una salida de FPGA, una sonda temporal y el renderizador genérico `signal_meter` muestran el porcentaje de tiempo en alto sin complemento Python. Copia la carpeta completa al catálogo de usuario y reinicia. Requiere FPGALab 0.1.0rc4 o posterior; las versiones anteriores no tienen este renderizador. La instalación desde la interfaz, la decodificación de protocolos (UART/I²C/SPI) y los renderizadores Python del usuario no forman parte de v1.

Para controles de posición, cada terminal temporal ofrece también `pulse_high_seconds`: el último pulso alto **completo** medido en tiempo virtual. No está disponible hasta que un flanco descendente completa el pulso, y la medición continúa entre actualizaciones de la interfaz. Su resolución depende de la frecuencia de muestreo temporal; las señales más rápidas pueden producir aliasing. El ejemplo externo [`pulse_servo`](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pulse_servo) asigna 1000–2000 µs a −90°…90° mediante el renderizador reutilizable `pulse_servo`. Visualiza el ángulo ordenado, no la dinámica mecánica ni realimentación de posición. Este paquete también requiere FPGALab 0.1.0rc4 o posterior.

## Agregar un periférico integrado

Crea `fpga_lab/peripherals/<id>/manifest.json` y los recursos SVG con licencia compatible. Define terminales, conexiones obligatorias, propiedades, renderizador, tamaño y modo de simulación. Reutiliza un renderizador genérico cuando sea posible.

El renderizador genérico `led_array` acepta `visual.terminals`, `visual.orientation` y `visual.color_property`. Consulta `examples/peripherals/led_bar` para ver un manifiesto completo de la API versión 1.

El renderizador genérico `state_svg` selecciona recursos SVG del paquete mediante reglas ordenadas en `visual.state_rules`. Por ahora cada regla compara una terminal declarada con `0` o `1`; se usa `visual.default_state` cuando ninguna coincide. Consulta `examples/peripherals/simple_relay` para ver el ejemplo sin código más pequeño. Las rutas deben ser relativas, permanecer dentro del directorio del periférico y terminar en `.svg`.

Para entradas digitales, `state_svg` también admite interacciones `click` delimitadas con la acción `toggle`. La interacción debe apuntar a una terminal de entrada declarada. Su valor retenido se restaura cada vez que inicia la simulación. Consulta `examples/peripherals/simple_switch` para ver un ejemplo interactivo completo sin código Python.

Las entradas momentáneas usan el evento `press_release` con la acción `momentary`. Permanecen activas mientras se mantienen presionadas, se liberan incluso si el puntero sale de la región activa y regresan a un nivel bajo seguro cuando se detiene la simulación. Consulta `examples/peripherals/simple_button`.

Ejecuta las pruebas antes de abrir un pull request:

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest -q
```

El código, identificadores y comentarios de desarrollo deben estar en inglés. Los textos visibles deben pasar por la capa de traducción.
