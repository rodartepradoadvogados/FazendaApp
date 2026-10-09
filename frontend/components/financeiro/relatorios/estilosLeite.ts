// Estilos a mais das telas Leite e Registros (Fase C2) — só tokens, mesmo
// vocabulário do molde (estilos.ts). Arquivo próprio para não disputar
// estilos.ts com as outras telas da Fase C.
export const CSS_LEITE_REGISTROS = `
.rl-hint{margin:.55rem 0 0;font-size:.78rem;line-height:1.5;color:var(--text-muted);max-width:75ch}
.rl .lk,.rl-hint .lk{all:unset;cursor:pointer;color:var(--text-accent);font-weight:600;text-decoration:underline;text-underline-offset:3px}
.rl .lk:focus-visible{outline:2px solid var(--text-accent);outline-offset:2px}
a.rl-btn{text-decoration:none}
.rl-dl-par{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.4rem .9rem;margin:0;font-size:.86rem}
.rl-dl-par dt{color:var(--text-muted)}
.rl-dl-par dd{margin:0;text-align:right;font-weight:700;font-variant-numeric:tabular-nums}
.rl-linha-valor{display:flex;flex-wrap:wrap;justify-content:space-between;gap:.25rem .75rem;padding:.45rem 0;border-bottom:1px solid var(--border);font-size:.86rem}
.rl-linha-valor:last-child{border-bottom:0}
.rl-linha-valor b{font-variant-numeric:tabular-nums;margin-left:auto;text-align:right}
.rl-linha-valor small{display:block;font-size:.72rem;color:var(--text-muted)}
.rl-selo.inv{border-style:dashed;border-color:var(--border-strong,var(--border));color:var(--text);font-weight:700}
.rl-tab td small{display:block;font-size:.72rem;color:var(--text-muted)}
.rl-tab th button.ord{all:unset;cursor:pointer;display:inline-flex;gap:.2rem;align-items:center}
.rl-tab th button.ord:focus-visible{outline:2px solid var(--text-accent);outline-offset:2px}
.rl-tab tr.clic:hover td{background:var(--surface-2)}
.rl-tab.rl-nw td,.rl-tab.rl-nw th{white-space:nowrap}
.rl-busca{display:flex;flex-wrap:wrap;gap:.5rem .75rem;align-items:flex-end}
.rl-busca .rl-in{width:11rem}
/* Régua de referência: trilho e faixa cinza neutros, marcador da fazenda — nunca verde/vermelho, nunca "meta". */
.rl-regua{display:flex;flex-direction:column;gap:.35rem}
.rl-regua>svg{display:block;width:100%;height:auto;overflow:visible}
.rl-regua .trilho{fill:var(--st-neutro-bg);stroke:var(--st-neutro-line)}
.rl-regua .faixa{fill:color-mix(in srgb,var(--text) 22%,var(--surface))}
.rl-regua .marca{fill:var(--text);stroke:var(--surface);stroke-width:1.5}
.rl-regua text{fill:var(--text-muted);font-size:11px;font-family:var(--font-body)}
.rl-regua text.forte{fill:var(--text);font-weight:700}
@media (max-width:640px){.rl-busca>.rl-campo{flex:1 1 100%}.rl-busca .rl-in{width:100%}}
@media print{.rl-regua{display:none!important}}
`;
