---
target: frontend/app/news/page.tsx
total_score: 17
max_score: 32
na_heuristics: 5,10
p0_count: 1
p1_count: 1
target_identity: "file:C:\\Projetos\\CowData-Milk\\frontend\\app\\news\\page.tsx"
target_fingerprint: "sha256:d469bb4207b2ad1be0c82a5c8b5966411c630ba22d52100adcfe727e9f4a449f"
target_path: "C:\\Projetos\\CowData-Milk\\frontend\\app\\news\\page.tsx"
timestamp: 2026-09-12T22-40-26Z
slug: frontend-app-news-page-tsx
---
Method: dual-agent (A: design-review sub-agent · B: detector+browser sub-agent)

## Design Health Score (mode: Read — heuristics 5 and 10 scored n/a)

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | Loading + error states exist, but no per-article skeleton; error surfaces a raw JS exception |
| 2 | Match System / Real World | 3 | Domain language, pt-BR dates, dairy taxonomy read naturally |
| 3 | User Control and Freedom | 1 | No back-out-able navigation because there's nowhere to navigate *to* (no article route exists) |
| 4 | Consistency and Standards | 2 | Reuses dashboard card/badge conventions for content that isn't dashboard data; category colors reused with meanings that contradict DESIGN.md's fixed-category rule |
| 5 | Error Prevention | n/a | Read-only surface, nothing destructive to prevent |
| 6 | Recognition Rather Than Recall | 3 | Auto-derived section grouping and "última semana" toggle reduce recall burden |
| 7 | Flexibility and Efficiency | 2 | One filter toggle exists; no search, tags, or RSS |
| 8 | Aesthetic and Minimalist Design | 3 | Visually clean and calm; undermined by flat hierarchy (every headline same weight regardless of importance) |
| 9 | Error Recovery | 1 | "Failed to fetch" shown verbatim to an anonymous public visitor |
| 10 | Help and Documentation | n/a | Not applicable to a marketing blog |
| **Total** | | **17/32 (53%)** | **Acceptable** |

## Design Specificity Verdict

**LLM assessment**: This could ship unchanged as the marketing blog for almost any B2B SaaS — a generic photo-card grid + line-clamp excerpt + read-more template, tinted institutional blue. Worse, it actively breaks from the North Star rather than extending it for reading: the rest of the product is Barlow Condensed, all-caps labels, near-square 2px corners; Milk News switches to Sora and `rounded-xl`/`rounded-2xl` cards (12-16px — exactly the radius DESIGN.md documents as "tried and reverted" elsewhere). That's a defensible reading-mode exception in principle, but nothing was built in its place: no masthead, no byline, no article template. It reads as "dashboard cards with photos and no data," not "the Ledger adapted for reading."

**Deterministic scan**: Static CLI scan of `page.tsx` and `NewsShell.tsx` came back clean. Live in-browser detection found exactly **1 anti-pattern**: `call-caps-body` (uppercase text-transform on 32 characters of body text — the "FONTES QUE ACOMPANHAMOS TODO DIA" label) — a much lighter mechanical footprint than the other surfaces reviewed so far, though the design-specificity and structural issues below are the real story on this page.

**Browser evidence**: Confirmed live — `/news` is genuinely public (no login redirect), and rendered an honest error state ("Não foi possível carregar as notícias: Failed to fetch.") rather than a blank screen, with the static "Fontes" sources card rendering fine independent of the API. Critically, both assessments independently confirmed **no article-detail route exists anywhere in the codebase** (`frontend/app/news/` contains only `page.tsx`) — headlines are not links, and only the single featured story gets an in-place excerpt expansion.

## Overall Impression

The most consequential finding on this surface isn't visual — it's structural: there is no destination for a reader to actually read an article. Everything else (typography exception, card chrome, category-color reuse) is worth fixing, but none of it matters until the page has something to link to. The one genuinely good instinct here — a public, no-login "Fontes que acompanhamos" transparency card — shows the team knows how to build credibility; that same instinct hasn't yet reached authorship, permalinks, or a real reading layout.

