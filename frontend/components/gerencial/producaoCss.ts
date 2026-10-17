// CSS comum das telas gerenciais de Lançamentos › Produção (Qualidade do leite, Indução de lactação, Venda mensal, BST).
// Vai num <style> dentro de cada tela (em vez de editar globals.css, que outros agentes alteram em paralelo). Só tokens.
// `.gp-raiz` envolve a tela e resolve onde ela roda:
//  · gaveta de lançamento (padding 0.9rem): a barra do pé fica colada na borda da gaveta (regra `.gaveta-lancamento-corpo`);
//  · página/card (Lançamentos, Agenda, Protocolos): a barra gruda no pé da janela sem sair da moldura;
//  · app de campo (`.mob-form-embutido`): toque grande, barra no fluxo (sem fixar sobre a barra de abas do app).
export const CSS_RAIZ = `
.gp-raiz { display: flex; flex-direction: column; font-size: 0.85rem; color: var(--text); min-width: 0; }
.gp-raiz .gv-barra { bottom: 0; margin: 0.9rem 0 0; border: 1px solid var(--border); }
.gaveta-lancamento-corpo .gp-raiz .gv-barra { bottom: -0.9rem; margin: 0.9rem -0.9rem -0.9rem; border: 0; border-top: 1px solid var(--border); }
.gp-raiz .gv-barra-retorno { background: var(--surface); }
.gp-btn { display: inline-flex; align-items: center; gap: 0.4rem; min-height: 2rem; padding: 0.3rem 0.75rem; font: inherit; font-size: 0.78rem; font-weight: 600; cursor: pointer;
  color: var(--text); background: var(--surface); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); }
.gp-btn:hover:not(:disabled) { background: var(--surface-2); }
.gp-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.gp-btn:focus-visible, .gp-raiz .btn-ghost:focus-visible, .gp-raiz .btn-primary-gold:focus-visible { outline: 2px solid var(--ft-ouro); outline-offset: 1px; }
.gp-perigo { color: var(--ft-verm); }
.gp-link { background: none; border: 0; padding: 0.2rem 0.1rem; font: inherit; font-size: 0.8rem; font-weight: 700; color: var(--ft-ouro-txt); text-decoration: underline; text-underline-offset: 2px; cursor: pointer; }
.gp-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.gp-muda { color: var(--text-muted); }
.gp-ok { color: var(--ft-verde); font-weight: 700; }
.gp-erro { color: var(--ft-verm); font-weight: 700; }
.gp-contagem { font-size: 0.8rem; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.gp-busca { position: relative; display: flex; align-items: center; }
.gp-busca svg { position: absolute; left: 0.6rem; color: var(--text-muted); pointer-events: none; }
.gp-busca input { padding-left: 2rem; width: 17rem; max-width: 100%; background: var(--surface-2); color: var(--text); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); font-size: 0.85rem; min-height: 2.1rem; }
.gp-busca input:focus { outline: 2px solid var(--ft-ouro); outline-offset: -1px; }
.gp-vazio { display: flex; flex-direction: column; align-items: center; gap: 0.25rem; padding: 1.6rem 1rem; border: 1px dashed var(--border-strong, var(--border)); border-radius: var(--r-sm); background: var(--surface-2); text-align: center; }
.gp-vazio b { font-size: 0.85rem; } .gp-vazio span { font-size: 0.78rem; color: var(--text-muted); }
.gp-solta { display: flex; flex-direction: column; justify-content: center; gap: 0.15rem; padding: 0.9rem 1.1rem; border: 1.5px dashed var(--border-strong, var(--border)); border-radius: var(--r-sm); background: var(--surface-2); min-height: 4.2rem; }
.gp-solta[data-sobre="true"] { border-color: var(--ft-ouro); background: var(--ft-ouro-tint); }
.gp-solta b { font-size: 0.85rem; word-break: break-all; } .gp-solta span { font-size: 0.74rem; color: var(--text-muted); }
.gp-raiz table input[type="checkbox"] { width: 1.05rem; height: 1.05rem; }
.mob-form-embutido .gp-raiz input[type="checkbox"], .mob-form-embutido .gp-raiz input[type="radio"] { padding: 0 !important; min-height: 0 !important; width: 1.4rem; height: 1.4rem; }
.mob-form-embutido .gp-raiz th button, .mob-form-embutido .gp-raiz .gp-compacto button { min-height: 0; }
@media (max-width: 767px) { .gp-raiz .gv-barra, .gaveta-lancamento-corpo .gp-raiz .gv-barra { position: static; } }
@media (max-width: 899px) { .gp-raiz .gv-faixa { grid-auto-flow: row; grid-template-columns: repeat(2, minmax(0, 1fr)); } .gp-raiz .gv-faixa-item { border-bottom: 1px solid var(--border); } }
`;
