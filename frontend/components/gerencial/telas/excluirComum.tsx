"use client";
// Peças COMUNS das 3 telas de Lançamentos › Excluir lançamento (ExcluirTipos, ExcluirRegistros, ExcluirConfirmar), já LIGADAS
// a dados reais por components/exclusao/ExclusaoPage.tsx: moldura de página cheia (um só cabeçalho com as 3 abas — o papel
// decide o rótulo de "Pedidos" × "Meus pedidos", a aba Trilha só existe para o admin — e UMA faixa de aviso), migalhas
// clicáveis, o ícone/destaque de cada tipo e o CSS `.gx-*` (só tokens).
// Este CSS deve migrar para o fim de `.gv-*` em globals.css (prefixo `.gx-`); fica aqui para não tocar em arquivo compartilhado.
import React from "react";
import {
  AlertTriangle, ArrowLeftRight, Baby, Banknote, Boxes, CalendarCheck, CalendarClock, ChevronRight, ClipboardCheck,
  ClipboardList, Dna, Droplets, FileText, FlaskConical, HandCoins, HardHat, Heart, History, Layers, Milk, Package,
  PawPrint, Pill, Receipt, Scale, ShoppingCart, Stethoscope, Syringe, Tags, Trash2, Truck, Users, Wheat,
} from "lucide-react";
import { Selo } from "@/components/gerencial/kit";

export type Icone = React.ComponentType<{ size?: number | string; "aria-hidden"?: boolean }>;

/** Ícone de cada tipo (por id de GET /exclusoes/tipos). Tipo novo sem ícone cai em "documento". */
const ICONES: Record<string, Icone> = {
  diagnostico: Stethoscope, servico: Heart, parto: Baby, controle: Milk, animal: PawPrint, movimento_lote: ArrowLeftRight,
  secagem: Droplets, pesagem_corporal: Scale, evento_manual: CalendarClock,
  sanidade: Syringe, protocolo_sanitario_lancamento: ClipboardCheck, protocolo_iatf_lancamento: FlaskConical,
  calendario_sanitario: CalendarCheck, exame_resultado: Pill,
  financeiro: Receipt, compra_animal: ShoppingCart, compra_semen: Dna, venda_animal: HandCoins, entrega_leite: Truck,
  estoque: Package, movimento_estoque: Boxes,
  diaria: CalendarCheck, diaria_pagamento: Banknote, empreitada: HardHat, contrato: FileText,
  lote: Layers, fornecedor: Truck, pessoa: Users, doenca: AlertTriangle, principio_ativo: Pill, motivo_movimentacao: Tags,
  evento_sanitario: ClipboardList, protocolo_sanitario: ClipboardList, safra: Wheat, todos_lancamentos: Layers,
};
export const iconeDoTipo = (id: string): Icone => ICONES[id] ?? FileText;

/** Blocos com tinta de ouro: os dois tipos que o dono mais procura (apagar a IA inteira × só o exame). */
export const TIPOS_DESTAQUE = new Set(["diagnostico", "servico"]);

export type AbaId = "apagar" | "pedidos" | "trilha";

const ABAS: { id: AbaId; Icone: Icone; admin?: boolean }[] = [
  { id: "apagar", Icone: Trash2 },
  { id: "pedidos", Icone: ClipboardList },
  { id: "trilha", Icone: History, admin: true },
];

