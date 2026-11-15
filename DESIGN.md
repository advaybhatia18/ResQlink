# ResQlink Design System (`DESIGN.md`)

ResQlink follows an **Operate** visual mode: high-contrast dark surfaces (`#070d17` / `#0a111c`) with crisp semantic accents designed for stressful emergency reporting and rapid responder scanning.

## Core Tokens (`theme.css`)
- **Surfaces:** `--rq-bg: #070d17`, `--rq-surface: #0f172a`, `--rq-surface-2: #162238`, `--rq-border: rgba(148, 163, 184, 0.22)`
- **Typography:** System sans stack (`Inter, system-ui, -apple-system, sans-serif`) for UI copy; `ui-monospace` for `RQ-YYYYMMDD-XXXXXX` alert IDs, coordinates, and live session timers.
- **Semantic Status & Severity Colors:**
  - Critical / Severity 5 / SOS Danger: `#ff4d6d`
  - High / Warning / Severity 3–4: `#ffbf69` / `#fb923c`
  - Moderate / Info / Dispatched: `#548aff`
  - Resolved / Verified / Low: `#38dfac`

## Accessibility & Interaction Rules
- **Safe DOM Updates:** Never use `innerHTML` with dynamic API data; always use `textContent` and `ResqlinkUI.el(...)`.
- **Modals:** Support `Escape` to close, focus trapping inside the open modal, and focus restoration to the triggering control on close.
- **Touch & Mobile Ergonomics:** Minimum 44px tap targets on primary SOS and session controls; responsive single-column collapse below `640px`.
