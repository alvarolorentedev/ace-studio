# ACE Studio UI guidelines

## Foundation

ACE Studio is a dark, desktop-first application. Use the semantic colors in `ace_studio.theme`: ink for the application background, panel for cards and dialogs, raised for subtle grouped content, border for separation, green for the single primary action, muted for secondary text, and danger only for destructive actions and failures. Do not introduce raw color values in views.

Use Inter throughout. Page titles are 32px, section titles 20px, card titles 17px, body text 14–16px, and helper text 12px. Use the spacing scale 4, 8, 12, 16, 24, and 32px. Controls use an 8px radius; cards and dialogs use 12px.

## Layout and controls

Use a padded standard page for Library, Edit, Train, and setup. Create is the only split workspace: its inspector may remain beside the main editor. Settings remains a scrollable dialog. Use responsive rows so multi-column pages stack rather than clip at the 900×700 minimum window size; the global player remains visible below page content.

Use one filled green primary button for the main action in a task region. Use neutral buttons for secondary actions, text or icon buttons for low-emphasis actions, and red only for destructive actions. Every icon-only action needs a tooltip. Inputs, dropdowns, and read-only file fields use the shared field style: hover remains neutral and green is reserved for focus. Use a checkbox or switch only for an immediate binary choice; use a dropdown for finite options; use a slider only for a continuous value with a readable label.

Advanced or infrequent controls belong in an expansion tile. Keep status, progress, and recovery instructions adjacent to the action that caused them. Empty states should explain the next useful action.

## Accessibility

Controls must have visible labels, keyboard focus, and a target size of at least 44px where practical. Keep text and essential controls at WCAG AA contrast or better against their background. Do not rely on color alone for selected, loading, success, or error states; pair it with text or an icon. Verify keyboard traversal, focus visibility, dialogs, and responsive layouts before handoff.