## What's Working

- **Honest, non-blank error state** — shows a real message and keeps the sources card usable rather than white-screening entirely.
- **Shared image-fallback system** (`lib/newsVisual.ts`) — sensible logic keeping admin and public views visually consistent.
- **"Fontes que acompanhamos todo dia" card** — a genuinely good, on-brand credibility gesture, rare for a content-marketing blog to surface this transparently and upfront.

## Priority Issues

- **[P0] There is no article page.** `frontend/app/news/` contains only `page.tsx` — no `[slug]`/`[id]` route exists. Headlines aren't links; only the single featured story gets a same-page excerpt toggle; every other article is a dead end beyond a 2-line clamp. This makes the entire surface non-shareable, non-linkable, non-indexable, and directly fails its own stated job. **Fix:** build a real article route with full body, sources, date, and a reading layout; make every headline a link. **Suggested command:** `$impeccable layout`.
- **[P1] No byline or authorship signal anywhere.** Nothing public identifies who wrote or vetted a piece, despite copy implying original authorship. For a journalist or industry professional deciding whether to cite this, that's disqualifying. **Fix:** add a visible masthead/byline line; surface existing internal review attribution publicly. **Suggested command:** `$impeccable clarify`.
- **[P2] Raw exception text shown to anonymous visitors.** The literal fetch error is rendered verbatim to a public, zero-context visitor — technical and unfriendly, breaking the institutional-credibility register. **Fix:** friendly copy + retry CTA, hide the raw message behind an optional details toggle. **Suggested command:** `$impeccable polish`.
- **[P2] Category colors reused with contradictory meaning.** Section colors repurpose the fixed brand category tokens (`cat-financeiro`, `cat-sanidade`, `cat-gestao`) for unrelated blog-section meanings ("Regulação," "Manejo e clima") — directly contradicts DESIGN.md's own fixed-category rule. **Fix:** give Milk News its own section-color set, distinct from the product's 8 fixed category colors. **Suggested command:** `$impeccable audit`.
- **[P3] Reading comfort was never designed for, only card chrome.** The one place prose appears (the featured excerpt) sits in a narrow column at small size next to a photo — not a reading measure. **Fix:** once the article page exists, give it a true reading column (~65-75ch, larger body size, generous line-height), separate from any card metaphor. **Suggested command:** `$impeccable typeset`.

## Persona Red Flags

**Jordan (first-timer)**: Clicks any non-featured headline expecting an article — nothing happens, with no hover affordance change to warn them it's a dead click.

**Riley (stress-tester)**: No expand path for long body text outside the single featured slot; the empty state ("Nenhuma matéria publicada ainda.") is bare text, violating DESIGN.md's own empty-state rule; broken source links have no fallback handling.

**Casey (mobile)**: Confirmed live — before any CowData content, mobile visitors scroll past a full-width stack of 7 outbound links to competitor/industry publications (Cepea, MilkPoint, DairyReporter…) above the actual news feed.

**Industry professional/journalist (project-specific persona)**: No byline, no per-article URL, no schema/meta; un-illustrated pieces fall back to generic dashboard-marketing photography — nothing here reads as safe to cite or link to.

## Minor Observations

- Header logo links to `/login` even on this no-login public surface — a mixed signal for an anonymous reader.
- Sora typography is used here as a one-off substitution, not documented as a deliberate long-form reading system.
- The "Fontes" label's all-caps treatment is the one live-detector finding (`call-caps-body`) — minor, but worth checking against the same rule elsewhere.

## Questions to Consider

1. If a farmer forwards a Milk News link to another farmer, what URL do they actually send — and where does it currently go?
2. Who is the author of these articles, and why is the reader never allowed to know?
3. Is the goal here SEO/content marketing, or internal filler for a dashboard sidebar with a public URL bolted on — because the current build reads like the latter?
4. Would this page survive being read by an actual dairy-trade journalist deciding whether to cite it?
