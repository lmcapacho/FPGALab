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
La respuesta MISO básica de SPI es una fuente reactiva de byte nativa,
configurada mediante el worker: observa SCK/CS cada ciclo virtual sin trabajo
Python por ciclo. Su estado es independiente de la cola acotada del monitor.

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

## Runtime gráfico portable

Construye la aplicación Linux en Ubuntu 24.04 con PyInstaller y el archivo
`packaging/pyinstaller/FPGALab.spec`. Instala las bibliotecas XCB de construcción
indicadas por `packaging/pyinstaller/linux_runtime.py` (también las instala el
workflow de release). El spec las incluye explícitamente y falla si falta alguna,
en vez de generar un ejecutable que exija instalarlas al usuario. PyInstaller
resuelve sus dependencias transitivas. Distribuye la carpeta portable completa,
incluyendo `_internal`.

Wayland nativo sigue habilitado. El arranque muestra la ventana normal y espera
su primera exposición antes de maximizar; X11 y las demás plataformas maximizan
directamente. No se impone `QT_QPA_PLATFORM` globalmente. Las pruebas automáticas
verifican ese orden; también se validó el arranque predeterminado en un escritorio
Ubuntu 24.04 limpio sin forzar X11. Otras configuraciones de compositor requieren
validación aparte; una prueba sin escritorio por sí sola no valida el compositor.

## Toolchain Linux autocontenido experimental

`packaging/linux_toolchain/build.py` es un **prototipo para mantenedores**, no
el descargador del primer inicio ni un nuevo requisito de instalación. Copia
paquetes Debian/Ubuntu ya instalados a un SDK privado: Verilator, GNU Make,
GCC/G++, binutils, Perl, Python y utilidades, con cabeceras, bibliotecas y
archivos de copyright. No instala paquetes ni cambia la búsqueda actual de
herramientas de FPGALab. Registra versiones exactas, sistema y glibc en
`toolchain.json`. Esta etapa admite Linux x86-64; la primera base local es
Ubuntu 24.04/glibc 2.39. No es un binario universal para cualquier Linux.

### Construcción controlada sobre Ubuntu

La ruta experimental preferida usa `container_build.py`. Docker se necesita
**solo en el equipo del mantenedor o CI**, con acceso a su servicio; el usuario
final no necesita Docker. El script no instala paquetes ni cambia permisos de
Docker en el equipo anfitrión.

```bash
python3 packaging/linux_toolchain/container_build.py --output /tmp/fpgalab-controlled-sdk
```

`packaging/linux_toolchain/recipe.json` fija la imagen oficial Ubuntu 24.04 amd64
por digest y la fecha de un [snapshot de paquetes Ubuntu](https://snapshot.ubuntu.com/).
La imagen se actualiza y las herramientas se instalan desde ese repositorio
firmado y congelado, no desde los paquetes del desarrollador ni el mirror actual.
Actualizar la base o las herramientas requiere revisar y cambiar la receta;
las versiones exactas de los paquetes binarios y fuente quedan en la salida.
Esto controla los insumos, pero no garantiza archivos comprimidos idénticos bit a bit.
La confianza HTTPS se prepara con `ca-certificates=20240203` desde el repositorio
original firmado de Noble por HTTP, antes de activar el snapshot HTTPS. Se
mantienen las verificaciones TLS y las firmas de APT; cualquier fallo al descargar
un repositorio detiene la construcción. El contexto de Docker solo incluye la
aplicación y los scripts del SDK, no el entorno virtual, historial Git ni archivos
locales de configuración del checkout.

El script reubica el SDK, prepara la prueba sintética de la ABI nativa de FPGALab
y la ejecuta en el Ubuntu limpio fijado, sin red, cabeceras ni compiladores del
anfitrión. Los contenedores son de solo lectura salvo la carpeta nueva de salida
y el almacenamiento temporal. Solo genera el comprimido y checksum si pasa la
prueba. La salida incluye `toolchain.json`, `source-packages.json`, copyrights,
`REDISTRIBUTION.txt` y un comprobante separado `validation.json`. Si falla conserva
la salida parcial para diagnóstico; se reintenta con otra carpeta nueva.

El workflow manual **Experimental Linux SDK** de GitHub Actions ejecuta el mismo
proceso y conserva los artefactos experimentales exitosos durante siete días.
No crea un release ni modifica el empaquetado habitual. La receta controlada de
Ubuntu pasó la prueba nativa con SDK reubicado y sin red. La prueba se repite al
cambiar la receta; las pruebas unitarias solas no validan una nueva toolchain.

Esta prueba valida el SDK/modelo nativo, no la aplicación PyQt completa en un
escritorio limpio. El empaquetado gráfico, otras distribuciones y las obligaciones
de entrega del código fuente correspondiente siguen pendientes antes de publicar.

### Snapshot local y prueba aislada

El constructor local anterior sigue disponible para diagnóstico, pero no es la
ruta controlada de distribución:

```bash
python3 packaging/linux_toolchain/build.py \
  --output /tmp/fpgalab-sdk \
  --archive /tmp/fpgalab-sdk.tar.gz
.venv/bin/python packaging/linux_toolchain/probe.py \
  --sdk /tmp/fpgalab-sdk --work-dir /tmp/fpgalab-sdk-probe --isolated
```

Usa carpetas nuevas, inexistentes y sin espacios. El archivo comprimido opcional
incluye una suma SHA-256 aparte; esa suma no demuestra por sí sola procedencia
confiable. No se sobrescriben salidas existentes. Los candidatos distribuibles
deben generarse en un entorno controlado, no desde instalaciones arbitrarias.
Antes de publicar falta revisar las obligaciones de redistribución, licencias y
código fuente correspondiente; incluir copyrights no completa esa revisión.
Los binarios del SDK no deben agregarse al repositorio.

La prueba aislada requiere **bubblewrap solo en el equipo del mantenedor**.
Monta el SDK y una carpeta temporal, con el shell, `env`, cargador y libc del
anfitrión como base del sistema; no ve compiladores, cabeceras, Apio ni red del
anfitrión. Usa el C ABI generado por FPGALab para compilar Verilog sintético,
cargar la biblioteca y comprobar lógica combinacional, reloj y Reset. Ejecuta
Make otra vez para verificar la compilación ya terminada. Mueve el SDK a otra
ruta y repite la prueba en una carpeta nueva para verificar su reubicación;
no reutilices Makefiles que apuntan a la ruta anterior. Sin `--isolated` solo se
limita PATH: eso no prueba independencia de cabeceras o bibliotecas del sistema.

Las herramientas usan su cargador/bibliotecas y PATH propios. GCC usa las
cabeceras y bibliotecas del sysroot empaquetado; Python y Perl usan sus
bibliotecas estándar privadas. El prototipo depende del kernel Linux y del
shell básico. Los modelos se cargan en el proceso de la aplicación y deben
ser compatibles con su ABI; faltan validaciones con glibc anterior, otras
distribuciones/arquitecturas, rutas con espacios y el runtime gráfico. La
descarga inicial, selección automática, firma e instaladores quedan para pasos
posteriores: estos scripts no los implementan.

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
