# API de periféricos externos

Un periférico externo es una carpeta con `manifest.json` y, cuando corresponde, archivos SVG. FPGALab lee sus datos al iniciar o al instalarlo desde el catálogo. El paquete no ejecuta código Python propio. La API versión 1 está disponible en FPGALab 0.1.0rc4. La versión 2 añade flujos de flancos en la versión de desarrollo posterior a RC4; no forma parte de sus artefactos.

## Empezar con un ejemplo

El [relé simple](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/simple_relay) muestra el paquete de salida digital más pequeño. Los ejemplos de [pulsador](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/simple_button), [barra de LED](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/led_bar), [medidor PWM](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pwm_meter) y [servo](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pulse_servo) cubren los demás comportamientos reutilizables.

```text
simple_relay/
├── manifest.json
├── icon.svg
├── off.svg
└── on.svg
```

`id` debe coincidir con el nombre de la carpeta y ser único entre los periféricos integrados e instalados. Para paquetes nuevos destinados a compartirse, conviene elegir un ID con espacio de nombres, como `tu_nombre.relay`; la API no exige todavía ese formato. `label` es el nombre visible.

## Campos de `manifest.json`

| Campo | Tipo | Uso |
| --- | --- | --- |
| `api_version` | entero, opcional | Versión del formato: `1` o `2`; si se omite se asume `1`. La versión 2 es necesaria para flujos de flancos. |
| `id` | texto, obligatorio | Identificador estable; debe coincidir con la carpeta. |
| `label` | texto, obligatorio | Nombre mostrado en el catálogo. |
| `category` | texto, opcional | Categoría del catálogo; por defecto `output`. Admite categorías nuevas. |
| `description` | texto, opcional | Descripción que aparece en la búsqueda y en el catálogo. |
| `keywords` | lista de textos, opcional | Palabras adicionales para la búsqueda. |
| `icon` | ruta relativa, opcional | SVG del catálogo, por ejemplo `icon.svg`. No es el dibujo del componente en la mesa. |
| `simulation` | objeto, obligatorio | Clase de señales y, si corresponde, medición temporal. |
| `terminals` | lista, opcional | Pines lógicos que se conectan a la tarjeta. |
| `properties` | objeto, opcional | Campos editables de cada instancia. |
| `visual` | objeto, obligatorio | Renderizador, tamaño y configuración gráfica. |
| `package` | objeto, opcional | Versión, autoría, licencia y compatibilidad para compartir y actualizar el paquete. |

### `package`: publicación y actualizaciones

Si incluyes `package`, sus campos obligatorios son `version` (versión semántica como `1.0.0`), `author.name`, `license` (identificador de estilo SPDX) y `compatibility.minimum_fpgalab` (por ejemplo, `0.1.0rc4`). `author.url` y `repository` son URL HTTP(S) opcionales.

`contributors` y `maintainers` son listas opcionales de objetos con `name` obligatorio y `url` HTTP(S) opcional. `author` conserva al creador original; agrega otras personas únicamente cuando hayan participado. Para actualizar un paquete instalado, conserva su `id`, aumenta `package.version` y vuelve a instalarlo. FPGALab valida el reemplazo y pide confirmación; rechaza archivos distintos con la misma versión o una anterior.

### `terminals`: conexiones

Cada terminal tiene `name` y `direction`. `input` significa entrada **hacia el FPGA** (por ejemplo, un pulsador); `output` significa salida **desde el FPGA** (por ejemplo, un LED). `width` es un entero positivo, por defecto `1`; `required` es booleano, por defecto `true`. `supplies`, si se usa, contiene únicamente `GND` o `VCC`. Los nombres no pueden repetirse.

### `simulation`: señales disponibles

| `class` | Uso |
| --- | --- |
| `gpio_driven` | El periférico cambia una entrada del FPGA mediante una interacción. |
| `gpio_sampled` | Se lee el último nivel de una salida en cada actualización de la interfaz. |
| `gpio_temporal` | Se observan salidas durante los ciclos simulados. Para los ejemplos externos, usa `"temporal": {"mode": "per_terminal"}`. |
| `streaming_sink` | Ruta especializada usada por VGA; aún no es una API declarativa general para UART, I²C o SPI. |
| `edge_stream` | API v2: captura flancos de salidas de un bit y, opcionalmente, programa cambios en entradas del FPGA por ciclo virtual. |

