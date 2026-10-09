// Estilos do molde único dos Relatórios (prefixo "rl-"). Só tokens (var(--…)):
// funciona nos 3 temas × 3 paletas. Sem gradiente em texto, sem borda lateral
// > 1px em card, sem sombra dura; status nunca só por cor (seta + palavra).
// Movimento: entrada ≤ 300 ms, só transform/opacity, desligado em
// prefers-reduced-motion (o conteúdo é visível por padrão).
export const CSS_RELATORIO = `
.rl{display:flex;flex-direction:column;gap:1rem;min-width:0;
  --rl-a:var(--text-accent);
  --rl-n1:color-mix(in srgb,var(--text) 74%,var(--surface));
  --rl-n2:color-mix(in srgb,var(--text) 44%,var(--surface));
  --rl-n3:color-mix(in srgb,var(--text) 16%,var(--surface));
  --rl-margem:color-mix(in srgb,var(--text-accent) 20%,var(--surface));
  --rl-ease:cubic-bezier(.16,1,.3,1)}
.rl *:focus-visible{outline:2px solid var(--text-accent);outline-offset:2px}
.rl .sr-only,.rl-sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}

/* Barra de contexto */
.rl-ctx{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-sm);padding:.7rem .8rem;display:flex;flex-direction:column;gap:.55rem}
.rl-ctx-sum{display:none;align-items:center;justify-content:space-between;gap:.5rem;font-size:.82rem;color:var(--text)}
.rl-ctx-row{display:flex;flex-wrap:wrap;align-items:flex-end;gap:.55rem .75rem}
.rl-campo{display:flex;flex-direction:column;gap:.2rem;min-width:0}
.rl-campo>label,.rl-campo>.rl-rot{font-size:.7rem;font-weight:600;color:var(--text-muted)}
.rl-in{background:var(--surface);color:var(--text);border:1px solid var(--border-strong,var(--border));border-radius:var(--r-sm);padding:0 .5rem;min-height:36px;font:inherit;font-size:.84rem;max-width:100%}
.rl-in:disabled{opacity:.6;cursor:not-allowed}
.rl-seg{display:inline-flex;border:1px solid var(--border-strong,var(--border));border-radius:var(--r-sm);background:var(--surface);max-width:100%}
.rl-seg button{border:0;background:transparent;color:var(--text-muted);font:inherit;font-size:.8rem;font-weight:600;padding:0 .65rem;min-height:34px;cursor:pointer;white-space:nowrap}
.rl-seg button+button{border-left:1px solid var(--border-strong,var(--border))}
.rl-seg button:hover:not(:disabled){color:var(--text);background:var(--surface-2)}
.rl-seg button[aria-pressed="true"]{background:var(--pill-active-bg);color:var(--pill-active-fg);box-shadow:inset 0 0 0 1px var(--pill-active-border)}
.rl-seg button:disabled{cursor:not-allowed;opacity:.65}
.rl-cresce{flex:1 1 0}
.rl-acoes{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center}
.rl-btn{display:inline-flex;align-items:center;gap:.35rem;border:1px solid var(--border-strong,var(--border));background:var(--surface);color:var(--text);border-radius:var(--r-sm);font:inherit;font-size:.78rem;font-weight:600;padding:0 .65rem;min-height:34px;cursor:pointer;white-space:nowrap}
.rl-btn:hover:not(:disabled){background:var(--surface-2)}
.rl-btn:disabled{opacity:.55;cursor:not-allowed}
.rl-btn.feito{border-color:var(--st-pago-line);color:var(--st-pago-fg);background:var(--st-pago-bg)}
.rl-ctxnota{display:flex;gap:.4rem;align-items:flex-start;margin:0;font-size:.78rem;color:var(--text-muted)}
.rl-ctxnota svg{flex-shrink:0;margin-top:2px}

/* Migalhas (onde estou) + voltar um nível */
.rl-mig{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.4rem .75rem;font-size:.8rem}
.rl-mig ol{display:flex;flex-wrap:wrap;align-items:center;gap:.25rem;list-style:none;margin:0;padding:0;color:var(--text-muted)}
.rl-mig li{display:inline-flex;align-items:center;gap:.25rem}
.rl-mig a,.rl-mig button.lk{all:unset;cursor:pointer;color:var(--text-accent);text-decoration:underline;text-underline-offset:3px}
.rl-mig [aria-current="page"]{color:var(--text);font-weight:700}

/* Cabeçalho, frase-resumo */
.rl-cab.com-acao{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:.6rem 1rem}
.rl-cab h2{font-size:1.75rem;font-weight:700;letter-spacing:-.02em;color:var(--text);margin:0;line-height:1.15}
.rl-cab h2:focus,.rl-cab h2:focus-visible{outline:none!important;box-shadow:none!important}
.rl-cab p{margin:.25rem 0 0;font-size:.82rem;color:var(--text-muted)}
.rl-frase{margin:0;max-width:72ch;font-size:1.02rem;line-height:1.6;color:var(--text)}
.rl-frase strong{font-weight:700}

/* Faixa de KPIs: 1 principal + 3 de apoio */
.rl-kpis{display:grid;grid-template-columns:minmax(0,1.55fr) repeat(3,minmax(0,1fr));gap:.6rem}
.rl-kpi{display:flex;flex-direction:column;gap:.3rem;background:var(--surface);border:1px solid var(--border);border-bottom:3px solid var(--st-neutro-line);border-radius:var(--r-sm);padding:.75rem .85rem;text-align:left;color:var(--text);font:inherit;min-width:0}
button.rl-kpi{cursor:pointer}button.rl-kpi:hover{background:var(--surface-2)}
.rl-kpi.principal{border-bottom-color:var(--rl-a)}
.rl-kpi .l{font-size:.6875rem;font-weight:600;letter-spacing:.13em;text-transform:uppercase;color:var(--text-muted);display:flex;flex-wrap:wrap;gap:.35rem;align-items:center}
.rl-kpi .v{font-size:1.45rem;font-weight:800;letter-spacing:-.01em;font-variant-numeric:tabular-nums;line-height:1.1;overflow-wrap:anywhere}
.rl-kpi.principal .v{font-size:2.6rem;letter-spacing:-.02em}
.rl-kpi .v .u{font-size:.5em;font-weight:700;color:var(--text-muted);margin-left:.15em}
.rl-kpi .v.neg{color:var(--st-venc-fg)}
.rl-kpi .s{font-size:.76rem;color:var(--text-muted);line-height:1.4}
.rl-kpi .ir{margin-top:auto;font-size:.75rem;font-weight:700;color:var(--text-accent);display:inline-flex;align-items:center;gap:.2rem}
.rl-dl{display:inline-flex;align-items:center;gap:.3rem;align-self:flex-start;border:1px solid var(--st-neutro-line);background:var(--st-neutro-bg);color:var(--st-neutro-fg);border-radius:999px;padding:1px 9px;font-size:.74rem;font-weight:600;line-height:1.5}
.rl-dl.bom{border-color:var(--st-pago-line);background:var(--st-pago-bg);color:var(--st-pago-fg)}
.rl-dl.ruim{border-color:var(--st-venc-line);background:var(--st-venc-bg);color:var(--st-venc-fg)}
.rl-selo{display:inline-flex;align-items:center;gap:.25rem;border:1px solid var(--st-neutro-line);background:var(--st-neutro-bg);color:var(--st-neutro-fg);border-radius:999px;padding:0 8px;font-size:.68rem;font-weight:600;letter-spacing:0;text-transform:none}

/* Painéis, gráfico */
.rl-painel{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-sm);padding:.85rem .95rem;min-width:0}
.rl-tit{font-size:.75rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--text-accent);margin:0 0 .65rem}
.rl-cab-painel{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.4rem .75rem;margin:0 0 .65rem}
.rl-cab-painel .rl-tit{margin:0}
.rl-graf svg.rl-svg{display:block;width:100%;height:auto;overflow:visible}
.rl-graf text{fill:var(--text-muted);font-size:12px;font-family:var(--font-body)}
.rl-graf .forte{fill:var(--text);font-weight:700}
.rl-leg{display:flex;flex-wrap:wrap;gap:.35rem 1rem;font-size:.76rem;color:var(--text-muted);margin-top:.5rem}
.rl-leg span{display:inline-flex;align-items:center;gap:.35rem}
.rl-leg i{display:inline-block;width:14px;height:10px;border-radius:1px}
.rl-leg i.ln{height:0;border-top:2.5px solid currentColor}
.rl-astab{margin-top:.5rem;font-size:.8rem}
.rl-astab summary{cursor:pointer;color:var(--text-accent);font-weight:600;display:inline-flex;gap:.35rem;align-items:center}
.rl-dois{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:.75rem}

/* Tabela Atual | Comparação | Δ | Δ% */
/* position:relative: o texto só para leitor de tela (.rl-sr, absoluto) das células roladas fica DENTRO da
   rolagem da tabela — sem ele vazava do card e a página rolava de lado a 390 px (achado por C1 e C2). */
.rl-tw{overflow-x:auto;position:relative;border:1px solid var(--border);border-radius:var(--r-sm)}
.rl-tab{margin:0}
.rl-tab th.r,.rl-tab td.r{text-align:right;white-space:nowrap}
.rl-tab td{vertical-align:top}
.rl-tab tr.tot td{font-weight:700;background:var(--surface-2)}
.rl-tab tr.ind td:first-child{padding-left:1.6rem}
.rl-tab tr.zero td{color:var(--text-muted)}
.rl-tab td .sub{display:block;font-size:.72rem;color:var(--text-muted);font-weight:400;margin-top:1px}
.rl-tab .mut{color:var(--text-muted)}
.rl-tab .neg{color:var(--st-venc-fg)}
.rl-tab tr.clic{cursor:pointer}
.rl-linkbtn{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:.25rem;color:inherit;font-weight:inherit}
.rl-linkbtn:hover{text-decoration:underline;text-underline-offset:3px}
.rl-linkbtn:focus-visible{outline:2px solid var(--text-accent);outline-offset:2px}
.rl-linkbtn svg{color:var(--text-muted);flex-shrink:0}
.rl-dt{display:inline-flex;gap:.25rem;align-items:center;font-weight:600;white-space:nowrap}
.rl-dt.bom{color:var(--st-pago-fg)}.rl-dt.ruim{color:var(--st-venc-fg)}.rl-dt.neu{color:var(--text-muted)}
.rl-tab tfoot td{font-weight:700;padding:8px 10px;color:var(--text);font-variant-numeric:tabular-nums;background:var(--surface-2);border-top:1px solid var(--border-strong,var(--border))}

/* Notas de método, conferência, avisos */
.rl-nota{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-sm)}
.rl-nota>summary{cursor:pointer;padding:.7rem .9rem;font-weight:700;font-size:.86rem;display:flex;align-items:center;gap:.45rem;color:var(--text)}
.rl-nota>div{padding:0 .9rem .85rem;font-size:.82rem;line-height:1.55;color:var(--text)}
.rl-nota dl{display:grid;grid-template-columns:minmax(0,13rem) minmax(0,1fr);gap:.35rem .9rem;margin:0}
.rl-nota dt{font-weight:700}.rl-nota dd{margin:0;color:var(--text-muted)}
.rl-nota ul{margin:.3rem 0 0;padding-left:1.1rem}
.rl-conf{display:flex;flex-wrap:wrap;gap:.25rem .6rem;align-items:center;font-size:.78rem;color:var(--text-muted);border-top:1px dashed var(--border-strong,var(--border));padding-top:.6rem}
.rl-conf b{display:inline-flex;align-items:center;gap:.3rem}
.rl-conf .ok{color:var(--st-pago-fg)}.rl-conf .nok{color:var(--st-venc-fg)}
.rl-aviso{display:flex;gap:.55rem;align-items:flex-start;padding:.65rem .8rem;border:1px solid var(--st-logo-line);background:var(--st-logo-bg);color:var(--st-logo-fg);border-radius:var(--r-sm);font-size:.82rem}
.rl-aviso.erro{border-color:var(--st-venc-line);background:var(--st-venc-bg);color:var(--st-venc-fg)}
.rl-aviso.info{border-color:var(--st-aberto-line);background:var(--st-aberto-bg);color:var(--st-aberto-fg)}
.rl-aviso svg{flex-shrink:0;margin-top:1px}
.rl-aviso p{margin:.15rem 0 0}
.rl-aviso a,.rl-aviso button.lk{color:inherit;font-weight:700;text-decoration:underline;text-underline-offset:3px;background:none;border:0;padding:0;font:inherit;cursor:pointer}

/* Estado vazio que ensina */
.rl-vazio{display:flex;flex-direction:column;gap:.55rem;padding:1.4rem 1.2rem;border:1px dashed var(--border-strong,var(--border));border-radius:var(--r-sm);background:var(--surface-2);color:var(--text)}
.rl-vazio b{font-size:1rem}
.rl-vazio p{margin:0;color:var(--text-muted);font-size:.86rem;max-width:70ch}
.rl-vazio .prog{font-size:.75rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted)}
.rl-chk{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.35rem;font-size:.86rem}
.rl-chk li{display:flex;gap:.45rem;align-items:flex-start}
.rl-chk .y{color:var(--st-pago-fg)}.rl-chk .n{color:var(--text-muted)}
.rl-chk a{color:var(--text-accent);font-weight:600}

/* Carregando */
.rl-esq{display:grid;gap:.6rem}
.rl-esq .skeleton{height:84px}

/* Movimento */
@media (prefers-reduced-motion:no-preference){
  .rl-entra{animation:rl-entra 260ms var(--rl-ease) both}
  .rl-degrau{transform-box:fill-box;transform-origin:left center;animation:rl-cresce 280ms var(--rl-ease) both;animation-delay:min(calc(var(--i,0) * 25ms),150ms)}
  .rl-degrau.esq{transform-origin:right center}
  .rl-barra{transform-origin:left center;animation:rl-cresce 280ms var(--rl-ease) both}
}
@keyframes rl-entra{from{opacity:0;transform:translateY(6px)}}
@keyframes rl-cresce{from{transform:scaleX(0)}}

@media (max-width:1100px){.rl-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.rl-kpi.principal{grid-column:1/-1}.rl-dois{grid-template-columns:minmax(0,1fr)}}
@media (max-width:767px){
  .rl-in,.rl-seg button,.rl-btn{min-height:44px}
  .rl-in{font-size:16px}
  .rl-cab h2{font-size:1.4rem}
  .rl-kpi.principal .v{font-size:2.1rem}
  .rl-nota dl{grid-template-columns:minmax(0,1fr)}
  .rl-opc{display:none}
  .rl-tab td:first-child{min-width:9.5rem}
}
@media (max-width:640px){
  .rl-ctx-sum{display:flex}
  .rl-ctx:not(.aberta) .rl-ctx-row,.rl-ctx:not(.aberta) .rl-ctxnota{display:none}
  .rl-ctx-row>.rl-campo{flex:1 1 100%}
  .rl-ctx-row .rl-in{width:100%}
  .rl-seg{display:flex;width:100%}.rl-seg button{flex:1 1 0;padding:0 .3rem;white-space:normal;line-height:1.15}
  .rl-kpis{grid-template-columns:minmax(0,1fr)}
  .rl-frase{font-size:.96rem}
}

/* Impressão: só o relatório, com o cabeçalho do cliente */
.rl-cab-impressao{display:none}
@media print{
  @page{margin:14mm}
  body:has(.rl) .farm-shell-h>*:not(main),body:has(.rl) main>nav,body:has(.rl) .fin-cabecalho,.rl-noprint{display:none!important}
  body:has(.rl) .farm-shell-h,body:has(.rl) main{display:block!important;height:auto!important;overflow:visible!important}
  /* Papel é sempre claro: cores do sistema (Canvas/CanvasText), em qualquer tema escolhido na tela. */
  :root:has(.rl){color-scheme:light}
  body:has(.rl){background:Canvas;color:CanvasText}
  .rl{gap:.6rem;--text:CanvasText;--text-muted:GrayText;--surface:Canvas;--surface-2:Canvas;--border:GrayText;--border-strong:GrayText;--text-accent:CanvasText;--thead-bg:Canvas;--thead-fg:CanvasText;color:CanvasText}
  .rl-cab-impressao{display:block;border-bottom:2px solid currentColor;padding-bottom:6px;margin-bottom:4px;font-size:10.5pt}
  .rl-cab-impressao b{display:block;font-size:14pt}
  .rl-kpis{grid-template-columns:repeat(4,1fr)!important}
  .rl-kpi.principal{grid-column:auto!important}
  .rl-kpi.principal .v{font-size:22pt}
  .rl-painel,.rl-kpi,.rl-tw,.rl-nota{break-inside:avoid;box-shadow:none}
  .rl-tw{overflow:visible}
  .rl-nota>div{display:block!important}
  .rl *{animation:none!important}
  .rl-kpi .ir,.rl .rl-btn,.rl .btn-primary,.rl-linkbtn svg{display:none!important}
}
`;
