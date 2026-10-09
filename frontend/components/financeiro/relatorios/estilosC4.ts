// Estilos das telas da Fase C4 (Réguas de referência, Painel do dono,
// "Apresentar o mês", "Reproduzir o ano" e o diálogo de exportação com réguas).
// Mesmas regras do molde (estilos.ts): só tokens, nada de verde/vermelho nas
// réguas (faixa cinza neutra), status com texto + ícone, sem sombra dura,
// movimento só transform/opacity/stroke-dashoffset e desligado em
// prefers-reduced-motion. Prefixos: rg- (réguas), pd- (painel), ap-
// (apresentação), ra- (reproduzir o ano), ex- (exportação).
export const CSS_C4 = `
/* ── Diálogos (pop-up das réguas, exportação) ── */
.c4-dlg{position:fixed;inset:0;margin:auto;height:fit-content;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface);color:var(--text);padding:0;width:min(760px,calc(100vw - 32px));max-height:calc(100dvh - 32px);overflow:auto}
.c4-dlg h2[tabindex="-1"]:focus,.c4-dlg h2[tabindex="-1"]:focus-visible{outline:none!important;box-shadow:none!important}
.c4-dlg::backdrop{background:var(--overlay)}
.c4-dlg .c4-h{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:.75rem;padding:.8rem 1rem;background:var(--surface);border-bottom:1px solid var(--border)}
.c4-dlg .c4-h h2{margin:0;font-size:1.15rem;font-weight:700;color:var(--text)}
.c4-dlg .c4-h h2:focus{outline:none}
.c4-dlg .c4-b{padding:.9rem 1rem 1rem;display:flex;flex-direction:column;gap:.8rem;font-size:.9rem;line-height:1.55}
.c4-dlg .c4-p{display:flex;flex-wrap:wrap;gap:.5rem;justify-content:flex-end;padding:.75rem 1rem;border-top:1px solid var(--border);position:sticky;bottom:0;background:var(--surface)}
.c4-dlg h3{margin:0 0 .25rem;font-size:.78rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text-accent)}
.c4-btn-pri{display:inline-flex;align-items:center;gap:.4rem;border:1px solid var(--pill-active-border);background:var(--pill-active-bg);color:var(--pill-active-fg);border-radius:var(--r-sm);font:inherit;font-size:.84rem;font-weight:700;padding:0 .9rem;min-height:38px;cursor:pointer;white-space:nowrap}
.c4-btn-pri:disabled{opacity:.55;cursor:not-allowed}
.c4-btn-pri:focus-visible,.c4-dlg button:focus-visible,.c4-dlg a:focus-visible,.c4-dlg input:focus-visible,.c4-dlg select:focus-visible,.c4-dlg textarea:focus-visible{outline:2px solid var(--text-accent);outline-offset:2px}
.c4-txt{white-space:pre-line;margin:0}
.c4-txt+.c4-txt{margin-top:.55rem}
.c4-txt b{display:block;font-size:.8rem;letter-spacing:.06em}
.c4-campo{display:flex;flex-direction:column;gap:.25rem}
.c4-campo label,.c4-campo legend{font-size:.76rem;font-weight:700;color:var(--text-muted)}
.c4-campo input[type=text],.c4-campo select,.c4-campo textarea{background:var(--surface);color:var(--text);border:1px solid var(--border-strong,var(--border));border-radius:var(--r-sm);padding:.45rem .55rem;font:inherit;font-size:.9rem;min-height:40px}
.c4-opcoes{display:flex;flex-direction:column;gap:.4rem;border:0;margin:0;padding:0}
.c4-opcoes label{display:flex;gap:.5rem;align-items:flex-start;font-size:.9rem;color:var(--text);font-weight:500;cursor:pointer}
.c4-opcoes input{margin-top:.25rem}
.c4-confirma{display:flex;gap:.55rem;align-items:flex-start;padding:.6rem .7rem;border:1px solid var(--border-strong,var(--border));border-radius:var(--r-sm);background:var(--surface-2);font-weight:600}
.c4-confirma input{margin-top:.25rem;width:18px;height:18px;flex-shrink:0}
.c4-erro{display:flex;gap:.45rem;align-items:flex-start;padding:.55rem .7rem;border:1px solid var(--st-venc-line);background:var(--st-venc-bg);color:var(--st-venc-fg);border-radius:var(--r-sm);font-size:.85rem}
.c4-info{display:flex;gap:.45rem;align-items:flex-start;padding:.55rem .7rem;border:1px solid var(--st-neutro-line);background:var(--st-neutro-bg);color:var(--st-neutro-fg);border-radius:var(--r-sm);font-size:.85rem}
.c4-info svg,.c4-erro svg{flex-shrink:0;margin-top:2px}
.c4-grade2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:.6rem}

/* ── Réguas de referência ── */
.rg-alerta{border:1px solid var(--border-strong,var(--border));background:var(--surface);border-radius:var(--r-sm);padding:.9rem 1rem;display:flex;flex-direction:column;gap:.6rem;max-width:100%}
.rg-alerta .rg-alerta-t{display:flex;gap:.5rem;align-items:flex-start;font-weight:800;font-size:.95rem;color:var(--text);margin:0;letter-spacing:.01em}
.rg-alerta .rg-alerta-t svg{flex-shrink:0;margin-top:2px;color:var(--text-muted)}
.rg-alerta p{margin:0;font-size:.88rem;line-height:1.6;color:var(--text);max-width:80ch;white-space:pre-line}
.rg-alerta .rg-datas{font-size:.78rem;color:var(--text-muted)}
.rg-alerta .rg-acoes{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center}
.rg-estado{display:inline-flex;align-items:center;gap:.35rem;border:1px solid var(--st-neutro-line);background:var(--st-neutro-bg);color:var(--st-neutro-fg);border-radius:999px;padding:1px 10px;font-size:.76rem;font-weight:600;line-height:1.6}
.rg-lista{display:flex;flex-direction:column}
.rg-leg{display:flex;flex-wrap:wrap;gap:.35rem 1rem;font-size:.76rem;color:var(--text-muted);margin:0 0 .4rem}
.rg-leg span{display:inline-flex;align-items:center;gap:.35rem}
.rg-leg i{display:inline-block;width:16px;height:10px;border:1px solid var(--border-strong,var(--border))}
.rg-linha{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1.5fr) minmax(0,.85fr);gap:.4rem 1.1rem;padding:.9rem 0;border-top:1px solid var(--border);align-items:start}
.rg-linha:first-of-type{border-top:0}
.rg-nome b{display:block;font-size:.95rem;color:var(--text)}
.rg-nome small{display:block;font-size:.78rem;color:var(--text-muted);margin-top:2px}
.rg-meta{display:flex;flex-wrap:wrap;gap:.35rem .6rem;align-items:center;margin-top:.45rem;font-size:.76rem;color:var(--text-muted)}
.rg-selo{display:inline-flex;align-items:center;gap:.3rem;border:1px solid var(--st-neutro-line);background:var(--st-neutro-bg);color:var(--st-neutro-fg);border-radius:999px;padding:0 9px;font-size:.74rem;font-weight:700;line-height:1.7}
.rg-crit{display:block;font-size:.74rem;color:var(--text-muted);margin-top:.25rem;max-width:52ch}
.rg-lk{all:unset;cursor:pointer;color:var(--text-accent);font-weight:700;font-size:.78rem;text-decoration:underline;text-underline-offset:3px;display:inline-flex;gap:.25rem;align-items:center}
.rg-lk:focus-visible{outline:2px solid var(--text-accent);outline-offset:2px}
.rg-trilho>svg{display:block;width:100%;max-width:560px;height:auto;overflow:visible}
.rg-trilho text{fill:var(--text-muted);font-size:11px;font-family:var(--font-body)}
.rg-porque{display:flex;gap:.35rem;align-items:flex-start;font-size:.8rem;color:var(--text-muted);margin:.35rem 0 0;max-width:64ch}
.rg-porque svg{flex-shrink:0;margin-top:2px}
.rg-ressalva{font-size:.78rem;color:var(--text-muted);margin:.35rem 0 0;max-width:64ch}
.rg-valor{text-align:right}
.rg-valor .v{display:block;font-size:1.45rem;font-weight:800;font-variant-numeric:tabular-nums;color:var(--text);line-height:1.15}
.rg-valor .p{display:inline-flex;gap:.3rem;align-items:center;justify-content:flex-end;font-size:.78rem;color:var(--text-muted);margin-top:.2rem}
.rg-valor .c{display:block;font-size:.74rem;color:var(--text-muted);margin-top:.25rem}
.rg-valor .q{display:block;font-size:.74rem;color:var(--text-muted);margin-top:.15rem}
.rg-fontes{grid-column:1/-1;margin-top:.2rem}
.rg-fontes table{margin:0}
.rg-rodape{margin:.6rem 0 0;padding:.55rem .7rem;border:1px solid var(--border-strong,var(--border));border-radius:var(--r-sm);font-size:.78rem;font-style:italic;color:var(--text)}
.rg-so-sem{display:none}
.rg-reportar textarea{min-height:110px;resize:vertical}
@media (max-width:900px){
  .rg-linha{grid-template-columns:minmax(0,1fr) minmax(0,38%)}
  .rg-linha .rg-trilho{grid-column:1/-1;grid-row:2}
  .rg-valor{grid-column:2;grid-row:1}
}
@media (max-width:640px){
  .rg-linha{grid-template-columns:minmax(0,1fr)}
  .rg-linha .rg-trilho{grid-column:1;grid-row:3}
  .rg-valor{grid-column:1;grid-row:2;text-align:left}
  .rg-valor .p{justify-content:flex-start}
}
@media (max-width:520px){.c4-grade2{grid-template-columns:minmax(0,1fr)}.rg-valor .v{font-size:1.2rem}}

/* ── Painel do dono ── */
.pd-cartoes{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.6rem}
.pd-cartao{display:flex;flex-direction:column;gap:.35rem;background:var(--surface);border:1px solid var(--border);border-bottom:3px solid var(--st-neutro-line);border-radius:var(--r-sm);padding:.8rem .9rem;min-width:0;color:var(--text)}
.pd-cartao:first-child{border-bottom-color:var(--rl-a)}
.pd-cartao .q{font-size:.92rem;font-weight:800;color:var(--text);margin:0}
.pd-cartao .l{font-size:.6875rem;font-weight:600;letter-spacing:.13em;text-transform:uppercase;color:var(--text-muted)}
.pd-cartao .v{font-size:1.75rem;font-weight:800;letter-spacing:-.01em;font-variant-numeric:tabular-nums;line-height:1.1;overflow-wrap:anywhere}
.pd-cartao .v .u{font-size:.5em;font-weight:700;color:var(--text-muted);margin-left:.15em}
.pd-cartao .v.neg{color:var(--st-venc-fg)}
.pd-cartao .s{font-size:.78rem;color:var(--text-muted);line-height:1.45}
.pd-cartao .s b{color:var(--text)}
.pd-cartao .s b.neg{color:var(--st-venc-fg)}
.pd-cartao .ir{margin-top:auto;padding-top:.3rem}
.pd-cartao .ir button{all:unset;cursor:pointer;font-size:.78rem;font-weight:700;color:var(--text-accent);display:inline-flex;align-items:center;gap:.2rem;text-decoration:underline;text-underline-offset:3px}
.pd-cartao .ir button:focus-visible{outline:2px solid var(--text-accent);outline-offset:2px}
.pd-chip{display:inline-flex;align-items:center;gap:.3rem;align-self:flex-start;border:1px solid var(--st-neutro-line);background:var(--st-neutro-bg);color:var(--st-neutro-fg);border-radius:999px;padding:1px 9px;font-size:.74rem;font-weight:600;line-height:1.5}
.pd-chip.ruim{border-color:var(--st-venc-line);background:var(--st-venc-bg);color:var(--st-venc-fg)}
.pd-chip.aten{border-color:var(--st-logo-line);background:var(--st-logo-bg);color:var(--st-logo-fg)}
.pd-chip.bom{border-color:var(--st-pago-line);background:var(--st-pago-bg);color:var(--st-pago-fg)}
.pd-dois{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);gap:.75rem}
.pd-lst{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.pd-lst li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:.6rem;align-items:start;padding:.6rem 0;border-top:1px solid var(--border)}
.pd-lst li:first-child{border-top:0}
.pd-lst li b{font-size:.88rem}
.pd-lst li small{display:block;font-size:.76rem;color:var(--text-muted)}
.pd-lst .ic{color:var(--text-muted);margin-top:2px}.pd-lst .ic.ruim{color:var(--st-venc-fg)}
.pd-lst .vl{font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.pd-total{font-size:.78rem;color:var(--text-muted);border-top:1px dashed var(--border-strong,var(--border));padding-top:.5rem;margin-top:.2rem}
.pd-saldo svg{display:block;width:100%;height:auto;overflow:visible}
.pd-saldo text{fill:var(--text-muted);font-size:11px;font-family:var(--font-body)}
@media (max-width:1100px){.pd-cartoes{grid-template-columns:repeat(2,minmax(0,1fr))}.pd-dois{grid-template-columns:minmax(0,1fr)}}
@media (max-width:640px){.pd-cartoes{grid-template-columns:minmax(0,1fr)}}

/* ── Linha do saldo (Painel e Apresentar) ── */
@media (prefers-reduced-motion:no-preference){
  .c4-linha{animation:c4-traco var(--c4-dur,450ms) var(--rl-ease,cubic-bezier(.16,1,.3,1)) backwards}
  .c4-tarde{animation:c4-surge 200ms ease-out both;animation-delay:var(--c4-tarde,300ms)}
}
/* Visível por padrão (impressão, movimento reduzido, sem animação): o tracejado só existe DURANTE o desenho. */
@keyframes c4-traco{from{stroke-dasharray:1;stroke-dashoffset:1}to{stroke-dasharray:1;stroke-dashoffset:0}}
@keyframes c4-surge{from{opacity:0}}

/* ── Apresentar o mês (tela cheia) ── */
/* O diálogo fica fora do .rl (top layer): repete as variáveis do molde (estilos.ts). */
.ap{--rl-a:var(--text-accent);--rl-n1:color-mix(in srgb,var(--text) 74%,var(--surface));--rl-n2:color-mix(in srgb,var(--text) 44%,var(--surface));
  --rl-n3:color-mix(in srgb,var(--text) 16%,var(--surface));--rl-margem:color-mix(in srgb,var(--text-accent) 20%,var(--surface));--rl-ease:cubic-bezier(.16,1,.3,1)}
.ap{position:fixed;inset:0;margin:0;width:100vw;height:100dvh;max-width:none;max-height:none;border:0;padding:0;background:var(--bg);color:var(--text);display:flex;flex-direction:column;overflow:hidden}
.ap:not([open]){display:none}
.ap::backdrop{background:var(--bg)}
.ap-topo{background:var(--pill-active-bg);color:var(--pill-active-fg);padding:.7rem clamp(16px,2vw,24px) 0;display:flex;flex-direction:column;gap:.55rem}
.ap-topo .lin{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem 1rem;justify-content:space-between}
.ap-topo .tit{font-weight:800;font-size:1.05rem;letter-spacing:.01em}
.ap-topo .acts{display:flex;flex-wrap:wrap;gap:.4rem}
.ap-topo .acts button{display:inline-flex;align-items:center;gap:.3rem;border:1px solid currentColor;background:transparent;color:inherit;border-radius:var(--r-sm);font:inherit;font-size:.8rem;font-weight:700;padding:0 .7rem;min-height:36px;cursor:pointer}
.ap-topo .acts button:disabled{opacity:.45;cursor:not-allowed}
.ap-topo button:focus-visible{outline:2px solid currentColor;outline-offset:2px}
.ap-prog{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:4px}
.ap-prog button{all:unset;box-sizing:border-box;width:100%;cursor:pointer;display:block;padding:.45rem .1rem .6rem;border-top:3px solid color-mix(in srgb,currentColor 35%,transparent);font-size:.8rem;font-weight:700;color:inherit}
.ap-prog button.feita,.ap-prog button[aria-current="step"]{border-top-color:currentColor}
.ap-prog button[aria-current="step"]{text-decoration:underline;text-underline-offset:4px}
.ap-prog button:focus-visible{outline:2px solid currentColor;outline-offset:-2px}
.ap-palco{flex:1 1 auto;overflow:auto;touch-action:pan-y}
.ap-cena{max-width:1100px;margin:0 auto;padding:clamp(16px,3vw,40px) clamp(16px,3vw,32px) 2rem;display:flex;flex-direction:column;gap:1rem}
.ap-cena h2{margin:0;font-size:clamp(1.6rem,3.2vw,2.4rem);font-weight:800;letter-spacing:-.02em;line-height:1.1}
.ap-cena h2:focus,.ap-cena h2:focus-visible{outline:none!important;box-shadow:none!important}
.ap-frase{margin:0;font-size:clamp(1rem,1.6vw,1.25rem);line-height:1.55;max-width:62ch}
.ap-grande{font-size:clamp(2.6rem,7vw,4.6rem);font-weight:800;letter-spacing:-.03em;font-variant-numeric:tabular-nums;line-height:1}
.ap-grande small{font-size:.32em;color:var(--text-muted);font-weight:700;margin-left:.3rem;letter-spacing:0}
.ap-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.6rem}
.ap-tiles div{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-sm);padding:.7rem .8rem}
.ap-tiles small{display:block;font-size:.76rem;color:var(--text-muted)}
.ap-tiles b{font-size:1.2rem;font-variant-numeric:tabular-nums}
.ap-nota{font-size:.78rem;color:var(--text-muted);margin:0}
.ap-dec{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.ap-dec li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:.8rem;align-items:start;padding:.85rem 0;border-top:1px solid var(--border)}
.ap-dec li:first-child{border-top:0}
.ap-dec b{font-size:1.02rem}
.ap-dec small{display:block;font-size:.88rem;color:var(--text-muted);margin-top:.15rem}
.ap-dec .ic{color:var(--text-muted);margin-top:2px}.ap-dec .ic.ruim{color:var(--st-venc-fg)}.ap-dec .ic.aten{color:var(--st-logo-fg)}
.ap .rl-graf,.ap .rl-painel{background:var(--surface)}
@media (prefers-reduced-motion:no-preference){
  .ap-entra{animation:ap-entra 260ms var(--rl-ease,cubic-bezier(.16,1,.3,1)) both}
  .ap .rl-degrau{animation-duration:420ms;animation-delay:calc(var(--i,0) * 90ms)}
}
@media (prefers-reduced-motion:reduce){.ap-entra{animation:ap-fade 120ms linear both}}
@keyframes ap-entra{from{opacity:0;transform:translateY(12px)}}
@keyframes ap-fade{from{opacity:0}}
@media (max-width:640px){
  .ap-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
  .ap-prog button{font-size:.72rem}
  .ap-topo .acts button{min-height:44px}
  .ap-topo .acts .so-largo{display:none}
}

@media print{
  .ap,.c4-dlg{display:none!important}
  .rg-lista:not([data-impressao="com"]) .rg-faixa,.rl-painel:has(.rg-lista:not([data-impressao="com"])) .rg-leg .rg-faixa{display:none!important}
  .rg-lista:not([data-impressao="com"]) .rg-so-sem{display:inline}
  .rg-lista:not([data-impressao="com"]) p.rg-so-sem{display:block;margin:0 0 .4rem;font-size:.8rem;font-style:italic}
  .rg-linha{break-inside:avoid}
  .pd-cartao{break-inside:avoid}
}
`;
