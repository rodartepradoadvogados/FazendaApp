---
target: frontend/app/login/page.tsx
total_score: 20
max_score: 32
na_heuristics: 7,10
p0_count: 2
p1_count: 2
target_identity: "file:C:\\Projetos\\CowData-Milk\\frontend\\app\\login\\page.tsx"
target_fingerprint: "sha256:2a953048752f865f8e73a5bfeb5a49336638059095c47b160bacdf151adad2e9"
target_path: "C:\\Projetos\\CowData-Milk\\frontend\\app\\login\\page.tsx"
timestamp: 2026-09-12T21-17-55Z
slug: frontend-app-login-page-tsx
---
Method: dual-agent (A: design-review sub-agent · B: detector+browser sub-agent)

## Design Health Score (mode: Persuade — heuristics 7 and 10 scored n/a)

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Spinners, carousel dots, inline errors present |
| 2 | Match System / Real World | 3 | Domain terms (IATF, CCS, CBT) used correctly, if unglossed for a newcomer |
| 3 | User Control and Freedom | 3 | Modal close, back-nav in multi-farm and forgot-password flows |
| 4 | Consistency and Standards | 1 | Feature/banner cards lift (`translateY`) + gain shadow on hover — violates the page's own documented No-Lift Rule; login card's heavy shadow ignores the single-`--shadow-sm` system |
| 5 | Error Prevention | 2 | Simulator numeric inputs have no min/max — negative CCS/protein or zero volume produce nonsensical output silently |
| 6 | Recognition Rather Than Recall | 3 | Clear nav labels, icon+text pairing throughout |
| 7 | Flexibility and Efficiency | n/a | Not a power-user surface (Persuade mode) |
| 8 | Aesthetic and Minimalist Design | 2 | Four dense, similarly-weighted sections stacked with no breathing room; login card's heavy shadow fights the flat "ledger" aesthetic |
| 9 | Error Recovery | 3 | Forgot-password flow gives specific, actionable recovery copy |
| 10 | Help and Documentation | n/a | Milk News blog is adjacent content marketing, not in-page help |
| **Total** | | **20/32 (63%)** | **Acceptable** |

## Design Specificity Verdict

**LLM assessment**: Strip the icon labels and this hero could sell any B2B SaaS — dark navy gradient, auto-rotating carousel, a login card with a heavy drop-shadow, a generic six-icon feature grid. The rotating headlines ("A fazenda inteira, num único painel de decisão") are interchangeable ERP value props. The one thing genuinely unique about this product — a rules engine encoding breed-specific gestation (280/287/295 days), IATF D0/D7/D9/D11, dry-off, BST eligibility — never appears in the hero. It only surfaces, diluted, as a bullet inside the "Reprodução" feature-card body copy.

**Deterministic scan**: Static CLI scan of `page.tsx` and the banner/feature components came back clean except one real hit: a `side-tab` (thick left-border accent) at `MilkPriceExplainer.tsx:287` — the detector's own description calls this "the most recognizable tell of AI-generated UIs." Live in-browser detection found **23 anti-patterns**, including the same low-contrast green (4.4:1) found in the earlier run, undersized footnote text (10.4-11.5px), a background image at 0.12 opacity, a clipped-overflow container, 5 paragraphs whose geometry bleeds past the viewport edge (not visible in the captured screenshot — a state/width-dependent issue worth checking at other viewport sizes), the `side-tab` pattern appearing **5 times at runtime** (one per numbered explainer card, vs. 1 source location statically), a thin-border+wide-shadow combo, and 18 em-dashes (possibly intentional PT-BR voice).

**Browser evidence**: Confirmed live — same 8 unlabeled-field console issues as the first critique run (2 in the login card, 6 in the milk-price simulator). Notably, this run's live detector did **not** re-surface the red-on-navy contrast failure (`#C0392B` on `#14385A`, 2.2:1) found earlier — because the simulator's default values (CCS 300, CBT 80, gordura 3.4%, proteína 3.2%) all compute to *positive* adjustments today, so the red-text path only renders when a farm's real numbers produce a negative adjustment. The bug is real and computed (2.2:1, confirmed math) but state-dependent — exactly the kind of thing that passes casual QA and then embarrasses the product in front of a real customer.

## Overall Impression

The page reads as reasonably premium at a glance — dark navy/gold, a real farm photo, consistent category colors — but two things undercut it hard: it sells itself as "a dashboard with six modules" instead of the one thing that's actually defensible (a rules engine that knows a Girolando gestates in 287 days, a vet can trust), and the two components most likely to form a first-time visitor's opinion (the feature cards) directly break the product's own documented design law (No-Lift). The biggest opportunity: put the differentiator in the actual headline, and enforce the design system on the marketing surface as strictly as internal-only screens.

## What's Working

- **The milk-price "de onde vem o ajuste" breakdown** — showing line-item adjustments (CCS/CBT/gordura/proteína) instead of a single black-box number is a genuinely good trust mechanic, rare in farm-software marketing.
- **Category color consistency** — feature-card icon colors reuse the exact same 8 fixed hues as the internal app, a real (if subtle) through-line between the pitch and the product.
- **Forgot-password flow copy** — specific and humane (masked email, explicit admin fallback) rather than a generic toast.

