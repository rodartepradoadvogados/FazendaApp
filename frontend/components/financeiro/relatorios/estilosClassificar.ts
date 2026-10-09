// Estilos da tela Classificar (Relatórios › Resultado), prefixo "cl-". Só tokens (var(--…)):
// funciona nos 3 temas × 3 paletas; status nunca só por cor (ícone + palavra); sem borda lateral
// > 1px em card; sem sombra; movimento ≤ 300 ms só em opacity/transform e desligado em
// prefers-reduced-motion (a base é o .rl-entra do molde). Complementa estilos.ts.
export const CSS_CLASSIFICAR = `
.cl-motivos{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.6rem}
.cl-motivo{display:flex;flex-direction:column;gap:.3rem;background:var(--surface);border:1px solid var(--border);border-bottom:3px solid var(--st-neutro-line);border-radius:var(--r-sm);padding:.7rem .8rem;text-align:left;color:var(--text);font:inherit;min-width:0;cursor:pointer}
.cl-motivo:hover{background:var(--surface-2)}
.cl-motivo[aria-pressed="true"]{border-color:var(--text-accent);border-bottom-color:var(--text-accent);box-shadow:inset 0 0 0 1px var(--text-accent)}
.cl-motivo.zero{border-bottom-color:var(--st-pago-line)}
.cl-motivo.falta{border-bottom-color:var(--st-logo-line)}
.cl-motivo .l{font-size:.6875rem;font-weight:600;letter-spacing:.13em;text-transform:uppercase;color:var(--text-muted)}
.cl-motivo .v{font-size:1.9rem;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums;line-height:1.05}
.cl-motivo .v small{font-size:.78rem;font-weight:600;color:var(--text-muted);letter-spacing:0;margin-left:.3rem}
.cl-motivo .s{font-size:.76rem;color:var(--text-muted);line-height:1.4}
.cl-motivo .ok{display:inline-flex;align-items:center;gap:.3rem;font-size:.78rem;font-weight:600;color:var(--st-pago-fg)}
.cl-motivo .trava{display:inline-flex;align-items:flex-start;gap:.3rem;font-size:.74rem;color:var(--text-muted);line-height:1.35}

.cl-cab{display:flex;flex-wrap:wrap;gap:.35rem 1rem;align-items:baseline;justify-content:space-between;margin:0 0 .5rem}
.cl-cab p{margin:0;font-size:.82rem;color:var(--text-muted);max-width:75ch}
.cl-tools{display:flex;flex-wrap:wrap;gap:.55rem .75rem;align-items:flex-end;margin:0 0 .7rem}
.cl-tools .rl-campo{min-width:min(100%,15rem)}
.cl-barra{display:flex;flex-direction:column;gap:.55rem;padding:.7rem .8rem;margin:0 0 .7rem;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface-2)}
.cl-barra-t{display:flex;flex-wrap:wrap;gap:.3rem .75rem;align-items:baseline;font-size:.82rem;color:var(--text)}
.cl-barra-t b{font-variant-numeric:tabular-nums}
.cl-barra-c{display:flex;flex-wrap:wrap;gap:.55rem .75rem;align-items:flex-end}
.cl-barra-c .rl-campo{min-width:min(100%,16rem);flex:0 1 22rem}
.cl-barra-c fieldset{border:0;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:.2rem 1rem;font-size:.82rem}
.cl-barra-c fieldset legend{font-size:.7rem;font-weight:600;color:var(--text-muted);padding:0;margin-bottom:.2rem}
.cl-barra-c fieldset label{display:inline-flex;align-items:center;gap:.4rem;min-height:30px;cursor:pointer}
.cl-barra-d{margin:0;font-size:.78rem;color:var(--text-muted);line-height:1.45}
.cl-aplicar{min-height:38px}
.cl-aplicar:disabled{opacity:.55;cursor:not-allowed}

.cl-tw{max-height:none}
.cl-tab th.cl-sel,.cl-tab td.c-sel{width:2.4rem;padding-right:0}
.cl-tab input[type=checkbox]{width:18px;height:18px;accent-color:var(--text-accent);cursor:pointer;margin:0}
.cl-tab input[type=checkbox]:disabled{cursor:not-allowed;opacity:.5}
.cl-tab td{vertical-align:top}
.cl-tab td b{font-weight:700}
.cl-tab td .sub{display:block;font-size:.74rem;color:var(--text-muted);font-weight:400;margin-top:1px}
.cl-tab tr.travada td{color:var(--text-muted)}
.cl-tab .c-conta .nenhuma{color:var(--text-muted);font-style:italic}
.cl-tab .c-valor{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;font-weight:700}
.cl-tab .c-valor small{display:block;font-weight:500;font-size:.72rem;color:var(--text-muted)}
.cl-tab .c-sug .t{display:flex;align-items:flex-start;gap:.35rem;font-weight:600;font-size:.82rem}
.cl-tab .c-sug .t svg{flex-shrink:0;margin-top:2px}
.cl-tab .c-sug .m{display:block;font-size:.74rem;color:var(--text-muted);margin:1px 0 .35rem;line-height:1.35}
.cl-tab tr.cl-grupo th{background:var(--surface-2);text-align:left;font-family:inherit;text-transform:none;letter-spacing:0;color:var(--text);font-size:.84rem;font-weight:400;padding:.55rem .7rem;white-space:normal}
.cl-grupo-in{display:flex;flex-wrap:wrap;gap:.35rem .9rem;align-items:center;justify-content:space-between}
.cl-grupo-in label{display:inline-flex;gap:.55rem;align-items:center;cursor:pointer;min-width:0}
.cl-grupo-in .qtd{color:var(--text-muted);font-size:.78rem}
.cl-grupo-sug{display:flex;flex-wrap:wrap;gap:.3rem .6rem;align-items:center;font-size:.8rem}
.cl-grupo-sug .t{display:inline-flex;align-items:center;gap:.35rem}
.cl-grupo-sug .t svg{flex-shrink:0}
.cl-grupo-sug .m{color:var(--text-muted);font-size:.74rem}
.cl-chip{display:inline-flex;align-items:center;gap:.25rem;border:1px solid var(--st-neutro-line);background:var(--st-neutro-bg);color:var(--st-neutro-fg);border-radius:999px;padding:0 8px;font-size:.7rem;font-weight:600;line-height:1.5;margin-right:.3rem}
.cl-chip.trava{border-color:var(--st-logo-line);background:var(--st-logo-bg);color:var(--st-logo-fg)}
.cl-mais{display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:center;justify-content:space-between;margin-top:.6rem;font-size:.8rem;color:var(--text-muted)}
.cl-ver{display:inline-flex;align-items:center;gap:.25rem;font-size:.76rem;font-weight:600;color:var(--text-accent);background:none;border:0;padding:0;font-family:inherit;cursor:pointer;text-decoration:underline;text-underline-offset:3px;margin-top:.2rem}

.cl-aviso-t{display:flex;flex-wrap:wrap;gap:.4rem .8rem;align-items:center}
.cl-msg{display:flex;gap:.55rem;align-items:flex-start;padding:.65rem .8rem;border:1px solid var(--st-pago-line);background:var(--st-pago-bg);color:var(--st-pago-fg);border-radius:var(--r-sm);font-size:.84rem}
.cl-msg.erro{border-color:var(--st-venc-line);background:var(--st-venc-bg);color:var(--st-venc-fg)}
.cl-msg svg{flex-shrink:0;margin-top:1px}
.cl-msg p{margin:.15rem 0 0}
.cl-desfazer{display:flex;flex-wrap:wrap;gap:.4rem .8rem;align-items:center;padding:.5rem .8rem;border:1px solid var(--border);background:var(--surface);border-radius:var(--r-sm);font-size:.82rem;color:var(--text)}
.cl-desfazer svg{color:var(--text-muted);flex-shrink:0}
.cl-vazio-motivo{display:flex;gap:.55rem;align-items:center;padding:1rem;border:1px dashed var(--border-strong,var(--border));border-radius:var(--r-sm);background:var(--surface-2);font-size:.88rem;color:var(--text)}
.cl-vazio-motivo svg{color:var(--st-pago-fg);flex-shrink:0}
.cl-trava-motivo{display:flex;gap:.55rem;align-items:flex-start;padding:.8rem 1rem;border:1px solid var(--st-logo-line);background:var(--st-logo-bg);color:var(--st-logo-fg);border-radius:var(--r-sm);font-size:.86rem}
.cl-trava-motivo svg{flex-shrink:0;margin-top:2px}

@media (prefers-reduced-motion:no-preference){
  .cl-msg{animation:rl-entra 200ms var(--rl-ease,ease-out) both}
}
@media (max-width:1100px){.cl-motivos{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:767px){
  .cl-aplicar,.cl-ver{min-height:44px}
  .cl-tab input[type=checkbox]{width:22px;height:22px}
  .cl-tw{border:0;overflow:visible}
  .cl-tab thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
  .cl-tab,.cl-tab tbody{display:block;width:100%}
  .cl-tab tbody tr{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:.2rem .65rem;padding:.75rem .7rem;border:1px solid var(--border);border-radius:var(--r-sm);margin-bottom:.5rem;background:var(--surface)}
  .cl-tab tbody td{display:block;padding:0!important;border:0;min-width:0!important}
  .cl-tab tbody td.c-sel{grid-column:1;grid-row:1/span 4}
  .cl-tab tbody td.c-lanc{grid-column:2}
  .cl-tab tbody td.c-valor{grid-column:3;grid-row:1}
  .cl-tab tbody td.c-data,.cl-tab tbody td.c-conta,.cl-tab tbody td.c-sug{grid-column:2/-1;font-size:.82rem}
  .cl-tab tbody td[data-rotulo]::before{content:attr(data-rotulo) ": ";color:var(--text-muted)}
  .cl-tab tbody tr.cl-grupo{display:block;padding:0;border:0;margin:.4rem 0 .25rem;background:transparent}
  .cl-tab tr.cl-grupo th{display:block;border:1px solid var(--border);border-radius:var(--r-sm)}
  .cl-motivo .v{font-size:1.6rem}
}
@media (max-width:520px){.cl-motivos{grid-template-columns:minmax(0,1fr)}}
@media print{.cl-barra,.cl-desfazer,.cl-tools,.cl-tab .c-sel,.cl-tab th.cl-sel,.cl-ver{display:none!important}}
`;