Una terminal temporal puede ofrecer `duty_cycle` (fracción entre 0 y 1), `edge_rate_hz` y `pulse_high_seconds` (duración, en segundos, del último pulso alto **completo**). Las mediciones usan tiempo virtual y la tasa de muestreo configurada; señales más rápidas pueden sufrir aliasing. `pulse_high_seconds` no aparece hasta que se observa el flanco descendente. El modo `display_common` existe para los displays integrados, pero no es el punto de partida recomendado para paquetes externos.

En `edge_stream`, declara `"channels": ["rx"]` dentro de `simulation`. Cada canal debe nombrar una terminal `output` distinta de un bit. Una simulación admite hasta 16 canales de captura, sumando los de todos los periféricos instalados. La cola nativa conserva hasta 16 384 transiciones entre actualizaciones de la interfaz; si se desborda, el renderizador recibe el aviso para descartar una trama incompleta. Las marcas de tiempo son ciclos virtuales del FPGA, no tiempo real. La captura ocurre en cada flanco ascendente, por lo que no detecta cambios más breves que un ciclo. No depende de la tasa más baja de medición temporal.

Para controlar entradas del FPGA en ciclos virtuales precisos, agrega `"drives": ["tx"]` al mismo objeto `simulation`. Cada nombre debe ser una terminal `input` distinta de un bit; `"drive_idle": {"tx": 1}` fija su nivel de reposo. El programador nativo reserva ese bit y conserva los demás bits GPIO del mismo puerto. Aplica los cambios antes de cada flanco ascendente, también entre actualizaciones de la interfaz. La cola tiene un máximo de 8192 transiciones. El terminal UART integrado usa esta capacidad, pero los paquetes externos todavía no pueden aportar código arbitrario para otros protocolos.

### `properties`: campos editables

Cada propiedad declara `type`; puede añadir `label` y `default`. Los tipos admitidos son `color`, `color_map`, `enum`, `boolean`, `string` y `key_sequence`. `color_map` usa `keys` y un `default` con colores por clave; `enum` usa `values` y puede declarar `presets`. Declara solo las propiedades que utilice el renderizador elegido. El nombre `position` está reservado por la mesa.

## `visual`: renderizadores reutilizables

Todos requieren `renderer` y `size: [ancho, alto]` con enteros positivos. `chrome: "compact"` elimina el marco de tarjeta y deja el nombre de la instancia abajo. Las coordenadas de SVG e interacción corresponden al área gráfica; normalmente los últimos 24 píxeles de alto se reservan para ese nombre.

| Renderizador | Datos que lo controlan | Campos propios principales |
| --- | --- | --- |
| `state_svg` | Niveles digitales y entradas interactivas | `states`, `default_state`, `state_rules`, `interactions` |
| `led_array` | Brillo de varias salidas | `terminals`, `orientation`, `indicator_shape`, `show_labels`, `color_property` |
| `measured_svg` | Ciclo útil o ancho de pulso | `terminal`, `measurement`, rangos, transformación y dos SVG |
| `uart_terminal` | Flujo de flancos y entrada temporizada de API v2 | `channel`, `baud_property`, `tx_channel` opcional; recibe y envía texto UART 8N1 |

`state_svg` asocia nombres de estado con archivos SVG mediante `states`, por ejemplo `{"off": "off.svg", "on": "on.svg"}`. `default_state` elige el estado inicial. Cada elemento de `state_rules` tiene `state` y `when: {"terminal": "signal", "equals": 1}`; las reglas se evalúan en orden. Para controles, cada `interaction` especifica `terminal`, `region: [x, y, ancho, alto]` y uno de los pares `event`/`action`: `click`/`toggle` o `press_release`/`momentary`. La región debe quedar dentro del dibujo.

`led_array` enumera terminales de salida únicas en `visual.terminals`. `orientation` puede ser `horizontal` o `vertical`; `indicator_shape`, `circle` o `rectangle`; `show_labels` es booleano. `color_property` debe apuntar a una propiedad de tipo `color` (por defecto, `color`).

