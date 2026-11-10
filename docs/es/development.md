# Arquitectura y contribución

Para agregar idiomas de interfaz sin modificar código, consulta la guía de
[traducciones comunitarias](translations.md): metadatos, plantillas y validación.

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
                         SimulationEngine (sin Qt)
                                            │
                         SimulationWorker (adaptador Qt)
                                            │  actualizaciones SimulationFrame
                         ┌──────────────────┴──────────────────┐
                         ▼                                     ▼
                Vista y controles de tarjeta       Mesa de periféricos
                (SVG + layout JSON)                 (Lab + manifiestos)
                                                               │
                                            GPIO / temporal / VGA / flancos

Conexión del Lab: terminal → endpoint de tarjeta → pin FPGA → red HDL
```

El wrapper nativo agrupa ciclos virtuales; `SimulationEngine` recoge los resultados
en objetos `SimulationFrame`. GPIO, observaciones temporales y destinos de streaming
como VGA permanecen como rutas de datos independientes.

El wrapper C++ generado expone asignación de entradas, lectura de salidas,
avance de reloj, ejecución por lotes, mediciones temporales y captura de flujos
mediante una ABI nativa. Python enlaza la biblioteca propia de cada diseño
(`.so`, `.dll` o `.dylib`) con `ctypes`; `SimulationEngine` ejecuta y captura sin Qt.
`SimulationWorker` lo programa fuera del hilo de interfaz y entrega cuadros
compactos a la tarjeta y a la mesa.
Qt no se actualiza a la frecuencia de reloj de la FPGA. La compilación
incremental usa una caché administrada del usuario, fuera de `ice-build`.

Las entradas GPIO, salidas muestreadas, observaciones temporales para LED y
displays, captura VGA por ciclo y flancos/entradas temporizadas de la API
UART/SPI en desarrollo son rutas distintas dentro de ese flujo.
La respuesta MISO básica de SPI es una fuente reactiva de byte nativa,
configurada mediante el worker: observa SCK/CS cada ciclo virtual sin trabajo
Python por ciclo. Su estado es independiente de la cola acotada del monitor.

Las restricciones del proyecto relacionan los nombres HDL generados con los
endpoints físicos de la tarjeta; así funcionan LEDs y controles aunque la red
HDL no se llame como su etiqueta visual. Un periférico puede seguir conectado
físicamente en el Lab aunque el HDL actual no utilice ese pin.

## Módulos principales

### Límite del núcleo independiente de frameworks

Definiciones/catálogos/datos de layout de tarjetas, perfiles, restricciones y
conexiones, compilador/generador del wrapper, caché/resolución de herramientas,
binding del modelo nativo, modelos temporales y decodificación/planificación
UART/SPI pueden importarse sin PyQt6 ni aplicación Qt. No leen preferencias Qt.
Los anfitriones sin GUI usan solicitudes de compilación/perfiles explícitos y
rutas/entorno de herramientas. El paquete sigue instalando PyQt6 para la
aplicación de escritorio; no hay una distribución headless separada.

`messages.py` formatea mensajes fuente en inglés por defecto, sin cargar catálogos
ni preferencias. El anfitrión puede instalar explícitamente una función de
traducción para todo el proceso con `set_translator`; `None` restaura el inglés.
Importar el adaptador de escritorio `i18n.py` instala el traductor del gestor Qt,
conservando cambios de idioma y fallback de formato. No es una configuración por
petición: clientes web concurrentes no deben cambiarla para cada solicitud.
Un futuro adaptador servidor deberá resolver la presentación por cliente.

Para un modelo nativo ya compilado y su perfil correspondiente:

```python
from fpga_lab.profile import BoardProfile
from fpga_lab.simulation import VerilatorSimulation

profile = BoardProfile.load("profile.json")
with VerilatorSimulation("./model.so", profile) as model:
    model.set_input("button", 1)  # Debe ser una entrada del perfil.
    model.ticks(1000)
    print(model.get_output("led"))  # Debe ser una salida del perfil.
