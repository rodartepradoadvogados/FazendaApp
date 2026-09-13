---
target: frontend/app/page.tsx
total_score: 27
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 2
target_identity: "file:C:\\Projetos\\CowData-Milk\\frontend\\app\\page.tsx"
target_fingerprint: "sha256:92ca8a0e5514cdff4f2e5c7476f0a9963916046bfce456c6082dc32b57c8fb3c"
target_path: "C:\\Projetos\\CowData-Milk\\frontend\\app\\page.tsx"
timestamp: 2026-09-12T19-41-52Z
slug: frontend-app-page-tsx
---
Method: dual-agent (A: design-review sub-agent · B: detector+browser sub-agent)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Bare "Carregando painel…" text on first load, no skeleton |
| 2 | Match System / Real World | 4 | Correct domain vocabulary (DEL, PEV, IATF, taxa de concepção) |
| 3 | User Control and Freedom | 3 | Modals close via X/overlay; no confirmed Esc handling; filters aren't persisted |
| 4 | Consistency and Standards | 3 | Token discipline strong, but "Descartados" modal reimplements AnimalModal inline |
| 5 | Error Prevention | 3 | Low-risk read surface; sensible date defaults |
| 6 | Recognition Rather Than Recall | 3 | Icon+label+hover-title pattern used consistently |
| 7 | Flexibility and Efficiency | 2 | No shortcuts, no saved filter/view, no export action |
| 8 | Aesthetic and Minimalist Design | 2 | Banner+alerts+8 KPIs+gauges+2 charts+benchmark+events all stacked with equal weight |
| 9 | Error Recovery | 2 | Generic "alguns dados não carregaram" banner, no per-section retry |
| 10 | Help and Documentation | 2 | No in-context help/tooltips beyond a few title attributes |
| **Total** | | **27/40** | **Acceptable** |

## Design Specificity Verdict

**LLM assessment**: No, this could not ship unchanged on an unrelated product — `DESIGN.md`'s named, enforced rules (Almost-Square, No-Lift, Gold-Is-Action, All-Caps Label) and a bespoke SVG speedometer gauge are load-bearing, not incidental. But specificity of *style* has outpaced specificity of *information architecture*: the layout is a flat grid of same-weight KPI cards, the same shape a generic admin dashboard would produce. The system knows what it looks like; it hasn't yet decided what it's for at 7am with 90 seconds of attention.

**Deterministic scan**: Static CLI scan of `page.tsx` and its 5 key components came back clean (exit 0, no findings) — the detector can't see resolved/painted styles from source alone. Live in-browser detection on the reachable surface today (the `/login` screen, since the backend is down and `/` redirects there) found **21 anti-patterns**: 3 undersized-text instances (10.4–11.5px), 2 low-contrast pairs (2.2:1 red-on-navy — well under the 4.5:1 floor — and 4.4:1 green-on-navy, just under), 2 excessive line-length paragraphs (~166 chars), a clipped-overflow container, a background image buried at 0.12 opacity, a thin-border-wide-shadow combo, 5 instances of a side-tab pattern, and 18 em-dashes flagged as possible overuse.

**Browser evidence**: Both sub-agents independently reached the live `/login` screen (the actual entry point today, since the backend on :8000 is down) and both independently found **8 unlabeled form fields** via console `[issue]` messages — a strong, corroborated signal, not a fluke. No broken images or obviously broken layout at a glance; the issues found are all sub-visual (contrast, type scale, clipping) rather than catastrophic.

Two detector flags may be intentional editorial choices rather than defects — flagging for your judgment rather than mine: **em-dash overuse (18)** is a very common construction in Brazilian Portuguese marketing copy, and the **166-char line length** may be a deliberate wide-hero-paragraph choice. I'm not resolving these myself; see the questions below.

## Overall Impression

This product has real design conviction — a genuinely custom identity ("The Institutional Ledger") enforced by named rules and a fixed 8-category color system reused everywhere, which is unusually disciplined for a project this size. But that conviction hasn't fully reached two places yet: the flagship dashboard still reads as a flat wall of same-weight KPI cards rather than a hierarchy that shouts "here's what needs you today," and the public gateway everyone passes through right now (login) has a real accessibility gap (P0) plus a cluster of small type/contrast issues that undercut the "reads like a bank statement" ambition. The single biggest opportunity: let the system's strength (bespoke components like the Gauge, the category-color language) organize the *information*, not just the *paint* — and let it earn one moment of restrained delight instead of zero.

## What's Working

- **`Gauge.tsx`** — a genuinely custom open-arc speedometer with target tick and needle, not a stock chart-library gauge. The one place the "instrument panel" ambition is fully realized.
- **Category-color system** (`.kpi-chip`, tinted via `color-mix`) — reused identically across KPI cards, badges, and (per `DESIGN.md`) the mobile app menu. Real cross-surface consistency, not just documentation.
- **Drill-down interactivity** — clicking a KPI or donut slice opens a filtered animal list (`AnimalModal`); the gold hover treatment on `.row-clickable` communicates the affordance well.

