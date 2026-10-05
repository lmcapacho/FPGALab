# Arquitectura y contribución

## Arquitectura de simulación

```text
Diseño de Icestudio (.ice)
        │
        ├── ice-build/<diseño>/main.v ──► interfaz Verilog + perfil de tarjeta
        └── ice-build/<diseño>/main.pcf o main.xdc
                  │                         │
                  └── redes HDL ↔ pines FPGA ↔ endpoints de tarjeta
                                            │
                                            ▼
                           caché de compilación Verilator
                                            │
                           wrapper C++ + captura nativa
                                            │
                                            ▼
                    biblioteca del diseño (.so / .dll / .dylib)
                                            │
                                      enlace ctypes
                                            │
                                            ▼
                         SimulationWorker (hilo de Qt)
                                            │  actualizaciones SimulationFrame
                         ┌──────────────────┴──────────────────┐
                         ▼                                     ▼
                Vista y controles de tarjeta       Mesa de periféricos
                (SVG + layout JSON)                 (Lab + manifiestos)
                                                               │
                                            GPIO / temporal / VGA / flancos

Conexión del Lab: terminal → endpoint de tarjeta → pin FPGA → red HDL
```

El wrapper nativo agrupa ciclos virtuales de FPGA y publica objetos `SimulationFrame`. Las entradas GPIO, salidas muestreadas, observaciones temporales y destinos de streaming como VGA permanecen como rutas de datos independientes.

El wrapper C++ generado expone asignación de entradas, lectura de salidas,
avance de reloj, ejecución por lotes, mediciones temporales y captura de flujos
mediante una ABI nativa. Python enlaza la biblioteca propia de cada diseño
(`.so`, `.dll` o `.dylib`) con `ctypes`; `SimulationWorker` la ejecuta fuera
del hilo de interfaz y entrega cuadros compactos a la tarjeta y a la mesa.
Qt no se actualiza a la frecuencia de reloj de la FPGA. La compilación
incremental usa una caché administrada del usuario, fuera de `ice-build`.

Las entradas GPIO, salidas muestreadas, observaciones temporales para LED y
displays, captura VGA por ciclo y flancos/entradas temporizadas de la API
UART/SPI en desarrollo son rutas distintas dentro de ese flujo.

Las restricciones del proyecto relacionan los nombres HDL generados con los
endpoints físicos de la tarjeta; así funcionan LEDs y controles aunque la red
HDL no se llame como su etiqueta visual. Un periférico puede seguir conectado
físicamente en el Lab aunque el HDL actual no utilice ese pin.

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
tarjetas.

| Archivo | Propósito |
| --- | --- |
| `board.json` | Identidad, endpoints físicos, reloj y controles integrados. |
| `pinout.pcf` o `pinout.xdc` | Restricciones de pines de referencia; incluye solo uno. |
| `profile.json` | Perfil de puertos de entrada y salida del modelo nativo. |
| `layout.json` | Controles interactivos, posiciones y referencia al SVG. |
| `board.svg` | Imagen vectorial de la tarjeta. |

FPGALab usa el `main.pcf` o `main.xdc` específico del proyecto en
`ice-build`; cada paquete de tarjeta incluye exactamente un `pinout.pcf` o
`pinout.xdc` como referencia. En XDC se leen asignaciones literales
`set_property PACKAGE_PIN <pin> [get_ports {<puerto>}]`, incluidos bits de bus
y la forma `-dict`. No se evalúan otros comandos XDC. Una expresión
`PACKAGE_PIN` no admitida produce un error en vez de un mapa vacío.
`BoardCatalog` descubre estas carpetas y valida sus archivos, definición,
layout, perfil y restricciones de pines. Omite los paquetes inválidos y conserva un diagnóstico.
Su `board_id` es el nombre de la carpeta (por ejemplo, `alhambra_ii`); el campo
`id` de `board.json` sigue siendo el identificador público de la tarjeta.
Los Labs guardan el identificador público en `metadata.board_id`. Al abrir un
Lab, la interfaz lo resuelve al nombre de la carpeta del paquete; cambiar el
selector actualiza esos metadatos. Un Lab sin este campo usa Alhambra II.
El campo positivo opcional `metadata.virtual_clock_hz` reemplaza el `clock_hz`
de la tarjeta para ese Lab. Cambiar la tarjeta elimina ese ajuste. El refresco
de interfaz y el muestreo temporal son globales por usuario; `--clock-hz` solo
se aplica a la ejecución actual.
En `layout.json`, un LED de la tarjeta puede declarar `"role": "power"` y un
botón puede declarar `"role": "reset"`. Estos roles opcionales controlan el
indicador de ejecución y el reinicio sin depender del nombre de la señal.
Selecciona el elemento en Editar layout para asignar su función; cada función
puede pertenecer a un solo elemento.
El orden de `controls.leds` en `board.json` determina el orden de los valores
LED publicados por el worker. Cada nombre de endpoint selecciona el LED visual
correspondiente en `layout.json`; una tarjeta puede declarar cualquier número
de LEDs, incluso ninguno.

## Periféricos externos

La [API de periféricos externos v1](peripheral-api.md) documenta los campos del manifiesto, renderizadores reutilizables, metadatos del paquete, ejemplos, validación e instalación. Consúltala para crear un paquete compartible. FPGALab no carga código Python de las carpetas de periféricos del usuario.

Hay dos ubicaciones diferentes:

```text
# Integrado en FPGALab (repositorio principal; puede usar un renderizador interno)
fpga_lab/peripherals/<peripheral-id>/
├── manifest.json
└── icon.svg
fpga_lab/peripherals/renderers/<renderer>.py

# Paquete externo/instalable (declarativo; sin código Python)
examples/peripherals/<peripheral-id>/
├── manifest.json
├── icon.svg
└── archivos SVG referenciados por el manifiesto
```

Agrega un periférico integrado solo cuando su comportamiento deba formar parte
del catálogo principal. Para un componente compartible, empieza en
`examples/peripherals/`, valida la carpeta y luego instálala desde el catálogo
o empaquétala como ZIP. Los paquetes externos deben usar los renderizadores que
FPGALab ya proporciona.

## Agregar un periférico integrado

Crea `fpga_lab/peripherals/<id>/manifest.json` y los recursos SVG con licencia compatible. Define terminales, conexiones obligatorias, propiedades, renderizador, tamaño y modo de simulación. Reutiliza un renderizador genérico cuando sea posible; agrega una clase de renderizador en `fpga_lab/peripherals/renderers/` solo cuando el comportamiento no pueda describirse con los renderizadores existentes.

Consulta la [referencia del API](peripheral-api.md#visual-renderizadores-reutilizables) para ver los renderizadores disponibles y sus campos.

Ejecuta las pruebas antes de abrir un pull request:

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest -q
```

El código, identificadores y comentarios de desarrollo deben estar en inglés. Los textos visibles deben pasar por la capa de traducción.
