// Estilos próprios do grupo Plano (Orçamento e Cenários), no mesmo vocabulário
// do molde (prefixo "rl-", só tokens). Ficam aqui para não mexer em estilos.ts,
// compartilhado com as outras telas da Fase C.
export const CSS_PLANO = `
.rl-segv{display:inline-flex;border:1px solid var(--border-strong,var(--border));border-radius:var(--r-sm);background:var(--surface)}
.rl-segv button{border:0;background:transparent;color:var(--text-muted);font:inherit;font-size:.8rem;font-weight:600;padding:0 .75rem;min-height:34px;cursor:pointer;white-space:nowrap}
.rl-segv button+button{border-left:1px solid var(--border-strong,var(--border))}
.rl-segv button[aria-pressed="true"]{background:var(--pill-active-bg);color:var(--pill-active-fg);box-shadow:inset 0 0 0 1px var(--pill-active-border)}
.rl-cabacoes{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;justify-content:space-between}
.rl-tab tr.sec td{font-weight:700;background:var(--surface-2);color:var(--text)}
.rl-tab tr.sub2 td{font-size:.74rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);background:var(--surface)}
.rl-tab tr.coberta td{color:var(--text-muted)}
.rl-tab tr.coberta td:first-child{padding-left:1.6rem}
.rl-tab td.av{white-space:nowrap;font-size:.8rem}
.rl-tab .lk{all:unset;cursor:pointer;color:var(--text-accent);font-weight:600;text-decoration:underline;text-underline-offset:3px;font-size:.8rem}
.rl-tab .lk:focus-visible{outline:2px solid var(--text-accent);outline-offset:2px}

/* Planilha do orçamento */
.rl-gtw{overflow:auto;max-height:640px;border:1px solid var(--border);border-radius:var(--r-sm)}
.rl-gtab{margin:0;border-collapse:separate;border-spacing:0}
.rl-gtab thead th{position:sticky;top:0;z-index:2;background:var(--thead-bg)}
.rl-gtab .stk{position:sticky;left:0;z-index:1;background:var(--surface);min-width:13rem;max-width:16rem;box-shadow:1px 0 0 var(--border)}
.rl-gtab thead th.stk{z-index:3;background:var(--thead-bg)}
.rl-gtab tbody td{padding:3px 4px;border-bottom:1px solid var(--border)}
.rl-gtab tbody td.stk{padding:6px 10px}
.rl-gtab tr.tot td{font-weight:700;background:var(--surface-2);padding:7px 8px;text-align:right}
.rl-gtab tr.tot td.stk{background:var(--surface-2);text-align:left}
.rl-gtab tr.sec td{font-weight:700;background:var(--surface-2);padding:6px 10px}
.rl-gtab td.r{text-align:right;white-space:nowrap}
.rl-gtab .nome{display:block;font-weight:600;color:var(--text);font-size:.84rem}
.rl-gtab .meta{display:block;font-size:.72rem;color:var(--text-muted)}
.rl-gtab .acoesl{display:flex;gap:.25rem;margin-top:.25rem;flex-wrap:wrap}
.rl-cel{width:100%;min-width:5.6rem;text-align:right;border:1px solid transparent;background:transparent;color:var(--text);font:inherit;font-size:.84rem;font-variant-numeric:tabular-nums;padding:5px 6px;border-radius:4px;min-height:34px}
.rl-cel:hover:not(:disabled){border-color:var(--border-strong,var(--border))}
.rl-cel:focus{border-color:var(--text-accent);background:var(--surface);outline:none;box-shadow:0 0 0 1px var(--text-accent)}
.rl-cel.mud{background:color-mix(in srgb,var(--text-accent) 12%,var(--surface))}
.rl-cel.inv{border-color:var(--st-venc-fg)}
.rl-cel:disabled{color:var(--text-muted);cursor:not-allowed}
.rl-mini{display:inline-flex;align-items:center;gap:.25rem;border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:var(--r-sm);font:inherit;font-size:.72rem;font-weight:600;padding:0 .45rem;min-height:28px;cursor:pointer}
.rl-mini:hover{background:var(--surface-2)}
.rl-barsalvar{position:sticky;bottom:0;z-index:4;display:flex;flex-wrap:wrap;gap:.5rem .75rem;align-items:center;justify-content:space-between;padding:.6rem .8rem;border:1px solid var(--border-strong,var(--border));border-radius:var(--r-sm);background:var(--surface);font-size:.86rem}
.rl-btn.pri{background:var(--pill-active-bg);color:var(--pill-active-fg);border-color:var(--pill-active-border)}
.rl-ferr{display:flex;flex-wrap:wrap;gap:.5rem .75rem;align-items:flex-end;margin-bottom:.7rem}
.rl-ferr label{font-size:.7rem;font-weight:600;color:var(--text-muted);display:flex;flex-direction:column;gap:.2rem}
.rl-in.num{width:6rem;text-align:right}

/* Cenários */
.rl-cvt{margin:0;border-collapse:separate;border-spacing:0}
.rl-cvt .stk{position:sticky;left:0;z-index:1;background:var(--surface);min-width:12rem;max-width:15rem;box-shadow:1px 0 0 var(--border)}
.rl-cvt thead th.stk{z-index:3;background:var(--thead-bg)}
.rl-cvt tbody th.stk{font-weight:600;font-size:.84rem;color:var(--text);text-align:left;padding:8px 10px;vertical-align:top}
.rl-cvt tbody th.stk small{display:block;font-weight:400;font-size:.72rem;color:var(--text-muted);text-align:left;margin-top:1px}
.rl-cvt td{vertical-align:top;border-bottom:1px solid var(--border);padding:6px 8px}
.rl-cvt tr.sec td,.rl-cvt tr.sec th{font-weight:700;background:var(--surface-2);font-size:.8rem;padding:6px 10px}
.rl-cvt tr.main th.stk,.rl-cvt tr.main td{background:color-mix(in srgb,var(--text-accent) 6%,var(--surface))}
.rl-cvt th.cvh{min-width:11.5rem;vertical-align:top;text-transform:none;letter-spacing:0}
.rl-cvt .cvc{display:flex;gap:.3rem;align-items:center;justify-content:flex-end}
.rl-cvt input.rl-in{width:8.4rem;text-align:right;font-variant-numeric:tabular-nums}
.rl-cvt select.rl-in{width:8.4rem}
.rl-cvt small{display:block;font-size:.72rem;color:var(--text-muted);text-align:right;margin-top:2px}
.rl-cvt td.r{text-align:right;white-space:nowrap}
.rl-cvt td.r b{display:block;font-variant-numeric:tabular-nums}
.rl-cvt .neg{color:var(--st-venc-fg)}
.rl-cvt .orig{display:block;font-size:.68rem;color:var(--text-muted);white-space:normal;max-width:10rem;margin-left:auto;text-align:right}
.rl-nomecen{font-weight:700;width:100%;max-width:11rem}
.rl-hintdeslize{display:none;font-size:.78rem;color:var(--text-muted);margin:0 0 .4rem}
@media (max-width:767px){
  .rl-hintdeslize{display:flex;gap:.3rem;align-items:center}
  .rl-cvt .stk,.rl-gtab .stk{min-width:9rem;max-width:10.5rem}
  .rl-cvt input.rl-in,.rl-cvt select.rl-in{width:7.2rem}
  .rl-cel{min-height:44px}
}
@media print{.rl-barsalvar,.rl-gtab .acoesl,.rl-cvt button{display:none!important}.rl-gtw{max-height:none;overflow:visible}}
`;
