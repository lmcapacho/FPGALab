# iCEBreaker Bitsy v1.1c resources

- Pin names and package assignments: FPGAwars/Icestudio `develop`, board
  `iCEBreaker-bitsy1`: https://github.com/FPGAwars/icestudio/tree/develop/app/resources/boards/iCEBreaker-bitsy1
- Hardware design: © 2018–2021 1BitSquared, © 2018–2020 Piotr Esden-Tempski,
  © 2020–2021 Jordi Pakey-Rodriguez; CC BY-SA 4.0 as declared in the v1.1c
  schematic and PCB. Accessible source mirror:
  https://github.com/zmetzing/icebreaker-bitsy/tree/master/hardware/bitsy-v1.1c
- `board.svg`: a board-only crop of the upstream iCEBreaker artwork
  [`icebreaker-bitsy-v1.1c_info-card_front.svg`](https://codeberg.org/icebreaker-fpga/icebreaker/src/branch/master/hardware/bitsy-v1.1c/ref/icebreaker-bitsy-v1.1c_info-card_front.svg).
  The original artwork belongs to its upstream creators, not to the FPGALab
  integrator. The adaptation removes the surrounding information card and
  retains the board image in an SVG container. Hardware licensing is described
  above; the artwork's specific redistribution terms still need confirmation
  before releasing this experimental package.
- FPGALab definition, layout, and profile: experimental integration for user
  testing. No USB, flash, PSRAM, or RGB hard-IP model is supplied.

`BTN`, `LEDR`, and `LEDG` are active-low. `LEDR` shares FPGA pin 25 with
`P13`; `LEDG` shares its signal with PSRAM chip select. CDONE is shown as
the simulation-active indicator, not as an HDL GPIO.
