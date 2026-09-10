# Testing policy

FPGALab uses automated tests to protect behavior that could break simulation results, saved Labs, supported toolchains, or cross-platform operation. A change does not require a new test merely because it changes code or appearance.

Add or update an automated test when a change affects:

- HDL compilation, caching, toolchain discovery, or process execution;
- simulation timing, input/output routing, PCF resolution, or peripheral behavior;
- Lab file compatibility, persistence, import/export, undo/redo, or migrations;
- public extension contracts such as manifests, renderers, frames, or bindings;
- a user-visible workflow whose regression would block or corrupt normal use;
- a confirmed bug that could reasonably recur.

Do not add a dedicated test for colors, margins, exact widget sizes, icon shapes, cursor appearance, QSS implementation details, or other purely visual decisions. Validate those changes with the visual checklist below. If several variants share one contract, prefer one parametrized test over many near-duplicates.

Tests should assert observable outcomes whenever possible. Access to private Qt attributes is acceptable only when no stable public boundary exists and the behavior is important enough to protect.

## Test layers

1. Unit tests cover parsing, policies, manifests, wiring, and deterministic simulation helpers.
2. Integration tests cover Labs, compiler/cache behavior, toolchain resolution, and component-to-HDL routing.
3. Qt workflow tests cover a small set of critical application flows. They should not become pixel or layout tests.
4. Packaging workflows validate supported Python versions and operating-system artifacts in CI.

Keep the default local suite fast enough to run before every commit. Slower end-to-end or packaging checks belong in CI rather than the default pytest run.

## Visual checklist for a release candidate

- Check the main window at a small and a large resolution.
- Check enabled, disabled, hover, pressed, error, and busy states.
- Open the Lab manager, simulation settings, peripheral configuration, and connection dialogs.
- Verify English and Spanish labels for clipping or overlap.
- Exercise workbench zoom, pan, selection, dragging, Fit, undo, and redo.
- Verify the application icon and packaged assets on each supported platform.