## Priority Issues

- **[P0] 8 form fields have visually-present labels with no `htmlFor`/`id` association.** Same root cause as the dashboard's login-gate finding, in different files: 2 in the login card (`app/login/page.tsx`), 6 in the milk-price simulator (`components/login/MilkPriceExplainer.tsx`). A skeptical buyer's own IT-literate staff would flag this immediately; it's also a real accessibility-law exposure for paid SaaS. **Fix:** wire matching `id`/`htmlFor` on all 8. **Suggested command:** `$impeccable harden`.
- **[P0] The hero never states the actual differentiator.** Everything in `PRODUCT.md` says the product's real edge is a rules engine (gestation-by-breed, IATF protocol, BST eligibility), not a generic dashboard — none of that reaches the fold. **Fix:** rewrite at least one carousel slide to name the mechanism explicitly. **Suggested command:** `$impeccable distill`.
- **[P1] FeatureShowcase and BannerGrid cards lift and gain shadow on hover.** This directly violates the documented No-Lift Rule, on the two components a first-time visitor sees first — the marketing page is less disciplined than the internal app it's selling. **Fix:** drop the `translateY`/elevated shadow, keep only a border-color hover. **Suggested command:** `$impeccable harden`.
- **[P1] Intermittent, state-dependent contrast failure.** `#C0392B` on `#14385A` (2.2:1) and `#4CAF80` on the same background (4.4:1) both fail AA; the red only renders when the simulator computes a negative adjustment, so it's easy to miss in a quick look. **Fix:** same calibrated pair proposed for the dashboard (`#FF8A80` / `#6BC79A`), reused here since it's the identical token/background combination. **Suggested command:** `$impeccable colorize`.
- **[P2] No trust/proof layer anywhere on the page.** No pricing, testimonial, or contact beyond a one-line footer — yet a genuinely provable, specific claim ("27+ automated business-rule tests," real Fazenda Estreito data) sits unused in the repo. **Fix:** add one concrete proof line near the fold or in the footer. **Suggested command:** `$impeccable layout`.
- **[P2] "Todos os temas do sistema" grid leaves 3 empty column slots in its last row** (8 cards in a 4-column grid) — a real, visible layout gap, not a detector artifact. **Fix:** reflow to a column count the item total fills evenly, or let the last row center/span. **Suggested command:** `$impeccable layout`.
- **[P2] Milk-price simulator has no input validation.** No min/max on any of the 6 numeric fields — negative CCS or zero volume silently produces a nonsensical "ajuste," undermining the very credibility the simulator exists to build. **Fix:** clamp to plausible domain ranges, disable/hide output on invalid input. **Suggested command:** `$impeccable harden`.
- **[P3] "side-tab" left-border accent repeated on 5 explainer cards** — the detector's own category for this rule is literally "AI-generated-UI tell." **Fix:** replace with a subtler accent (a colored dot, a number badge) instead of a solid left border. **Suggested command:** `$impeccable polish`.

## Persona Red Flags

**Jordan (confused first-timer):** Lands on a dark hero where a gold-outlined login form dominates the fold — a plausible first read is "wrong page, this is for existing customers," not realizing scrolling reveals the sales pitch at all.

**Riley (stress-tester):** Enters negative/zero values into the milk simulator (no `min` attribute) and gets a silently wrong "ajuste" with no validation message; tabbing through the login form hits the unlabeled-field gap directly.

**Casey (distracted mobile):** At phone width, the login form sits below the full headline+carousel+dots stack — a returning user (the majority of daily traffic) has to scroll past marketing copy to reach the one thing they came for.

**Dono de fazenda cético (persona específica do produto):** The first 10 seconds show generic dashboard copy, no pricing, no proof; the one specific, checkable claim (the rules engine) is buried two-plus scrolls down — nothing on the first screen distinguishes this from "yet another farm app."

## Minor Observations

- Carousel arrow touch targets (~34px) sit under the 44px mobile guideline.
- Milk News callout uses the `--vinho` (wine) gradient token but renders navy under the currently-active palette — a token/intent mismatch worth a quick audit.
- 5 body paragraphs geometrically bleed past the viewport edge per the live detector (not visible in the captured screenshot — likely width/state-dependent; worth checking at other breakpoints).
- Footnote/citation text renders at 10.4-11.5px, below a comfortably legible floor.
- A background image renders at 0.12 opacity — functionally invisible; worth confirming it's intentional watermarking and not a broken asset.

## Questions to Consider

1. If the rules engine is the real product, why does a visitor have to scroll past a login form, a carousel, and a feature grid before any copy names it?
2. Is the milk-price calculator building trust, or does its stacked disclaimer copy quietly tell visitors "don't trust the numbers on this page"?
3. Why is the No-Lift Rule enforced everywhere except the two components a first-time buyer sees first?
4. Where does a convinced-but-not-ready prospect click next — is there any call to action on this page besides "log in"?
