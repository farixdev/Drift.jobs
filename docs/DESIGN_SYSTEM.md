# Drift — Design System (Phase 1)

macOS Sonoma / iOS 17 system aesthetic, built natively in PyQt5. Restrained,
dense-but-breathable, expensive. Light and dark are true hand-tuned pairs; every
value flows from one token file and nothing hardcodes a hex outside it.

**See it:** run the app and press **Ctrl+Shift+D** for the live gallery — every
component in every state, with a Light/Dark/Auto switch and the eight accents.
(The spec's `/design-system` *route* is a *screen* here; Qt has no URL routing.)

```
ui/theme/            tokens · manager · qss · motion
ui/components/       controls · inputs · display · feedback · navigation · overlays · table
ui/screen_design_system.py   the gallery
```

---

## Foundations

### Typography
Stack: `-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display",
"Inter", "Segoe UI", system-ui, sans-serif`. SF Pro is not licensed for web/redist
and is not bundled; on macOS the system face is used, elsewhere it falls through
to Segoe UI / Inter. Semantic scale (size/line-height/weight/tracking):

| Role | px / line | Weight | Tracking |
|---|---|---|---|
| largeTitle | 34 / 41 | 700 | −0.022em |
| title1 | 28 / 34 | 700 | −0.020em |
| title2 | 22 / 28 | 700 | −0.016em |
| title3 | 20 / 25 | 600 | −0.012em |
| headline | 17 / 22 | 600 | −0.006em |
| body | 17 / 22 | 400 | 0 |
| callout | 16 / 21 | 400 | −0.003em |
| subhead | 15 / 20 | 400 | −0.002em |
| footnote | 13 / 18 | 400 | 0 |
| caption1 | 12 / 16 | 400 | 0 |
| caption2 | 11 / 13 | 500 | +0.006em |

Tracking tightens as size grows. Access via `theme().font("headline")`.

### Color
Defined as light/dark `Palette` pairs in `ui/theme/tokens.py`; resolved through
`theme().palette()`. Layered backgrounds (`bg_base`/`elevated`/`overlay`/
`sidebar`), four label levels (primary→quaternary), four translucent fills,
opaque + non-opaque separators, and semantic `success`/`warning`/`danger`/`info`
each with a subtle `_bg`. Dark is a true near-black (`#1C1C1E`), not inverted gray.
Accent is user-selectable from the eight system colors (blue default), stored in
the `ui.accent` setting.

### Materials
Sidebar and modal chrome use a translucent fill; on Windows 11 the window also
requests a **DWM Mica backdrop** and a theme-matched title bar
(`theme().apply_backdrop(window)`). Where unsupported, the solid `bg_sidebar_solid`
fallback carries the look. Cards use `bg_elevated` + a 1px non-opaque border + a
`QGraphicsDropShadowEffect` (dark mode drops shadow opacity, raises border
contrast) — Qt has no CSS `box-shadow`.

### Geometry
8pt grid (4·8·12·16·20·24·32·40·48·64). Radii: 4 chips · 8 controls · 12 cards ·
16 sheets · 20 modals · 999 pills. Control heights 28/32/40; touch targets ≥44.

### Motion
Standard spring `cubic-bezier(0.32, 0.72, 0, 1)`, evaluated exactly via
`QEasingCurve.setCustomType` (Qt lacks the enum). Durations 150 micro / 250
standard / 400 large — nothing over 500ms. `motion.animate()` honours OS
**reduced-motion** (`SPI_GETCLIENTAREAANIMATION`), collapsing to instant/opacity.

---

## Components

All 34 spec components ship, each theme-reactive (restyle on `themeChanged`):

Sidebar · Toolbar · SearchField · SegmentedControl · Button (primary/secondary/
tinted/plain/destructive) · TextField (inline validation) · Select · ChipInput ·
Toggle · Slider · Stepper · Checkbox · Radio · Chip/token · DataTable (sortable,
sticky header, virtualised) · Card · Sheet · Modal · Popover · Tooltip ·
context menu · Toast (+ ToastHost) · InlineBanner · ProgressBar · Spinner ·
Skeleton · EmptyState · ErrorState · TabBar · DisclosureGroup · Badge · Avatar ·
KeyboardHint (`⌘K`) · CommandPalette · ConfirmDialog.

Custom-painted components (Toggle, Checkbox, Radio, SegmentedControl, Spinner,
Skeleton, ProgressBar, Avatar) read tokens directly and repaint on theme change;
the rest regenerate a small per-widget stylesheet.

## Interaction
- Command palette on **⌘K / Ctrl+K**: navigate, toggle theme, open settings.
- Destructive actions route through `ConfirmDialog`; transient outcomes offer a
  toast (undo affordance).
- Every async surface has loading (Spinner/Skeleton), empty (EmptyState), error
  (ErrorState/InlineBanner), and success states — no blank screens.
- Focus is keyboard-navigable; the accent focus ring is `theme().focus_ring()`
  (accent at 40%).

## Honest Qt 5.15 deviations
These are the only places the platform can't do exactly what the CSS-oriented
spec describes; each has a working equivalent, noted so nothing reads as
silently missing:

- **`/design-system` route → screen** (Ctrl+Shift+D). Qt has no URL router.
- **Press-scale 0.97 → pressed-fill states.** QWidget has no transform; press
  feedback is the `:pressed` background treatment instead of a literal scale.
- **`tabular-nums` → right-aligned numeric columns.** Qt 5.15's QFont has no
  `font-feature-settings`; data tables/scores right-align and rely on the near-
  tabular figures of SF/Segoe/Inter. (A Qt 6 move would restore true tabular.)
- **`backdrop-filter` blur → DWM Mica** at the window level (Windows 11), with a
  solid fallback everywhere else.

## Integration status
The app boots on the new theme (`main.py` → `theme().apply(app)`); the design
system screen and command palette are wired in. The legacy setup/scan/results
screens adopt the new palette through a `ui/styles.py` compatibility bridge and
will be rebuilt directly on the component library in **Phase 10**, where they are
replaced by the dashboard and jobs views. New UI code imports from `ui.theme` and
`ui.components`, never from `ui.styles`.