## Priority Issues

- **[P0] Login form fields lack accessible labels.** Confirmed independently by both assessments (8 instances via browser console `[issue]` messages) on the live `/login` screen — the actual entry point today. Screen-reader users cannot reliably identify Usuário/Senha and are blocked before ever reaching the product. **Fix:** wire `<label htmlFor>`/`aria-label` to every input on the login form. **Suggested command:** `$impeccable harden`.
- **[P1] Flat KPI hierarchy buries what's actionable.** 7-8 same-size, same-weight KPI cards give a financial loss, a critical stock alert, and a routine metric equal visual force; the real daily action list ("Próximos Eventos") sits at the very bottom of the page, below two charts and a full reproductive-efficiency module. **Fix:** promote a "today" module above the fold; demote the KPI grid to a visually quieter secondary row. **Suggested command:** `$impeccable distill` then `$impeccable bolder` on the promoted module.
- **[P1] Low-contrast text on the public login screen.** Two failing/near-failing pairs found live: `#c0392b` on `#14385a` at 2.2:1 (needs 4.5:1) and `#4caf80` on `#14385a` at 4.4:1 (just under). This is on the one screen every user — including the accountant and vet personas — must read correctly. **Fix:** darken/lighten to clear AA compliance; re-run detector to confirm. **Suggested command:** `$impeccable audit` then `$impeccable harden`.
- **[P2] Generic, non-actionable error state.** The `erroCarga` banner ("Alguns dados não puderam ser carregados") doesn't say which module failed or offer a per-card retry. **Fix:** per-section inline error + retry instead of one page-level banner. **Suggested command:** `$impeccable clarify`.
- **[P2] Zero motion anywhere, including on load.** Bare "Carregando painel…" text with no skeleton, despite the product's own stated rural-connectivity constraints (loading states are a real, frequent scenario, not an edge case). Plus a small cluster of live-detector findings on the public page (undersized 10–11.5px footnote text, a clipped-overflow container, a background image buried at 0.12 opacity, a thin-border-wide-shadow combo, a repeated side-tab pattern in 5 places) that read as unintentional rough edges rather than deliberate choices. **Fix:** KPI/chart-shaped skeleton loaders; fix the type/contrast/clipping cluster. **Suggested commands:** `$impeccable animate` (loading), `$impeccable layout` + `$impeccable typeset` (the cluster).
- **[P3] No delight or trend signal on KPI cards.** Every value is a bare number — no sparkline, no up/down arrow versus last period, nothing that rewards a herd that's actually doing well. **Fix:** add trend deltas and one restrained positive-state treatment that stays inside the Institutional identity (no gradient, no lift — color/glyph only). **Suggested command:** `$impeccable delight`.

## Persona Red Flags

**Alex (Power User)**: Must visually scan all 7-8 equal-weight KPIs to find what's urgent; the reload button only triggers a full-page refetch, no per-card refresh; the benchmark-vs-goal comparison — arguably the first thing a power user wants — is hidden behind a collapsed toggle by default.

**Sam (Accessibility-Dependent)**: Confirmed unlabeled login inputs block entry entirely. The reproductive donut chart's drill-down (`Pie onClick`) is mouse-only with no keyboard equivalent — a whole interaction path is unreachable. Category pill toggles signal active state via color/border alone, no `aria-pressed`.

**Farm Owner (limited morning window — project-specific persona)**: Actionable alerts (implant shortage, bills due, low stock) render as the same low-contrast pill weight as purely informational badges — nothing escalates visually by real urgency. The one list that answers "what do I do today" (`Próximos Eventos`) is the very last thing on the page.

## Minor Observations

- "Descartados" modal duplicates `AnimalModal`'s structure inline instead of reusing the component — a consistency/drift risk (heuristic #4).
- Skull icon for discarded-animal count feels tonally harsh sitting inside the main KPI grid.
- A native `<input type="date">` embedded inside a KPI card breaks the card's "number-first" reading pattern used everywhere else.
- The vaca/novilha category toggle is rendered twice (gauges card + reproductive-status card) for one shared piece of state — redundant.
- A negative financial result only escalates to amber, the same color used for merely "needs attention" elsewhere — under-signals an actual loss.
- Public page: 18 em-dashes and ~166-char line length flagged by the detector — likely intentional editorial voice, needs your call (see questions).

## Questions to Consider

1. If the owner has 90 seconds between chores, which 3 numbers must dominate — and are they visually distinct from the other 15+ data points today, or all the same size?
2. Does "reads like a bank statement" have to mean zero delight, or can one moment (a goal met, a healthy herd) earn a single restrained flourish without breaking the Institutional identity?
3. Is the reproductive gauges/benchmark/donut module this large because it's the daily decision the owner actually needs, or because it was the easiest section to build out first?