/** Moldura de PÁGINA CHEIA (não gaveta): UM só cabeçalho (título + abas na mesma linha) e UMA faixa de aviso. */
export function MolduraExcluir({ children, aba = "apagar", onAba, souAdmin = false, pedidosPendentes = 0 }: {
  children: React.ReactNode; aba?: AbaId; onAba?: (a: AbaId) => void; souAdmin?: boolean; pedidosPendentes?: number;
}) {
  const rotulo = (id: AbaId) => (id === "apagar" ? "Apagar" : id === "pedidos" ? (souAdmin ? "Pedidos" : "Meus pedidos") : "Trilha");
  return (
    <div className="gv-quadro gx-quadro" style={{ ["--gv-largura" as string]: "100%" }}>
      <EstiloExcluir />
      <div className="gx-topo">
        <span className="gx-titulo"><Trash2 size={15} aria-hidden /> Excluir lançamento</span>
        <div className="gx-abas" role="tablist" aria-label="Excluir lançamento">
          {ABAS.filter((a) => !a.admin || souAdmin).map((a) => (
            <button key={a.id} type="button" role="tab" id={`gx-aba-${a.id}`} className="gx-aba" aria-selected={a.id === aba}
              aria-controls="gx-painel" onClick={() => onAba?.(a.id)}>
              <a.Icone size={14} aria-hidden />{rotulo(a.id)}
              {a.id === "pedidos" && pedidosPendentes > 0 && (
                <span className="gx-aba-n" title={`${pedidosPendentes} ${pedidosPendentes === 1 ? "pedido" : "pedidos"} ${souAdmin ? "esperando decisão" : "seu(s) em análise"}`}>{pedidosPendentes}</span>
              )}
            </button>
          ))}
        </div>
        <span className="gv-espaco" style={{ flex: 1 }} />
        {souAdmin
          ? <Selo tom="info" titulo="Administrador: exclui na hora. Os demais usuários enviam um pedido.">Administrador · apaga na hora</Selo>
          : <Selo tom="neutro" titulo="Você envia um pedido de exclusão; o administrador decide.">Você pede · o administrador decide</Selo>}
      </div>
      <div className="gv-corpo gx-corpo" id="gx-painel" role="tabpanel" aria-labelledby={`gx-aba-${aba}`}>
        <div className="gx-aviso" role="note">
          <AlertTriangle size={15} aria-hidden />
          {souAdmin
            ? <span><b>Exclusão apaga de verdade.</b> Você é administrador: exclui na hora, com motivo, e fica registrado na trilha.</span>
            : <span><b>Exclusão apaga de verdade.</b> Você solicita e o administrador decide; acompanhe em Meus pedidos.</span>}
        </div>
        {children}
      </div>
    </div>
  );
}

export type ItemMigalha = { texto: string; aoClicar?: () => void };

