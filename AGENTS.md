# ACE Studio agent instructions

Before making any change, read `docs/architecture.md` and `docs/ui-guidelines.md` completely.

- Keep endpoint paths, polling, filesystem work, and persistence in services; views only collect input and render state.
- Reuse the semantic values and control styles in `ace_studio.theme`. Do not introduce screen-local colors or a second component system.
- Preserve keyboard access, visible focus, labels, errors, and responsive behavior at the supported minimum window size.
- Update the relevant architecture or UI guideline when changing a shared convention, then run the smallest relevant test plus `make check` before handoff.