`measured_svg` compone `base_svg` (fijo) y `moving_svg` (móvil). Ambos SVG usan el tamaño y sistema de coordenadas de la zona gráfica. `terminal` señala una salida de un bit; `measurement` es `duty_cycle` o `pulse_high_seconds`; `input_range` y `output_range` son pares numéricos que relacionan la medición con la posición visual. `transform` admite `rotate` (grados) o `scale_x` (escala horizontal); `origin: [x, y]` fija el punto de transformación. La medición se limita al rango de entrada. Para ciclo útil con salida `[0, 1]`, `value_label: {"format": "percent", "rect": [x, y, ancho, alto]}` muestra el porcentaje. El [servo](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pulse_servo) usa giro; el [medidor PWM](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/pwm_meter), escala horizontal.

Los renderizadores anteriores `signal_meter` y `pulse_servo` siguen disponibles para paquetes existentes. Su aspecto está definido en FPGALab; para nuevos diseños con gráficos propios, usa `measured_svg`.

### Ejemplo serial: terminal UART

El [ejemplo de terminal UART](https://github.com/lmcapacho/FPGALab/tree/main/examples/peripherals/uart_terminal) es un paquete externo que solo necesita manifiesto e icono del catálogo. Conecta `rx` a la salida TX serial del FPGA y el `tx` opcional a su entrada RX; selecciona la misma tasa de baudios del HDL. Las direcciones de terminal se definen desde el FPGA: `rx` es `output` y `tx` es `input`. Sus campos relevantes son:

```json
{
  "api_version": 2,
  "simulation": {"class": "edge_stream", "channels": ["rx"], "drives": ["tx"], "drive_idle": {"tx": 1}},
  "terminals": [
    {"name": "rx", "direction": "output", "width": 1},
    {"name": "tx", "direction": "input", "width": 1, "required": false}
  ],
  "properties": {"baud": {"type": "enum", "default": "115200", "values": ["9600", "115200"]}},
  "visual": {"renderer": "uart_terminal", "size": [320, 200], "channel": "rx", "tx_channel": "tx", "baud_property": "baud"}
}
```

El terminal recibe texto ASCII y puede enviar hasta 512 bytes UTF-8 por envío. Su campo para escribir está activo durante la simulación y requiere que `tx` esté conectado a una entrada del FPGA. El codificador integrado programa un bit de inicio, ocho bits de datos del menos significativo al más significativo y un bit de parada con el reloj virtual configurado; no usa temporizadores de la interfaz. El paquete no puede ejecutar Python ni definir cualquier protocolo por sí mismo. La misma base se podrá reutilizar para futuros renderizadores I²C/SPI, pero estos aún no están implementados. `package.compatibility.minimum_fpgalab` no garantiza por sí solo que una versión anterior pueda abrir el paquete: RC4 rechaza `api_version: 2`, aunque el mínimo indicado sea `0.1.0rc4`.

## Validar, instalar y compartir

Desde la raíz del repositorio, valida una o varias carpetas:

```bash
python -m fpga_lab.peripherals.validate examples/peripherals/simple_relay
```

El comando revisa manifiesto, renderizador, recursos SVG, nombre de carpeta y versión mínima, sin instalar el paquete. En la aplicación, abre el catálogo y pulsa el icono de instalación junto a la búsqueda. Puedes elegir una carpeta o un ZIP que contenga **una única carpeta raíz** con `manifest.json` y sus recursos; los SVG deben permanecer dentro del paquete. El catálogo permite desinstalar paquetes del usuario sin borrar sus instancias de los Labs. Consulta [Arquitectura y contribución](development.md) para integrar nuevos renderizadores en el núcleo.

También puedes copiar la carpeta completa y reiniciar FPGALab. El catálogo de usuario está en `~/.local/share/FPGALab/peripherals/` (Linux), `%APPDATA%\FPGALab\peripherals\` (Windows) o `~/Library/Application Support/FPGALab/peripherals/` (macOS). Para desarrollo y pruebas, `FPGALAB_PERIPHERALS_DIR` sustituye temporalmente esa ubicación. Los Labs conservan sus instancias y conexiones al desinstalar; un tipo ausente aparece como no disponible hasta que se reinstale.
