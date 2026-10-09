// Estilos das telas de Entrega ao contador (Fase C5): lista de conferências,
// grade de meses, fila de pareamentos e formulários em linha. Só tokens
// (var(--…)); status sempre com ícone + palavra (nunca só cor); sem borda
// lateral > 1px em card; movimento curto e desligado em prefers-reduced-motion.
export const CSS_ENTREGA = `
.ce-lst{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.ce-lst>li{display:grid;grid-template-columns:24px minmax(0,1fr) auto;gap:.35rem .7rem;align-items:start;padding:.65rem 0;border-bottom:1px solid var(--border)}
.ce-lst>li:last-child{border-bottom:0}
.ce-lst b{font-weight:700;font-size:.9rem;color:var(--text)}
.ce-lst small{display:block;font-size:.76rem;color:var(--text-muted);line-height:1.45;margin-top:1px}
.ce-ic{display:inline-flex;margin-top:1px}
.ce-ic.ok{color:var(--st-pago-fg)}.ce-ic.aten{color:var(--st-logo-fg)}.ce-ic.neu{color:var(--text-muted)}.ce-ic.info{color:var(--st-aberto-fg)}
.ce-sub{grid-column:2/-1;list-style:none;margin:.2rem 0 0;padding:0 0 0 .75rem;border-left:1px solid var(--border);display:flex;flex-direction:column}
.ce-sub>li{display:flex;flex-wrap:wrap;justify-content:space-between;gap:.25rem .75rem;padding:.45rem 0;border-bottom:1px dashed var(--border);font-size:.82rem}
.ce-sub>li:last-child{border-bottom:0}
.ce-sub .t{font-weight:600;color:var(--text)}
.ce-sub .s{display:block;font-size:.74rem;color:var(--text-muted)}
.ce-mais{font-size:.76rem;color:var(--text-muted);padding:.35rem 0}
.ce-pill{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}
.ce-acts{display:flex;flex-wrap:wrap;gap:.45rem;align-items:center;margin-top:.75rem}
.ce-acts .hint{font-size:.78rem;color:var(--text-muted)}
.ce-btn-pri{display:inline-flex;align-items:center;gap:.4rem;border:1px solid var(--pill-active-border,var(--text-accent));background:var(--pill-active-bg,var(--text-accent));color:var(--pill-active-fg,var(--surface));border-radius:var(--r-sm);font:inherit;font-size:.82rem;font-weight:700;padding:0 .85rem;min-height:38px;cursor:pointer}
.ce-btn-pri:disabled,.ce-btn-pri[aria-disabled="true"]{opacity:.55;cursor:not-allowed}
.ce-btn-pri:hover:not(:disabled){filter:brightness(1.06)}
.ce-btn{display:inline-flex;align-items:center;gap:.35rem;border:1px solid var(--border-strong,var(--border));background:var(--surface);color:var(--text);border-radius:var(--r-sm);font:inherit;font-size:.78rem;font-weight:600;padding:0 .65rem;min-height:38px;cursor:pointer;white-space:nowrap}
.ce-btn:hover:not(:disabled){background:var(--surface-2)}
.ce-btn:disabled{opacity:.55;cursor:not-allowed}
.ce-form{display:flex;flex-direction:column;gap:.45rem;margin-top:.6rem;padding:.75rem;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface-2);max-width:40rem}
.ce-form label{font-size:.76rem;font-weight:600;color:var(--text-muted)}
.ce-form textarea,.ce-form input,.ce-form select{background:var(--surface);color:var(--text);border:1px solid var(--border-strong,var(--border));border-radius:var(--r-sm);padding:.45rem .55rem;font:inherit;font-size:.86rem;min-height:38px;max-width:100%}
.ce-form textarea{min-height:64px;resize:vertical}
.ce-form .linha{display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));gap:.5rem}
.ce-form .linha>div{display:flex;flex-direction:column;gap:.2rem;min-width:0}
.ce-erro{font-size:.8rem;color:var(--st-venc-fg);margin:0}
.ce-meses{display:grid;grid-template-columns:repeat(auto-fill,minmax(6.6rem,1fr));gap:.4rem}
.ce-mes{all:unset;box-sizing:border-box;display:flex;flex-direction:column;gap:2px;padding:.45rem .55rem;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface);cursor:pointer;font-size:.8rem;color:var(--text)}
.ce-mes b{font-size:.84rem}
.ce-mes span{display:inline-flex;align-items:center;gap:4px;color:var(--text-muted);font-size:.74rem}
.ce-mes.fechado{background:var(--surface-2)}
.ce-mes[aria-current="true"]{border-color:var(--text-accent);box-shadow:inset 0 0 0 1px var(--text-accent)}
.ce-mes:hover{background:var(--surface-2)}
.ce-mes:focus-visible{outline:2px solid var(--text-accent);outline-offset:2px}
.ce-topo{display:flex;flex-wrap:wrap;gap:.5rem .75rem;align-items:center;justify-content:space-between}
.ce-topo .rl-seg{flex-wrap:wrap}
.ce-file{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
.ce-tab td{vertical-align:middle}
.ce-tab th{position:relative} /* o texto só para leitor de tela (absoluto) fica preso na tabela que rola, não alarga a página */
.ce-tab{position:relative}
.ce-tab td small{display:block;font-size:.72rem;color:var(--text-muted);margin-top:1px}
.ce-tab .r{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.ce-tab .neg{color:var(--st-venc-fg)}
.ce-tab .mut{color:var(--text-muted)}
.ce-tab .acao{display:flex;flex-wrap:wrap;gap:.3rem;justify-content:flex-end}
.ce-tab tr.foco td{background:var(--surface-2)}
.ce-fila{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.4rem}
.ce-fila>li{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr) auto;gap:.4rem .75rem;align-items:center;padding:.55rem .65rem;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface);font-size:.82rem}
.ce-fila .lado b{display:block;font-size:.84rem}
.ce-fila .lado small{display:block;color:var(--text-muted);font-size:.74rem}
.ce-fila .seta{color:var(--text-muted)}
.ce-dl{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.3rem .9rem;margin:0;font-size:.84rem}
.ce-dl dt{color:var(--text-muted)}.ce-dl dd{margin:0;text-align:right;font-weight:700;font-variant-numeric:tabular-nums}
.ce-ok{display:flex;gap:.55rem;align-items:flex-start;padding:.65rem .8rem;border:1px solid var(--st-pago-line);background:var(--st-pago-bg);color:var(--st-pago-fg);border-radius:var(--r-sm);font-size:.84rem}
.ce-ok p{margin:.15rem 0 0}
.ce-hash{font-family:var(--font-mono,ui-monospace,monospace);font-size:.74rem;color:var(--text-muted);word-break:break-all}
.ce-gira{animation:ce-gira .8s linear infinite}
@keyframes ce-gira{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.ce-gira{animation:none}}
@media (prefers-reduced-motion:no-preference){.ce-entra{animation:rl-entra 220ms var(--rl-ease,ease-out) both}}
@media (max-width:767px){
  .ce-lst>li{grid-template-columns:22px minmax(0,1fr)}
  .ce-lst>li>.ce-pill{grid-column:2;justify-self:start}
  .ce-meses{grid-template-columns:repeat(auto-fill,minmax(5.2rem,1fr))}
  .ce-fila>li{grid-template-columns:minmax(0,1fr)}
  .ce-fila .seta{display:none}
  .ce-btn-pri,.ce-btn{min-height:44px}
  .ce-tab .acao{justify-content:flex-start}
  .ce-tab td:first-child{min-width:0}
  .ce-tab td:nth-child(2){min-width:11rem}
}
@media print{.ce-acts,.ce-form,.ce-topo .rl-btn,.ce-tab .acao{display:none!important}.ce-mes{border:1px solid GrayText}}
`;
