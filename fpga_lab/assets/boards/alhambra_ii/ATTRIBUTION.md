# Alhambra II resources

## Original board and artwork

- Board project: [FPGAwars/Alhambra-II-FPGA](https://github.com/FPGAwars/Alhambra-II-FPGA).
  Its README credits **Eladio Delgado Mingorance** as the board author and
  states that Alhambra II V1.0 derives from Icezum Alhambra V1.1.
- Source for `board.svg`:
  [Alhambra II_V1.0A - Board_v1.0.svg](https://github.com/FPGAwars/Alhambra-II-FPGA/blob/master/doc/pinout/Alhambra%20II_V1.0A%20-%20Board_v1.0.svg).
  The upstream artwork is used for the virtual board; FPGALab does not claim
  authorship of the original SVG or hardware design. Interactive overlays,
  orientation and control geometry are configured separately in `layout.json`.
- The board project's README declares
  [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/).
  Preserve the upstream attribution and the applicable ShareAlike terms when
  redistributing or adapting its artwork. The repository also contains an
  LGPL-3.0 `LICENSE` file; this notice records the README's hardware/design
  declaration rather than treating all upstream resources as uniformly licensed.

## Pin mapping and FPGALab integration

- Pin names and assignments reference the
  [Icestudio `alhambra-ii` board package](https://github.com/FPGAwars/icestudio/tree/develop/app/resources/boards/alhambra-ii).
  Credit remains with the upstream Icestudio contributors for those resources.
- `board.json`, `layout.json`, `profile.json` and the reference `pinout.pcf`
  form the FPGALab integration. They describe mapping and simulation behavior,
  not a new physical board design or a claim of authorship over upstream data.
- FPGALab's software license does not replace the licenses of third-party
  hardware documentation and artwork.
