---
target: frontend/app/contador/page.tsx
total_score: 22
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 1
target_identity: "file:C:\\Projetos\\CowData-Milk\\frontend\\app\\contador\\page.tsx"
target_fingerprint: "sha256:89569c6d3e50e24437d5c16d646311efa36af75c9b7bd4f56edcc2be0265f04c"
target_path: "C:\\Projetos\\CowData-Milk\\frontend\\app\\contador\\page.tsx"
timestamp: 2026-09-12T22-57-35Z
slug: frontend-app-contador-page-tsx
---
Method: dual-agent (A: design-review sub-agent · B: detector+browser sub-agent)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Loading/error states exist, but all 9 tabs' data is fetched in one `Promise.all` before any tab renders — no per-tab loading state |
| 2 | Match System / Real World | 1 | "RMCA," "GTA," "Plano de contas" fed straight to an external accountant with zero glossary — RMCA is a dairy-specific ratio, not standard accounting vocabulary |
| 3 | User Control and Freedom | 2 | No breadcrumbs beyond a hidden-for-accountants "Voltar à fazenda"; no per-tab reset; date filter has no quick reset |
| 4 | Consistency and Standards | 3 | Internally consistent own identity, but the tab-strip/KPI-card/table pattern is identical to every other CowData screen — undermines the "feels different" goal structurally |
| 5 | Error Prevention | 2 | No visible date-range validation; the extraordinary-actions lock (`useCadeado`) is a genuine strength here |
| 6 | Recognition Rather Than Recall | 2 | Nine terse tabs, no icons distinguishing "read" tabs from the one "write" tab — user must infer or remember |
| 7 | Flexibility and Efficiency | 2 | Column sort exists; no saved filters or "last tab visited"; the one-click monthly Excel export is a real efficiency win |
| 8 | Aesthetic and Minimalist Design | 3 | Dense but disciplined; loses a point for identical visual weight given to all 9 tabs regardless of relevance |
| 9 | Error Recovery | 2 | Raw exception string shown (`Não foi possível carregar os dados financeiros: {erro}`) — fine for a technical user, cold for a periodic non-technical visitor |
| 10 | Help and Documentation | 0 | Zero onboarding, zero tooltips defining DRE/RMCA/GTA/"Plano de contas" — no "what am I looking at" primer anywhere |
| **Total** | | **22/40** | **Acceptable** |

## Design Specificity Verdict

**LLM assessment**: This could not ship unchanged as a generic accountant portal — the team deliberately built a *third* distinct identity here (graphite/slate background, serif ledger-book display font, double-hairline header, muted steel-blue), explicitly commented in code as "never look like just another farm screen." That's real craft and real specificity of tone. But the content underneath — nine flat tabs, a global date-range filter, KPI tiles, sortable tables, one Excel export — is exactly the generic shape any small-business accountant portal would have. The specificity is skin-deep: a distinctive costume on an entirely conventional, undifferentiated body. Nothing in the layout or IA reflects that the visitor is a rare, external, non-farm professional — it reads as a shrunk owner-dashboard with different paint.

**Deterministic scan**: Static CLI scan of both files in this route (`page.tsx`, `layout.tsx`) came back completely clean.

**Browser evidence**: The authenticated `/contador` view could not be reached live (same backend-down redirect to `/login` seen throughout this roadmap) — no new markup to add live-detector evidence for, so this run relies on source reading, which surfaced the real findings below (all living in IA/copy/interaction, not in markup patterns a scanner targets).

## Overall Impression

This is a tool built for the right instinct (an external, infrequent, financially-serious visitor deserves its own identity) that stops at the surface. A moody, disciplined palette and a serif ledger title signal "this is different and serious," but the actual structure — nine equal-weight tabs including dairy-specific jargon like RMCA and GTA, with zero explanation — hands a rare external accountant the exact same cognitive task as a daily power user, with none of the context a daily user has built up. Biggest opportunity: let the visual seriousness be matched by informational orientation — a first-and-only-visit user needs a primer this screen currently doesn't offer at all.

## What's Working

- **`useCadeado` lock gating "Ações extraordinárias"** — a genuinely well-considered guardrail: the one tab that can write/change data is deliberately harder to reach, exactly the right instinct for an external, infrequent user.
- **Distinct visual identity** (serif ledger title, graphite palette, double-rule header) — a real design decision, not a reused shell; it does communicate "different context" at a glance.
- **One-click monthly close export** bundling DRE/Extrato/Patrimônio/Folha into a single Excel file — directly serves this persona's actual job (pull documents and leave) better than most of the surrounding UI.

## Priority Issues

- **[P0] No orientation or glossary for a first-and-only-visit user.** Landing directly on 9 unexplained tabs (including jargon like RMCA/GTA) with no primer is the single biggest mismatch between this screen and its actual persona — someone who logs in a couple of times a year and has zero farm context. **Fix:** a one-line contextual header per tab explaining what it is and where the number comes from. **Suggested command:** `$impeccable onboard`.
- **[P1] Flat, undifferentiated tab bar mixes read tabs with the one write tab.** "Ações extraordinárias" sits visually identical to "DRE" in the same row; only an internal lock (not visible from the tab itself) signals it's different. **Fix:** visually separate/group the write-capable tab from the eight read/export tabs (icon, divider, or distinct color). **Suggested command:** `$impeccable layout`.
- **[P2] Raw error messages and terse empty states for a non-technical periodic user.** The raw exception string is rendered directly; several tabs' zero-state is a single terse row. **Fix:** friendlier copy that also suggests a likely cause (e.g., "tente ampliar o intervalo de datas"). **Suggested command:** `$impeccable clarify`.
- **[P3] Farm jargon leaks untranslated for a professional serving multiple non-farm clients.** RMCA especially has no accounting-standard equivalent and no tooltip. **Fix:** an info-icon glossary on RMCA, GTA, and "Plano de contas" labels. **Suggested command:** `$impeccable document`.

## Persona Red Flags

**Jordan (first-timer — this IS this persona's only screen)**: Lands on 9 tabs with zero framing; "RMCA," "GTA," and "Plano de contas" are opaque terms with no explanation on the very first screen this persona will ever see.

**Sam (accessibility)**: Interactive elements built with inline styles and hardcoded hex colors; no visible focus-state audit; contrast of the muted label color on the panel background is borderline for WCAG AA at small label sizes.

**External accountant serving several farm clients (project-specific persona)**: This user has zero patience for single-farm jargon or a support call to understand a screen — RMCA, GTA, and "centro de custo" filters demand exactly the farm-specific fluency this persona was never expected to have.

## Minor Observations

- Date-range picker has no visible min/max validation or "invalid range" guard.
- The attachment popover on line-item documents has no click-outside-to-close handler.
- Real accountants get no equivalent "what do I do when I'm done" affordance beyond "Sair" (the "Voltar à fazenda" link only shows for owners peeking in, which is correct but leaves this persona without a clear exit ritual).

## Questions to Consider

1. If this accountant serves five farm clients, does each one hand them a differently-jargoned, differently-organized version of this same screen — has anyone asked an actual accountant how that feels?
2. Why does "Ações extraordinárias" get a password lock but no visual distinction in the tab bar itself — is the lock compensating for an IA decision that should have separated it in the first place?
3. Is RMCA meaningful to anyone who isn't already a CowData power user — if not, why is it a top-level tab rather than a line inside DRE with a footnote?
4. Was any actual accountant interviewed before treating a flat 9-tab dashboard as sufficient IA for a 15-minutes-twice-a-year visitor?