```

Usa la extensión de biblioteca apropiada para el sistema. La ejecución sigue
necesitando un modelo compilado compatible: quitar imports Qt no aporta una
toolchain ni aísla código nativo. `SessionService` prepara, compila y abre sesiones
sin Qt; preferencias, diálogos y coordinación visual siguen en el escritorio.
`SimulationWorker` adapta temporizador y señales al motor independiente. No se
incluye un servidor web.
Las regresiones bloquean imports Qt en un proceso nuevo, preparan una compilación
nativa y ejercitan la ABI generada con un modelo sintético.

### Motor de ejecución y planificación del anfitrión

`simulation_engine.py` controla ejecución y datos de cuadros. No tiene temporizador
ni bucle de eventos: el anfitrión aporta tiempo real transcurrido a
`advance(segundos)`. `play()` habilita el avance; `pause()` lo suspende sin reiniciar
el modelo. `power_off()` detiene, reinicia captura/colas de entrada y devuelve un
cuadro apagado. `reset()` limpia estado/colas y conserva si estaba ejecutándose.
`close()` cierra el modelo a su cargo una sola vez e impide seguir usándolo.
Todas las operaciones del motor/modelo deben permanecer en un único hilo dueño;
no es un gestor multicliente seguro entre hilos ni crea un hilo en segundo plano.

```python
from fpga_lab.profile import BoardProfile
from fpga_lab.simulation import VerilatorSimulation
from fpga_lab.simulation_engine import SimulationEngine

profile = BoardProfile.load("profile.json")
engine = SimulationEngine(VerilatorSimulation("./model.so", profile), clock_hz=12_000_000)
try:
    engine.play()
    frame = engine.advance(1 / 60)  # Explicit elapsed time; not a sleep.
    print(frame.outputs)
    engine.reset()
    blank_frame = engine.power_off()
finally:
    engine.close()
```

Usa el reloj configurado de la tarjeta/sesión, no supongas los 12 MHz del ejemplo.
El worker de escritorio aporta tiempo monotónico real desde su temporizador Qt.
La recuperación se limita a 100 ms por llamada y conserva fracciones de ciclo;
la velocidad usa tiempo real sin recortar. Los cuadros conservan timestamps
nativos y notifican flancos perdidos, descartando el lote incompleto en overflow.
Los pulsos y persistencia LED usan tiempo virtual, no intervalos de refresco.
La planificación UART y configuración nativa SPI/VGA pertenecen al mismo motor.
Las excepciones se propagan al anfitrión sin GUI; el adaptador Qt conserva señales
de error/aviso y detiene su temporizador ante fallos de ejecución. Después de
apagar, cambiar entradas combinacionales no publica salidas hasta Run.

### Preparación, compilación y propiedad de sesiones

`session.py` ofrece `SessionService` síncrono para escritorio y anfitriones sin GUI.
No abre diálogos, lee QSettings, crea hilos ni elige idioma.
`prepare(ice_file, lab_file=..., board_id=..., profile=..., clock_hz=...)` lee la
exportación existente de Icestudio, resuelve tarjeta/perfil y PCF/XDC y devuelve
`PreparedSession` con controles integrados, conexiones, avisos y `lab_document`
sin modificar, incluidos metadata/anotaciones. Trata sus diccionarios anidados
como datos de solo lectura.
Las instancias/conexiones desconocidas permanecen conservadas en el Lab original;
preparar no importa ni reescribe el archivo. Tarjeta/reloj explícitos tienen
prioridad sobre metadata; en su ausencia usa la tarjeta/reloj del Lab y después
la tarjeta predeterminada y su reloj. El perfil manual opcional es un objeto
`BoardProfile`, no una ruta de archivo.

`build(prepared, verilator=..., optimization_mode=..., cancel_requested=...)` usa
la caché exacta/incremental administrada, comprueba cancelación antes/después y
la transmite al compilador. No sustituye la sesión activa.
`open(prepared, artifact, observation_hz=...)` cierra la sesión anterior antes de
inicializar el modelo nativo y crea un motor pausado con niveles inactivos de
controles integrados, incluidos botones activos en bajo. Devuelve
`SimulationSession` con preparación, artefacto, binding y motor. `close()` es
idempotente; si falla la configuración, cierra el modelo que ya cargó.
Cada preparación debe usarse con su propio artefacto compilado.

```python
from fpga_lab.session import SessionService

service = SessionService(cache_dir="/path/to/managed-cache")
prepared = service.prepare("design.ice", lab_file="example.lab")
artifact = service.build(prepared, verilator="/path/to/sdk/bin/verilator")
session = service.open(prepared, artifact)
try:
    session.engine.play()
    frame = session.engine.advance(1 / 60)
    print(frame.outputs, prepared.wires, prepared.warnings)
    session.engine.reset()
    session.engine.power_off()
