# Labs y mesa de trabajo

Un **Lab** es una configuración reutilizable de periféricos, independiente del proyecto de Icestudio. Almacena la tarjeta, los componentes, asignaciones de pines, propiedades, posiciones, zoom y posición de la cámara. El reloj virtual usa normalmente el `clock_hz` de la tarjeta seleccionada. En Configuración de simulación, activa **Usar otra frecuencia de reloj para este Lab** para cambiarla solo en ese Lab; restaurar los valores predeterminados vuelve al reloj de la tarjeta. El refresco de la interfaz y el muestreo temporal siguen siendo ajustes globales del usuario. El diálogo muestra la frecuencia efectiva de muestreo temporal, que no puede superar el reloj virtual.

Al iniciar por primera vez después de este cambio, el reloj virtual global guardado anteriormente se asigna al Lab activo. Los demás Labs usan el reloj de su tarjeta, salvo que se configuren por separado. La opción `--clock-hz` prevalece solo durante la ejecución actual y no modifica el Lab.

## Administrar Labs

Abre el administrador desde el selector de la barra superior. Puedes crear, duplicar, renombrar, eliminar, importar y exportar Labs. Los archivos `.lab` exportados son documentos JSON portables que se pueden compartir junto con el diseño `.ice` correspondiente.

Los archivos `.lab.json` anteriores siguen siendo compatibles. Al importar se
valida y copia el Lab al espacio de trabajo local sin sobrescribir otro Lab.
FPGALab recuerda el último Lab seleccionado en los ajustes del usuario y lo
recupera al iniciar. El archivo del Lab no contiene rutas de proyecto propias
de un computador.

Ubicaciones predeterminadas:

- Linux y macOS: `~/FPGALab/labs`
- Windows: `Documents/FPGALab/labs`

Configura `FPGALAB_WORKSPACE` para elegir otra carpeta raíz.

## Controles de la mesa

- Abre el catálogo con el botón flotante para agregar un periférico.
- Arrastra un componente para moverlo.
- Arrastra sobre un espacio vacío para seleccionar varios componentes.
- Usa `Shift`+clic para modificar la selección.
- Usa `Ctrl+D` para duplicar y `Supr` para eliminar.
- Usa `Ctrl+Z` y `Ctrl+Y` para deshacer y rehacer.
- Usa la rueda del mouse para controlar el zoom.
- Usa `Ctrl`+arrastrar o el botón central para desplazar la mesa.
- Usa la barra para volver a 100 % o encuadrar todos los elementos.

Los terminales pueden quedar sin conexión mientras se organiza el Lab. Al iniciar la simulación se informan las conexiones obligatorias faltantes.

## Catálogo de periféricos

Abre el catálogo flotante para buscar por categoría o nombre y agregar un
periférico. El catálogo integrado incluye pulsadores, interruptores, LED,
sensores, semáforos, displays de siete segmentos y BCD, y monitores VGA.
También puedes instalar un paquete declarativo desde una carpeta o un ZIP con
la acción de instalación del catálogo; los paquetes instalados pueden
desinstalarse allí. Si un paquete deja de estar disponible, sus instancias
guardadas en el Lab no se borran. El formato y las reglas de validación están
en la [API de periféricos externos](peripheral-api.md).

## Tiempo virtual y actualización visual

El modelo nativo agrupa ciclos de FPGA mientras la interfaz se actualiza a una
frecuencia menor. La configuración de simulación controla el reloj virtual de
cada Lab, la frecuencia de refresco de interfaz (60 Hz de forma predeterminada)
y el muestreo temporal global (1 MHz de forma predeterminada) para efectos como
brillo PWM y displays multiplexados. El común de un display puede conectarse a
`GND` o `VCC`, o controlarse con un pin FPGA para multiplexación. Un muestreo menor reduce
el costo de medición; usa una frecuencia suficiente para observar la señal que
te interesa. El equipo puede no sostener un reloj solicitado muy alto, sobre
todo con diseños o Labs complejos; la barra de estado muestra la velocidad real.

Los diseños VGA de 640×480 suelen necesitar un reloj virtual cercano a 25 MHz.
FPGALab advierte si se usa un monitor VGA con los 12 MHz predeterminados de
Alhambra II, pero no cambia automáticamente el reloj. El catálogo incluye
monitores VGA de 1, 6 y 12 bits.
