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

Los recursos de cada tarjeta se agrupan en `fpga_lab/assets/boards/<board-id>/`.
Cada carpeta contiene la definición, el pinout, el perfil, el layout y el SVG
de la tarjeta. `alhambra_ii/` es la estructura de referencia para futuras
tarjetas. FPGALab usa el PCF específico generado por Icestudio en `ice-build`;
el `pinout.pcf` empaquetado sirve como referencia del pinout de la tarjeta.
`BoardCatalog` descubre estas carpetas y valida sus archivos, definición,
layout, perfil y PCF. Omite los paquetes inválidos y conserva un diagnóstico.
Su `board_id` es el nombre de la carpeta (por ejemplo, `alhambra_ii`); el campo
`id` de `board.json` sigue siendo el identificador público de la tarjeta.
En `layout.json`, un LED de la tarjeta puede declarar `"role": "power"` y un
botón puede declarar `"role": "reset"`. Estos roles opcionales controlan el
indicador de ejecución y el reinicio sin depender del nombre de la señal.
Selecciona el elemento en Editar layout para asignar su función; cada función
puede pertenecer a un solo elemento.

## Periféricos externos

La [API de periféricos externos v1](peripheral-api.md) documenta los campos del manifiesto, renderizadores reutilizables, metadatos del paquete, ejemplos, validación e instalación. Consúltala para crear un paquete compartible. FPGALab no carga código Python de las carpetas de periféricos del usuario.

## Agregar un periférico integrado

Crea `fpga_lab/peripherals/<id>/manifest.json` y los recursos SVG con licencia compatible. Define terminales, conexiones obligatorias, propiedades, renderizador, tamaño y modo de simulación. Reutiliza un renderizador genérico cuando sea posible.

Consulta la [referencia del API](peripheral-api.md#visual-renderizadores-reutilizables) para ver los renderizadores disponibles y sus campos.

Ejecuta las pruebas antes de abrir un pull request:

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest -q
```

El código, identificadores y comentarios de desarrollo deben estar en inglés. Los textos visibles deben pasar por la capa de traducción.