/** Migalhas: "Tipos › Diagnósticos de gestação › 11153". O que não é o último item volta um passo. */
export function Migalhas({ itens }: { itens: ItemMigalha[] }) {
  return (
    <nav aria-label="Onde você está" className="gx-migalhas">
      <ol>
        {itens.map((t, i) => {
          const ultimo = i === itens.length - 1;
          return (
            <li key={`${i}-${t.texto}`}>
              {ultimo ? <span aria-current="page">{t.texto}</span> : <button type="button" className="gx-link" onClick={t.aoClicar}>{t.texto}</button>}
              {!ultimo && <ChevronRight size={13} aria-hidden />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function EstiloExcluir() {
  return <style>{CSS}</style>;
}

const CSS = `
.gx-topo { display: flex; align-items: center; gap: 1.1rem; padding: 0 0.9rem; min-height: 2.9rem; background: var(--card-header-bg); color: var(--card-header-fg); border-bottom: 1px solid var(--border); }
.gx-titulo { display: inline-flex; align-items: center; gap: 0.5rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; font-size: 0.78rem; white-space: nowrap; }
.gx-abas { display: flex; align-self: stretch; gap: 0.15rem; }
.gx-aba { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0 0.95rem; background: transparent; border: 0; border-bottom: 2px solid transparent; margin-bottom: -1px;
  color: var(--text-muted); font: inherit; font-size: 0.82rem; font-weight: 600; cursor: pointer; }
.gx-aba:hover { color: var(--text); }
.gx-aba[aria-selected="true"] { color: var(--text); border-bottom-color: var(--ft-ouro); font-weight: 700; }
.gx-aba-n { display: inline-flex; align-items: center; justify-content: center; min-width: 1.15rem; height: 1.15rem; padding: 0 0.3rem; border-radius: 999px; font-size: 0.68rem; font-weight: 800;
  background: var(--ft-ouro-tint); color: var(--ft-ouro-txt); border: 1px solid var(--ft-ouro); font-variant-numeric: tabular-nums; }
.gx-corpo { gap: 0; }
.gx-aviso { display: flex; align-items: center; gap: 0.55rem; padding: 0.45rem 0.7rem; margin-bottom: 0.85rem; border: 1px solid var(--border); border-left: 3px solid var(--ft-verm);
  background: var(--surface-2); border-radius: var(--r-sm); font-size: 0.8rem; color: var(--text); }
.gx-aviso svg { color: var(--ft-verm); flex-shrink: 0; }
.gx-migalhas ol { list-style: none; margin: 0 0 0.75rem; padding: 0; display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap; font-size: 0.82rem; color: var(--text-muted); }
.gx-migalhas li { display: inline-flex; align-items: center; gap: 0.35rem; }
.gx-migalhas [aria-current] { color: var(--text); font-weight: 700; }
.gx-link { background: none; border: 0; padding: 0.15rem 0; font: inherit; color: var(--ft-aco); font-weight: 600; cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }
.gx-link:hover { color: var(--text); }
.gx-seta { display: inline-flex; }

/* Passo 1 — busca + bloco largo + grade de blocos compactos */
.gx-linha-busca { display: flex; gap: 0.6rem; align-items: stretch; }
.gx-busca { position: relative; flex: 0 0 22rem; }
.gx-busca svg { position: absolute; left: 0.6rem; top: 50%; transform: translateY(-50%); color: var(--text-muted); }
.gx-busca input { width: 100%; height: 100%; min-height: 2.6rem; padding: 0.45rem 0.6rem 0.45rem 2rem; background: var(--surface-2); color: var(--text);
  border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); font: inherit; font-size: 0.85rem; }
.gx-busca input:focus { outline: 2px solid var(--ft-ouro); outline-offset: -1px; }
.gx-grupo { display: flex; flex-direction: column; gap: 0.4rem; margin-top: 0.8rem; }
.gx-grupo-cab { display: flex; align-items: center; gap: 0.6rem; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-muted); }
.gx-grupo-cab::before { content: ""; width: 0.55rem; height: 0.55rem; background: var(--gx-cor, var(--border-strong)); border-radius: 1px; }
.gx-grupo-cab::after { content: ""; flex: 1; height: 1px; background: var(--border); }
.gx-grupo-cab span { font-weight: 600; letter-spacing: 0.06em; }
.gx-grade { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 0.5rem; }
.gx-bloco { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; grid-template-areas: "ic nome n" "dica dica dica"; column-gap: 0.55rem; row-gap: 0.2rem; align-items: center;
  min-height: 3.55rem; padding: 0.5rem 0.7rem; text-align: left; cursor: pointer; font: inherit; color: var(--text);
  border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface); }
.gx-bloco:hover { border-color: var(--ft-aco); background: var(--surface-2); }
.gx-bloco:focus-visible { outline: 2px solid var(--ft-ouro); outline-offset: 1px; }
.gx-bloco[data-destaque="true"] { border-color: var(--ft-ouro); background: var(--ft-ouro-tint); box-shadow: inset 0 0 0 1px var(--ft-ouro); }
.gx-bloco-ic { grid-area: ic; display: inline-flex; color: var(--gx-cor, var(--text-muted)); }
.gx-bloco-nome { grid-area: nome; font-size: 0.85rem; font-weight: 700; min-width: 0; display: flex; align-items: center; gap: 0.4rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gx-bloco-n { grid-area: n; font-size: 0.85rem; font-weight: 800; font-variant-numeric: tabular-nums; color: var(--text); }
.gx-bloco-dica { grid-area: dica; font-size: 0.7rem; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gx-todos { flex: 1; min-width: 0; grid-template-columns: auto minmax(0, 1fr) auto; grid-template-areas: "ic nome n" "ic dica n"; border-color: var(--ft-aco); border-width: 1.5px; background: var(--surface); }
.gx-todos .gx-bloco-ic { color: var(--ft-aco); }
.gx-todos .gx-bloco-n { font-size: 1.1rem; }
.gx-cad-cab { display: flex; align-items: center; gap: 0.7rem; width: 100%; padding: 0.55rem 0.7rem; text-align: left; font: inherit; color: var(--text); cursor: pointer;
  border: 1px dashed var(--border-strong, var(--border)); border-radius: var(--r-sm); background: var(--surface-2); }
.gx-cad-cab:hover { border-color: var(--ft-ambar); }
.gx-cad-cab:focus-visible { outline: 2px solid var(--ft-ouro); outline-offset: 1px; }
.gx-cad-cab > span.gx-cad-txt { font-size: 0.78rem; color: var(--text-muted); flex: 1; }
.gx-cad-acao { font-size: 0.78rem; font-weight: 700; color: var(--ft-aco); white-space: nowrap; text-decoration: underline; text-underline-offset: 2px; }

/* Passo 2 — filtros, comparação, tabela, paginação */
.gx-filtros { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 0.75rem; }
.gx-filtros .gv-campo input[type="date"] { width: 9.6rem; }
.gx-filtros .gx-campo-busca { flex: 0 0 24rem; }
.gx-filtros .gx-campo-busca input { width: 100%; }
.gx-compara { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface); }
.gx-compara > div { padding: 0.5rem 0.75rem; display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.78rem; color: var(--text); min-width: 0; }
.gx-compara > div + div { border-left: 1px solid var(--border); background: var(--surface-2); }
.gx-compara-topo { display: flex; align-items: center; gap: 0.5rem; }
.gx-compara p { margin: 0; color: var(--text-muted); font-size: 0.76rem; line-height: 1.45; }
.gx-th-ord { display: inline-flex; align-items: center; gap: 0.25rem; background: none; border: 0; padding: 0; font: inherit; letter-spacing: inherit; text-transform: inherit; color: inherit; cursor: pointer; }
.gx-res-pos { color: var(--ft-verde); font-weight: 800; }
.gx-res-neg { color: var(--ft-verm); font-weight: 800; }
.gx-res-per { color: var(--ft-ambar); font-weight: 800; }
.gx-acao-linha { display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.25rem 0.55rem; min-height: 1.9rem; background: transparent; border: 1px solid var(--border); border-radius: var(--r-sm);
  font: inherit; font-size: 0.76rem; font-weight: 600; color: var(--text-muted); cursor: pointer; text-decoration: none; }
.gx-acao-linha:hover { background: var(--surface-2); color: var(--text); }
.gx-acao-linha[data-perigo="true"] { color: var(--ft-verm); border-color: var(--ft-verm); }
.gx-pag { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; font-size: 0.78rem; color: var(--text-muted); }
.gx-pag b { color: var(--text); font-variant-numeric: tabular-nums; }
.gx-pag-botoes { display: inline-flex; gap: 0.25rem; }
.gx-pag-botoes button { min-width: 1.9rem; height: 1.9rem; padding: 0 0.4rem; background: var(--surface); color: var(--text-muted); border: 1px solid var(--border); border-radius: var(--r-sm); font: inherit; font-size: 0.78rem; font-weight: 600; cursor: pointer; font-variant-numeric: tabular-nums; }
.gx-pag-botoes button[aria-current="page"] { background: var(--ft-ouro-tint); border-color: var(--ft-ouro); color: var(--ft-ouro-txt); font-weight: 800; }
.gx-pag-botoes button:disabled { opacity: 0.45; cursor: default; }

/* Passo 3 — o que será desfeito, impacto, decisão */
.gx-desfazer { display: flex; align-items: center; gap: 1rem; padding: 0.7rem 0.9rem; border: 1px solid var(--border-strong, var(--border)); border-left: 4px solid var(--ft-verm); border-radius: var(--r-sm); background: var(--surface); }
.gx-desfazer-rotulo { font-size: 0.66rem; font-weight: 800; letter-spacing: 0.13em; text-transform: uppercase; color: var(--ft-verm); }
.gx-desfazer-titulo { font-size: 1.05rem; font-weight: 800; margin: 0.1rem 0 0.15rem; }
.gx-desfazer-sub { font-size: 0.8rem; color: var(--text-muted); }
.gx-desfazer-meta { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; margin-top: 0.35rem; font-size: 0.72rem; color: var(--text-muted); }
.gx-desfazer-meta b { color: var(--text); font-variant-numeric: tabular-nums; }
.gx-desfazer-dir { margin-left: auto; display: flex; flex-direction: column; align-items: flex-end; gap: 0.5rem; }
.gx-impacto { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
.gx-imp { border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface); display: flex; flex-direction: column; min-width: 0; }
.gx-imp-cab { display: flex; align-items: center; gap: 0.55rem; padding: 0.45rem 0.7rem; border-bottom: 1px solid var(--border); background: var(--surface-2); }
.gx-imp-cab svg { flex-shrink: 0; }
.gx-imp-cab b { font-size: 0.7rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; }
.gx-imp-cab small { font-size: 0.72rem; color: var(--text-muted); flex: 1; min-width: 0; }
.gx-imp[data-tom="bloqueio"] .gx-imp-cab svg, .gx-imp[data-tom="bloqueio"] .gx-imp-cab b { color: var(--ft-verm); }
.gx-imp[data-tom="apagar"] .gx-imp-cab svg, .gx-imp[data-tom="apagar"] .gx-imp-cab b { color: var(--ft-verm); }
.gx-imp[data-tom="reverter"] .gx-imp-cab svg, .gx-imp[data-tom="reverter"] .gx-imp-cab b { color: var(--ft-aco); }
.gx-imp[data-tom="aviso"] .gx-imp-cab svg, .gx-imp[data-tom="aviso"] .gx-imp-cab b { color: var(--ft-ambar); }
.gx-imp ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.gx-imp li { display: flex; flex-direction: column; gap: 0.1rem; padding: 0.45rem 0.7rem; border-top: 1px solid var(--border); font-size: 0.8rem; }
.gx-imp li:first-child { border-top: 0; }
.gx-imp li span { font-size: 0.74rem; color: var(--text-muted); line-height: 1.4; }
.gx-imp-vazio { margin: 0; padding: 0.55rem 0.7rem; font-size: 0.8rem; color: var(--text-muted); display: flex; align-items: center; gap: 0.4rem; }
.gx-decisao { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: 1rem; align-items: start; }
.gx-niveis { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface); }
.gx-nivel { padding: 0.5rem 0.65rem; display: flex; flex-direction: column; gap: 0.2rem; font-size: 0.74rem; color: var(--text-muted); line-height: 1.4; min-width: 0; }
.gx-nivel + .gx-nivel { border-left: 1px solid var(--border); }
.gx-nivel b { font-size: 0.68rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text); }
.gx-nivel[data-atual="true"] { background: var(--ft-ouro-tint); box-shadow: inset 0 0 0 1px var(--ft-ouro); }
.gx-campo-motivo textarea { width: 100%; resize: vertical; min-height: 3.6rem; font: inherit; }
.gx-perigo { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1.25rem; border-radius: var(--r-sm); font-weight: 700; font-size: 0.875rem; cursor: pointer;
  background: var(--ft-verm); color: var(--surface); border: 1px solid var(--ft-verm); }
.gx-perigo:hover { background: color-mix(in srgb, var(--ft-verm) 85%, black); }
.gx-perigo:disabled { opacity: 0.45; cursor: not-allowed; }
.gx-perigo:focus-visible, .gx-acao-linha:focus-visible { outline: 2px solid var(--ft-ouro); outline-offset: 2px; }
.gx-depois { margin-top: 1.7rem; border: 1px dashed var(--border-strong, var(--border)); border-radius: var(--r-sm); background: var(--surface); }
.gx-depois > .gv-rotulo { padding: 0.55rem 0.9rem; border-bottom: 1px dashed var(--border); }
.gx-depois .gv-barra { position: static; margin: 0; border-top: 0; }
.gx-ok { display: inline-flex; align-items: center; gap: 0.35rem; color: var(--ft-verde); font-weight: 700; }
.gx-lote-det { margin-top: 0.5rem; font-size: 0.78rem; }
.gx-lote-det summary { cursor: pointer; font-weight: 700; color: var(--ft-aco); }
.gx-lote-det ul { margin: 0.2rem 0 0; padding-left: 1.1rem; color: var(--text-muted); }
.gx-ok[data-tom="pedido"] { color: var(--ft-aco); }
.gx-comprovante { font-variant-numeric: tabular-nums; font-weight: 800; padding: 0.05rem 0.4rem; border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); background: var(--surface); }

/* Responsivo: esta tela também roda no app de campo (celular) e dentro de Cadastro. */
@media (max-width: 1280px) { .gx-grade { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 900px) {
  .gx-grade { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .gx-topo { flex-wrap: wrap; gap: 0.4rem 1rem; padding-top: 0.4rem; }
  .gx-linha-busca { flex-wrap: wrap; }
  .gx-busca, .gx-filtros .gx-campo-busca { flex: 1 1 100%; }
  .gx-todos { flex: 1 1 100%; }
  .gx-compara, .gx-impacto, .gx-decisao { grid-template-columns: 1fr; }
  .gx-compara > div + div { border-left: 0; border-top: 1px solid var(--border); }
  .gx-desfazer { flex-direction: column; align-items: flex-start; }
  .gx-desfazer-dir { margin-left: 0; align-items: flex-start; }
}
@media (max-width: 520px) {
  .gx-grade { grid-template-columns: 1fr; }
  .gx-niveis { grid-template-columns: 1fr; }
  .gx-nivel + .gx-nivel { border-left: 0; border-top: 1px solid var(--border); }
  .gx-abas { overflow-x: auto; }
}
.gx-retorno-op { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; padding: 0.5rem 0.75rem; margin-bottom: 0.75rem; border: 1px solid var(--border);
  border-left: 3px solid var(--ft-aco); border-radius: var(--r-sm); background: var(--surface-2); font-size: 0.8rem; }
.gx-th-ord:focus-visible, .gx-link:focus-visible, .gx-pag-botoes button:focus-visible { outline: 2px solid var(--ft-ouro); outline-offset: 2px; }
`;
