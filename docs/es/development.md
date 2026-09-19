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

Copia allí el directorio completo del periférico y reinicia FPGALab. Por ejemplo, copia `examples/peripherals/led_bar` de modo que la ruta final termine en `peripherals/led_bar/manifest.json`. La barra de 8 LED aparecerá en el catálogo sin modificar ni recompilar FPGALab.

Por ahora los periféricos externos son declarativos: pueden usar las propiedades, clases de simulación y renderizadores genéricos admitidos por el manifiesto, pero FPGALab no ejecuta código Python desde esas carpetas. Usa `FPGALAB_PERIPHERALS_DIR` para seleccionar otra carpeta de catálogo durante el desarrollo o las pruebas.

## Agregar un periférico integrado

Crea `fpga_lab/peripherals/<id>/manifest.json` y los recursos SVG con licencia compatible. Define terminales, conexiones obligatorias, propiedades, renderizador, tamaño y modo de simulación. Reutiliza un renderizador genérico cuando sea posible.

El renderizador genérico `led_array` acepta `visual.terminals`, `visual.orientation` y `visual.color_property`. Consulta `examples/peripherals/led_bar` para ver un manifiesto completo de la API versión 1.

Ejecuta las pruebas antes de abrir un pull request:

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest -q
```

El código, identificadores y comentarios de desarrollo deben estar en inglés. Los textos visibles deben pasar por la capa de traducción.
