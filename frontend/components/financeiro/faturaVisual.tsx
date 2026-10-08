"use client";
// Peças visuais da Gestão de faturas de fornecedor (FaturasView e ModalInserirEmFatura).
// Só aparência: tudo em var(--…) para funcionar nos temas claro, escuro e misto.
// Status sempre com ícone + texto; dourado nunca vira cor de texto (usa --text-accent / --st-*-fg).
import { CheckCircle2, Layers, Lock } from "lucide-react";
import type { FaturaStatus } from "@/lib/api";

export const FATURA_CSS = `
.fv{display:flex;flex-direction:column;gap:.75rem;min-width:0}
.fv-head{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:.6rem 1rem}
.fv-head h2{font-family:var(--font-heading);font-size:1.35rem;font-weight:700;letter-spacing:-.01em;color:var(--text);margin:0;display:flex;flex-wrap:wrap;align-items:center;gap:.4rem .6rem;overflow-wrap:anywhere}
.fv-sub{font-size:.82rem;color:var(--text-muted);margin:.2rem 0 0;max-width:86ch}
.fv-acoes{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center}
.fv-acoes .btn-primary,.fv-acoes .btn-secondary,.fv-acoes .btn-ghost{font-size:.8rem;padding:.4rem .85rem}
.fv-voltar{display:inline-flex;align-items:center;gap:.3rem;font-size:.78rem;padding:.3rem .6rem .3rem .35rem;align-self:flex-start}
.fv-tit{font-size:.75rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text-accent);margin:0}
.fv-sec-topo{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.5rem .75rem;margin-bottom:.45rem}
.fv-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.5rem}
.st-kpi.fv-k-fat{border-bottom-color:var(--st-fat-line)}
.st-kpi .l svg{flex-shrink:0}
.fv-k-fat .l svg{color:var(--st-fat-fg)}.fv-k-aberto .l svg{color:var(--st-aberto-fg)}.fv-k-pago .l svg{color:var(--st-pago-fg)}
.fv-seg{display:inline-flex;border:1px solid var(--border-strong,var(--border));border-radius:var(--r-sm);flex-wrap:wrap;max-width:100%;background:var(--surface)}
.fv-seg button{border:0;background:transparent;color:var(--text-muted);font:inherit;font-size:.8rem;font-weight:600;padding:0 .75rem;min-height:34px;cursor:pointer;white-space:nowrap}
.fv-seg button+button{border-left:1px solid var(--border-strong,var(--border))}
.fv-seg button:hover{color:var(--text);background:var(--surface-2)}
.fv-seg button[aria-pressed="true"]{background:var(--pill-active-bg);color:var(--pill-active-fg);box-shadow:inset 0 0 0 1px var(--pill-active-border)}
.fv-seg .n{font-weight:500;opacity:.85;font-variant-numeric:tabular-nums}
.fv-pan{border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface);box-shadow:var(--shadow-sm);padding:.8rem .95rem;min-width:0}
.fv-tw{overflow-x:auto;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface);max-width:100%}
.fv-tw .fazenda-table{margin:0;font-size:.84rem}
.fv-tw .fazenda-table td{vertical-align:middle}
.fv-tw .fazenda-table th.r,.fv-tw .fazenda-table td.r,.fv-modal .r{text-align:right}
.fv-num{font-variant-numeric:tabular-nums;white-space:nowrap}
.fv-forte{font-weight:700}
.fv-lk{background:none;border:0;padding:0;font:inherit;font-weight:700;color:var(--text);cursor:pointer;text-align:left;text-decoration:underline;text-decoration-color:var(--border-strong,var(--border));text-underline-offset:3px;overflow-wrap:anywhere}
.fv-lk:hover{text-decoration-color:currentColor}
.fv-tw td.fv-col-fat{min-width:180px}
.fv-t2{display:block;font-size:.74rem;color:var(--text-muted);margin-top:1px}
.fv-mini{font-size:.76rem;padding:.3rem .7rem;white-space:nowrap}
.fv-ciclo{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}
.fv-passo{position:relative;display:grid;justify-items:start;align-content:start;gap:2px;padding-right:12px;min-width:0}
.fv-passo:not(:last-child)::after{content:"";position:absolute;left:38px;right:10px;top:15px;height:2px;background:var(--border-strong,var(--border))}
.fv-passo.feito:not(:last-child)::after{background:var(--st-pago-line)}
.fv-bola{width:32px;height:32px;border-radius:50%;border:2px solid var(--border-strong,var(--border));background:var(--surface);display:grid;place-items:center;color:var(--text-muted);font-weight:700;font-size:.85rem;position:relative;z-index:1}
.fv-passo.feito .fv-bola{background:var(--st-pago-bg);border-color:var(--st-pago-line);color:var(--st-pago-fg)}
.fv-passo.atual .fv-bola{border-color:var(--text-accent);color:var(--text-accent);background:var(--surface);box-shadow:0 0 0 4px color-mix(in srgb,var(--text-accent) 20%,transparent)}
.fv-passo .fv-rot{font-size:.95rem;font-weight:600;color:var(--text);margin-top:5px;text-decoration:none}
.fv-passo.atual .fv-rot{font-weight:800}
.fv-passo .fv-dt{font-size:.75rem;color:var(--text-muted);font-variant-numeric:tabular-nums}
.fv-passo .fv-agora{font-size:.66rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--text-accent)}
.fv-fatos{display:flex;flex-wrap:wrap;gap:.65rem 1.75rem;margin:0}
.fv-fatos>div{display:grid;gap:1px;min-width:0}
.fv-fatos dt{font-size:.74rem;color:var(--text-muted);font-weight:600}
.fv-fatos dd{margin:0;font-weight:700;font-size:1rem;font-variant-numeric:tabular-nums;display:flex;flex-wrap:wrap;align-items:center;gap:.35rem;color:var(--text)}
.fv-fatos dd.fraco{font-weight:500;font-size:.85rem;color:var(--text-muted)}
.fv-sep{border:0;border-top:1px solid var(--border);margin:.8rem 0}
.fv-ok,.fv-ruim{display:inline-flex;align-items:center;gap:4px;font-size:.78rem;font-weight:700}
.fv-ok{color:var(--st-pago-fg)}.fv-ruim{color:var(--st-venc-fg)}
.fv-delta{display:inline-flex;align-items:center;gap:4px;font-size:.72rem;font-weight:700;border-radius:999px;padding:0 8px;border:1px solid var(--st-logo-line);background:var(--st-logo-bg);color:var(--st-logo-fg);white-space:nowrap;line-height:1.5}
.fv-delta.desc{border-color:var(--st-pago-line);background:var(--st-pago-bg);color:var(--st-pago-fg)}
.fv-sit{display:flex;flex-wrap:wrap;align-items:center;gap:.3rem .4rem}
.fv-barra{display:flex;align-items:center;gap:.5rem;min-width:120px}
.fv-barra>span{flex:1;height:7px;border-radius:99px;background:var(--st-neutro-bg);border:1px solid var(--st-neutro-line);overflow:hidden}
.fv-barra i{display:block;height:100%;background:var(--text-accent)}
.fv-barra small{min-width:34px;text-align:right;font-size:.74rem;color:var(--text-muted);font-variant-numeric:tabular-nums}
.fv-lbl{display:block;font-size:.72rem;font-weight:600;color:var(--text-muted);margin-bottom:.2rem}
.fv-in{width:100%;background:var(--surface-2);color:var(--text);border:1px solid var(--border);border-radius:var(--r-sm);padding:.4rem .5rem;font-size:.82rem;min-height:36px;font-family:inherit}
.fv-in:disabled{opacity:.6;cursor:not-allowed}
.fv-in.dir{text-align:right}
.fv-grupo{font-size:.78rem;font-weight:700;color:var(--text);margin:1rem 0 .4rem}
.fv-grupo small{display:block;font-weight:400;color:var(--text-muted);font-size:.74rem}
.fv-opcoes{display:flex;flex-wrap:wrap;gap:.5rem}
.fv-opcao{display:flex;gap:.45rem;align-items:center;border:1px solid var(--border);border-radius:var(--r-sm);padding:.4rem .75rem;font-size:.82rem;min-height:36px;cursor:pointer;background:var(--surface);color:var(--text);margin:0}
.fv-opcao:has(input:checked){border-color:var(--text-accent);background:var(--surface-2);font-weight:600}
.fv-opcao:has(input:disabled){opacity:.55;cursor:not-allowed}
.fv-opcao:focus-within{box-shadow:0 0 0 2px var(--bg),0 0 0 4px var(--text-accent)}
.fv-opcao input{accent-color:var(--text-accent);width:16px;height:16px;flex-shrink:0}
.fv-aviso{display:flex;gap:.55rem;align-items:flex-start;border:1px solid var(--st-aberto-line);background:var(--st-aberto-bg);color:var(--st-aberto-fg);border-radius:var(--r-sm);padding:.55rem .75rem;font-size:.8rem;margin-top:.75rem}
.fv-aviso.logo{border-color:var(--st-logo-line);background:var(--st-logo-bg);color:var(--st-logo-fg)}
.fv-aviso.ok{border-color:var(--st-pago-line);background:var(--st-pago-bg);color:var(--st-pago-fg)}
.fv-aviso.venc{border-color:var(--st-venc-line);background:var(--st-venc-bg);color:var(--st-venc-fg)}
.fv-aviso svg{flex-shrink:0;margin-top:2px}
.fv-aviso b{display:block;font-weight:700}
.fv-aviso p{margin:.15rem 0 0}
.fv-aviso ul{margin:.3rem 0 0;padding-left:1rem}
.fv-rodape{display:flex;flex-wrap:wrap;gap:.6rem;margin-top:1rem;align-items:center}
.btn-ghost.fv-perigo{color:var(--st-venc-fg);border-color:var(--st-venc-line)}
.btn-ghost.fv-perigo:hover{background:var(--st-venc-bg);color:var(--st-venc-fg)}
.btn-ghost.fv-perigo-cheio{background:var(--st-venc-bg);color:var(--st-venc-fg);border-color:var(--st-venc-line);font-weight:700;display:inline-flex;align-items:center;gap:.4rem}
.btn-ghost.fv-perigo-cheio:hover{background:color-mix(in srgb,var(--st-venc-bg) 80%,var(--st-venc-line))}
.btn-ghost.fv-btn{display:inline-flex;align-items:center;gap:.4rem}
.fv-modal p{font-size:.84rem;color:var(--text)}
.fv-modal .fv-nota{font-size:.78rem;color:var(--text-muted);margin-top:.4rem}
.fv-hist{list-style:none;margin:0;padding:0}
.fv-hist li{display:grid;grid-template-columns:28px minmax(0,1fr);gap:.6rem;align-items:start;padding:.55rem 0;border-bottom:1px solid var(--border)}
.fv-hist li:last-child{border-bottom:0}
.fv-hist .ic{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;border:1px solid var(--st-neutro-line);background:var(--st-neutro-bg);color:var(--st-neutro-fg)}
.fv-hist .ic.fat{border-color:var(--st-fat-line);background:var(--st-fat-bg);color:var(--st-fat-fg)}
.fv-hist .ic.aberto{border-color:var(--st-aberto-line);background:var(--st-aberto-bg);color:var(--st-aberto-fg)}
.fv-hist .ic.pago{border-color:var(--st-pago-line);background:var(--st-pago-bg);color:var(--st-pago-fg)}
.fv-hist .ic.venc{border-color:var(--st-venc-line);background:var(--st-venc-bg);color:var(--st-venc-fg)}
.fv-hist b{display:block;font-size:.86rem;color:var(--text)}
.fv-hist .det{display:block;font-size:.8rem;color:var(--text);margin-top:1px;overflow-wrap:anywhere}
.fv-hist small{display:block;font-size:.74rem;color:var(--text-muted);margin-top:2px}
.fv-vazio{display:flex;flex-direction:column;align-items:center;gap:.35rem;text-align:center;padding:1.4rem 1rem;color:var(--text-muted);border:1px dashed var(--border-strong,var(--border));border-radius:var(--r-sm);background:var(--surface-2);font-size:.82rem}
.fv-vazio b{color:var(--text);font-size:.92rem}
.fv-msg{font-size:.82rem;color:var(--text-muted);margin:0}
.fv-checks{max-height:220px;overflow-y:auto;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface)}
.fv-check{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:.6rem;align-items:center;padding:.45rem .7rem;font-size:.82rem;border-bottom:1px solid var(--border);cursor:pointer;margin:0;color:var(--text)}
.fv-check:last-child{border-bottom:0}
.fv-check:hover{background:var(--surface-2)}
.fv-check:has(input:checked){background:var(--sel-row)}
.fv-check input{accent-color:var(--text-accent);width:16px;height:16px}
.fv-check:focus-within{box-shadow:inset 0 0 0 2px var(--text-accent)}
@media (max-width:767px){
  .fv-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  .fv-seg{display:flex;width:100%}.fv-seg button{flex:1 1 auto;padding:0 .45rem}
  .fv button:not(.fv-lk),.fv-modal button,.fv-in,.fv-opcao,.fv-check,.fv-voltar{min-height:44px}
  .fv-in{font-size:16px}
  .fv-acoes{width:100%}
  .fv-passo{padding-right:6px}
  .fv-passo:not(:last-child)::after{left:36px;right:4px}
  .fv-passo .fv-rot{font-size:.85rem}
  .fv-fatos{gap:.6rem 1.2rem}
  .fv-fatos>div{flex:1 1 40%}
}
`;

/** Injeta os estilos (idempotente na prática: tags iguais não conflitam). */
export function EstiloFatura() {
  return <style>{FATURA_CSS}</style>;
}

/** Situação da fatura: Aberta = fat (camadas), Fechada = aberto (cadeado), Paga = pago (check). */
export function PilulaFatura({ s }: { s: FaturaStatus }) {
  if (s === "paga") return <span className="st-pill pago"><CheckCircle2 size={12} aria-hidden />Paga</span>;
  if (s === "fechada") return <span className="st-pill aberto"><Lock size={12} aria-hidden />Fechada</span>;
  return <span className="st-pill fat"><Layers size={12} aria-hidden />Aberta</span>;
}