finally:
    service.close()
```

Se requieren exportaciones `ice-build` existentes y herramientas compatibles.
Compilar bloquea al llamador: el `BuildWorker` de escritorio lo hace fuera del
hilo gráfico. Solo datos de preparación/compilación de lectura cruzan esa frontera;
abrir y operar el modelo corresponde a su dueño. El escritorio cierra el worker
anterior antes de `open` y transfiere el motor nuevo al worker Qt; no operes el
servicio/modelo concurrentemente desde otro hilo. Servicios separados no aíslan
la ABI global del proceso: la misma biblioteca no admite varios dueños activos.

Es la base de sesiones nativas, no un renderizador headless del Lab ni una API
servidor. No incluye HTTP, aislamiento multiusuario ni sandbox de servidor.

### Plan de canales de periféricos

`peripherals.channel_plan.build_channel_plan(project, wires, profile, catalog=...)`
construye un `ChannelPlan` inmutable sin Qt. Recibe un `VirtualLabProject`, sus
conexiones resueltas mediante tarjeta/restricciones y el `BoardProfile` del modelo
nativo. El catálogo opcional relaciona identificadores de tipo con `PeripheralSpec`;
si se omite, carga el catálogo integrado/del usuario. Preparar el plan no modifica
el Lab ni configura el motor.

El plan incluye predicados temporales, canales de captura/entrada y configuración
del respondedor SPI nativo. Los enlaces identifican `(peripheral_id, terminal)`,
no widgets. Los índices de canal siguen el orden del proyecto/manifiesto; los de
salida siguen el perfil. Tipos no disponibles y referencias HDL inválidas o sin
mapear no reservan canales. Se conserva el comportamiento del escritorio para
polaridad/habilitación del común y avisos de respuesta SPI.

El anfitrión puede pasar `plan.temporal_probes`, `plan.edge_channels`,
`plan.drive_channels` y `plan.spi_slaves` a los métodos de configuración
correspondientes del motor en su hilo dueño. Debe conservar el orden de las tuplas
al distribuir frames y resultados de envío. El escritorio relaciona identificadores
con elementos gráficos y emite sus señales Qt existentes. El historial de flujos,
el ciclo de vida de los decodificadores y la presentación siguen en los
renderizadores de escritorio; este plan todavía no es un runtime completo de
periféricos independiente de la interfaz.

### Mapa de módulos

- `app.py`: coordinación de escritorio y presentación de compilación asíncrona.
- `session.py`: preparación, caché y propiedad de sesiones nativas sin GUI.
- `compiler.py` y `build_cache.py`: generación con Verilator y compilación incremental.
- `simulation.py`: enlace nativo; `simulation_engine.py`: ejecución y cuadros.
- `simulation_worker.py`: adaptador de temporizador, ciclo de hilo y señales Qt.
- `virtual_lab.py`: composición de tarjeta y mesa.
- `peripherals/catalog.py` y `peripherals/manifest.py`: catálogo declarativo.
- `workbench/view.py` y `workbench/item.py`: interacción con el lienzo e instancias visuales.
- `wiring.py`: resolución terminal del Lab → tarjeta → HDL.

## Paquetes de tarjetas

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

### Restricciones del proyecto y pinout de referencia

Estos archivos cumplen funciones diferentes:

- **`main.pcf` o `main.xdc` del proyecto:** se lee desde `ice-build/<design>/`
  del proyecto de Icestudio. Relaciona las redes HDL de ese diseño con pines FPGA.
- **`pinout.pcf` o `pinout.xdc` de la tarjeta:** pertenece al paquete de tarjeta
  y es su referencia de pines. Incluye solo uno; no sustituye al del proyecto.

En XDC se leen asignaciones literales `set_property PACKAGE_PIN <pin>
[get_ports {<puerto>}]`, incluidos bits de bus y la forma `-dict`. No se evalúan
otros comandos Tcl. Una expresión `PACKAGE_PIN` no admitida produce un error
en vez de un mapa vacío.

### Descubrimiento e identificadores

`BoardCatalog` descubre las carpetas y valida archivos requeridos, definición,
layout, perfil y restricciones. Los paquetes inválidos se omiten con un diagnóstico.

| Identificador | Dónde se usa |
| --- | --- |
| Nombre de carpeta, como `alhambra_ii` | `board_id` interno del paquete para localizar sus recursos. |
| `id` de `board.json`, como `alhambra-ii` | Identificador público de la tarjeta. |
| `metadata.board_id` de un Lab | Guarda el identificador público de la tarjeta seleccionada. |

Al abrir un Lab, su identificador público se resuelve a la carpeta del paquete.
Cambiar el selector actualiza los metadatos; un Lab sin `metadata.board_id`
usa Alhambra II por defecto.

### Reloj y muestreo

- `clock_hz` de la tarjeta establece su reloj virtual predeterminado.
- Un `metadata.virtual_clock_hz` positivo lo reemplaza para ese Lab. Cambiar
  la tarjeta elimina el ajuste; `--clock-hz` prevalece solo en la sesión actual.
- El refresco de interfaz y el muestreo temporal son ajustes globales por usuario.

### Controles integrados

Los roles opcionales de `layout.json` distinguen controles de simulación y E/S FPGA:

| Elemento | Rol | Comportamiento |
| --- | --- | --- |
| LED de tarjeta | `power` | Indicador de ejecución sin requerir un pin FPGA. |
| Botón de tarjeta | `reset` | Reinicia la simulación sin requerir un pin FPGA. |

Asigna los roles en **Editar layout**. Cada rol pertenece a un solo elemento;
asignarlo a otro lo transfiere. `PWR` y `RESET` son identificadores internos
sugeridos: el comportamiento depende del rol, no del nombre.

Para LEDs normales, `controls.leds` de `board.json` define el orden de las
muestras publicadas por el worker. Los endpoints identifican los LEDs visuales
de `layout.json`; se admite cualquier número de LEDs, incluso ninguno.

### Editor de layout

- **Señal de la tarjeta:** selecciona endpoints lógicos de `board.json`, no
  pines físicos ni redes HDL del proyecto. Los LEDs ofrecen output/inout y los
  botones input/inout, excluyendo el reloj. Los roles power/reset permiten
  nombres internos. Las señales antiguas no disponibles se conservan; no se
  permite guardar señales vacías.
- **Creación de componentes:** un único formulario comienza por el rol y sigue
  con identificador y señal. Los identificadores inválidos o duplicados quedan
  en el formulario para corregirlos, sin cerrarlo.
- **Secciones del panel:** separan propiedades/acciones, creación, rotación o
  reflejo de toda la tarjeta y controles de vista. Guardar y cerrar quedan al pie.
- **Persistencia:** la geometría de ventana y el divisor entre lienzo y
  propiedades se recuerdan por usuario.

## Integración de tarjetas: iCEBreaker Bitsy

Un pin de `board.json` puede declarar `"active_low": true` (por defecto: false).
Las mediciones de LED se invierten antes de aplicar persistencia visual; un
botón activo en bajo envía 1 al soltarlo y 0 al presionarlo. Los niveles de
reposo se restauran antes de ejecutar y después de un reset de tarjeta. Los
alias de un pin físico conservan la misma red HDL; la búsqueda inversa prefiere
un endpoint del conector.

El paquete `icebreaker_bitsy_v1/` integra una segunda tarjeta mediante la misma
estructura de definición, pinout, perfil, layout y recursos usada por Alhambra II.
Usa el identificador `iCEBreaker-bitsy1` de Icestudio. El soporte validado cubre
el reloj de 12 MHz, los LEDs de usuario activos en bajo, el botón integrado,
GPIO externo y la selección de tarjeta por Lab. No se simulan USB, flash,
PSRAM ni el bloque especializado RGB.
La imagen es un recorte de la tarjeta informativa original de iCEBreaker;
consulta `ATTRIBUTION.md` del paquete para conocer la fuente y los créditos.
Al cambiar de tarjeta, las conexiones a pines inexistentes se conservan en el
Lab, inactivas y con un aviso. Las asignaciones no se traducen automáticamente
entre tarjetas; al volver a la anterior se resuelven nuevamente sin perder
conexiones.

## Distribución y herramientas

La [guía de empaquetado](packaging.md) describe PyInstaller, construcción del
SDK controlado, fuentes correspondientes, pruebas de descarga y paquetes offline.
Separa los procedimientos reproducibles de mantenimiento del desarrollo de la
aplicación. Las evidencias de artefactos y controles de publicación quedan en los
[registros de cumplimiento del SDK](https://github.com/lmcapacho/FPGALab/tree/main/packaging/linux_toolchain/compliance).

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
