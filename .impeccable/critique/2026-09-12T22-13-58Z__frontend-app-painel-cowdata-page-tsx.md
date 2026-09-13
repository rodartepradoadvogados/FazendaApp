---
target: frontend/app/painel-cowdata/page.tsx
total_score: 25
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 1
target_identity: "file:C:\\Projetos\\CowData-Milk\\frontend\\app\\painel-cowdata\\page.tsx"
target_fingerprint: "sha256:3be00e3c8d2cd378716797796a16b199a40e322e2b94b671bf7b3819c0ff8872"
target_path: "C:\\Projetos\\CowData-Milk\\frontend\\app\\painel-cowdata\\page.tsx"
timestamp: 2026-09-12T22-13-58Z
slug: frontend-app-painel-cowdata-page-tsx
---
Method: dual-agent (A: design-review sub-agent · B: detector+browser sub-agent)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Loading/empty states present; approve/suspend gives no success toast, only silent table reload |
| 2 | Match System / Real World | 4 | MRR, DRE, Fluxo de Caixa, contract language correct for a BR SaaS operator |
| 3 | User Control and Freedom | 2 | Suspending a paying customer's contract is one click, zero confirmation, no undo |
| 4 | Consistency and Standards | 2 | Usuários/Parâmetros hardcode 10px/8px radii while every sibling page uses the 2px Institutional token |
| 5 | Error Prevention | 2 | No confirm step before suspend/approve — the two highest-stakes actions on this surface |
| 6 | Recognition Rather Than Recall | 3 | Sidebar grouping + active-state border is clear |
| 7 | Flexibility and Efficiency | 2 | No filter/search on Fazendas or Assinaturas, no bulk approve — won't scale past a handful of farms |
| 8 | Aesthetic and Minimalist Design | 3 | Dense but readable, not cluttered |
| 9 | Error Recovery | 2 | Errors surface as raw `e.message`, no guidance or retry |
| 10 | Help and Documentation | 2 | Confiança/LGPD page is genuinely good docs, but isolated — no contextual help elsewhere |
| **Total** | | **25/40** | **Acceptable** |

## Design Specificity Verdict

**LLM assessment**: This cockpit correctly runs its own dark slate-blue palette, isolated from the farm product's marinho/category colors — the right instinct, since an operator shouldn't stare at Reprodutivo-purple KPI tiles. But having earned that separation, it does almost nothing distinctive with it: strip the CowData wordmark and this is indistinguishable from any Stripe-clone admin (KPI-tile row → tabbed table → form-in-a-card). It could ship unchanged as the back office for a food-delivery app or a gym-membership SaaS.

**Deterministic scan**: Static CLI scan across all 15 files under `painel-cowdata/` came back completely clean (exit 0, zero findings both runs) — no mechanical anti-patterns detected.

**Browser evidence**: The authenticated cockpit could not be reached live (backend down redirects to `/login`, the same screen already inspected in the página pública critique) — so this run leans on source reading, which surfaced real findings a static scanner can't catch (hardcoded radii, missing confirmation dialogs, gold-token misuse) that live purely in application logic and inline styles, not markup patterns the detector's rule set targets.

## Overall Impression

The cockpit gets the big call right — its own visual identity, separate from the farm product — but stops short of using that freedom to build what this surface actually needs: an ops queue that surfaces "who needs me today," with friction proportional to the stakes of each action. Right now approving or suspending a paying customer's access is exactly as casual as sorting a column, and the one visually disciplined system in the codebase (2px Institutional radii, gold reserved for confirm-actions) quietly drifts within this very panel. Biggest opportunity: turn the stats wall into a queue, and put real friction in front of the two actions that can hurt a paying customer.

## What's Working

- **Own, correctly isolated palette** (`painelCowDataTema.tsx`) — the code comments show a prior "white-text-on-white-card" bug from theme leakage was already caught and fixed, and the isolation holds.
- **Confiança / LGPD page** — real contractual language (titularidade, operator/controller role, portability), not placeholder text. The one screen that feels bespoke to a SaaS-ops audience.
- **Suporte's audit/session model** — timed sessions, protocol numbers, blocked-vs-allowed action logging is a genuinely well-thought-out trust mechanism for pilot-stage software.

## Priority Issues

- **[P0] No confirmation on contract suspend/approve.** The single highest-consequence click in the entire surface (cuts a paying customer's access) currently has *less* friction than deleting a manual ledger entry, which does get a `confirm()`. **Fix:** confirmation modal naming the specific farm before suspend fires; a brief inline success state after approve. **Suggested command:** `$impeccable harden`.
- **[P1] Cockpit and Assinaturas are a stats wall, not a queue.** The "Aguardando aprovação" KPI tile turns gold if >0 but links nowhere; the Assinaturas table isn't sorted by urgency — the founder must eyeball every row to find who needs action. **Fix:** default-sort Assinaturas by status (pending first); make the Cockpit's pending tile a direct link to that filtered view. **Suggested command:** `$impeccable layout`.
- **[P2] In-panel corner-radius drift.** `usuarios/page.tsx` and `parametros/page.tsx` hardcode `10px`/`8px` while every sibling page in the same folder uses the 2px Institutional token — a copy-paste inconsistency inside the one surface meant to be visually disciplined. **Fix:** replace hardcoded radii with `var(--r-sm)`. **Suggested command:** `$impeccable audit`.
- **[P3] Gold used as a generic accent, not "confirm only."** DESIGN.md's Gold-Is-Action Rule is violated throughout — gold marks active tabs, active nav, KPI numbers, and plain links, diluting its meaning as "this commits something." **Fix:** reserve gold for Aprovar/Salvar buttons only; give active-tab/nav state a neutral highlight. **Suggested command:** `$impeccable colorize`.

## Persona Red Flags

**Alex (Power User)**: No search/filter on Fazendas or Assinaturas, no bulk-approve — beyond a handful of farm-customers, stuck scrolling and eyeballing every row.

**Sam (Accessibility)**: Contract status leans on color alone (green/gold/red text, no icon+text redundancy in Assinaturas, unlike Suporte's status dot+label pairing) — a colorblind operator can't reliably distinguish "Ativo" from "Suspenso."

**Founder doing platform support (project-specific persona)**: "Who needs me today" has no home — no unified queue across pending contracts, pending support requests, and pending parameter rollouts; must check Cockpit, then Assinaturas, then Suporte separately every session.

## Minor Observations

- Raw `e.message` from the API shown directly to the user — will occasionally leak backend-internal phrasing.
- The Cockpit's "Atalhos" card duplicates links already in the sidebar with no added value.
- Suporte auto-polls every 30s with no visible "last updated" timestamp — staleness at second 29 is invisible.

## Questions to Consider

1. If this cockpit is meant to scale to "dozens of farms eventually," why does nothing on it support search, filter, or bulk action today?
2. Is gold currently CowData's brand color or just "the panel's accent" — right now it's doing both jobs badly.
3. Would the founder actually trust a click-to-suspend button with no confirmation on a live paying customer, or has nobody stress-tested this yet?
4. Why does the LGPD/Confiança page get real bespoke content while the higher-frequency Assinaturas/Fazendas screens get generic table chrome?
