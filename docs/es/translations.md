# Contribuir una traducción

FPGALab descubre los idiomas de la interfaz desde `fpga_lab/locales/*.json`.
Agregar un catálogo no requiere cambiar código Python. El inglés es el respaldo;
se aceptan traducciones parciales. Este flujo traduce la aplicación, no el sitio
de documentación.

## Crear un catálogo

Ejecuta desde la raíz del repositorio de código fuente, con Python 3.10+
(estas herramientas no requieren Qt):

```text
python -m fpga_lab.locale_tools template --code fr --name Français --output fpga_lab/locales/fr.json
```

Usa el comando que inicia Python 3 en tu sistema: si es necesario, sustituye
`python` por `python3` en Linux/macOS o por `py -3` en Windows.

Usa un código de idioma ISO, como `fr`, o uno regional, como `pt_BR`. El nombre
del archivo debe coincidir con el código. El comando lo crea directamente en
la carpeta de catálogos del código fuente, `fpga_lab/locales/`, no en la carpeta
del ejecutable instalado. No sobrescribe archivos existentes.

```json
{
  "_meta": {
    "code": "fr",
    "name": "Français",
    "contributors": ["Tu nombre o usuario"]
  },
  "Open {path}": ""
}
```

`name` es el nombre nativo del idioma; `contributors` permite acreditar a quienes
realmente tradujeron o revisaron ese catálogo. No atribuyas automáticamente el
trabajo a los mantenedores ni a contribuidores ajenos. Otros traductores pueden
agregar sus nombres después.

## Traducir de forma segura

- Cambia los **valores**, no las claves inglesas. Deja valores vacíos u omite las
  entradas pendientes: la interfaz usará inglés para ellas.
- Conserva los parámetros y su formato: `{path}`, `{count}`, `{value:.1f}`.
  Se pueden reordenar, pero no renombrar, agregar ni cambiar su formato.
- Conserva las marcas Markdown/HTML y los atajos (`&`) donde sean útiles. En JSON
  los saltos de línea se escriben `\n` y las comillas se escapan como `\"`.
- Guarda JSON UTF-8, sin comentarios, claves duplicadas ni comas finales.

Valida desde la raíz del repositorio:

```bash
python -m fpga_lab.locale_tools validate
```

El reporte muestra cobertura; una traducción incompleta no es un error. Los
metadatos inválidos, claves desconocidas, JSON incorrecto y parámetros diferentes
hacen fallar la validación y CI. Durante el arranque se omiten catálogos dañados
y se usa inglés para entradas individuales inválidas, sin impedir abrir la app.

Reinicia la ejecución desde código fuente para descubrir un archivo nuevo y
selecciona el idioma en la cabecera. El desplegable muestra nombres nativos y
el selector cerrado conserva el código compacto. Se recuerda la selección y los
controles que ya admiten traducción en vivo se actualizan al cambiar de idioma.
Revisa diálogos, textos largos y ambos temas. Qt determina la dirección de los
idiomas de derecha a izquierda. Sus botones estándar usan traducciones `qtbase`
empaquetadas y prueban el idioma base para variantes regionales; si Qt no ofrece
traducción, esos textos estándar permanecen en inglés.

Envía un pull request con el catálogo. Los paquetes distribuidos incorporan el
idioma al reconstruirse; editar una carpeta externa del usuario no instala un
idioma. La traducción de documentación puede proponerse por separado.

## Mantener la referencia inglesa

Al agregar textos `t("English text")` o etiquetas de periféricos incluidos, ejecuta:

```bash
python -m fpga_lab.locale_tools update-source
python -m fpga_lab.locale_tools validate
```

`en.json` es la referencia para generar plantillas y validar, no otra traducción
del inglés. El actualizador conserva las claves existentes, incluidas las
dinámicas. Agrega manualmente a esa referencia las claves dinámicas nuevas que
no puedan extraerse, con clave y valor ingleses idénticos. No sobrescribas otros
idiomas ni exijas completarlos al agregar una funcionalidad.
