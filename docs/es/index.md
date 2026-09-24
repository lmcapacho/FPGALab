# FPGALab

FPGALab es un laboratorio virtual de FPGA para diseños de Icestudio y Verilog. Compila el HDL generado con Verilator y conecta el modelo nativo resultante con una tarjeta interactiva y una mesa de periféricos.

## Comenzar

- Sigue [Primeros pasos](getting-started.md) para ejecutar tu primer diseño.
- Aprende a crear, importar y compartir [Labs](labs-and-workbench.md).
- Consulta [Toolchain y solución de problemas](troubleshooting.md) si FPGALab no encuentra Verilator o el compilador.
- Usa la [API de periféricos externos](peripheral-api.md) para crear e instalar tus propios componentes.
- Lee [Arquitectura y contribución](development.md) para ampliar el proyecto.

## Alcance actual

La primera tarjeta soportada es Alhambra II. El catálogo incluye LED, pulsadores, interruptores individuales y DIP, sensor de presencia vehicular, semáforo, displays de siete segmentos y BCD, y monitores VGA.

FPGALab se distribuye bajo la Licencia Pública General Affero de GNU, versión 3 o posterior.
