"use client";
// Peças COMUNS das 3 telas de Lançamentos › Excluir lançamento (ExcluirTipos, ExcluirRegistros, ExcluirConfirmar):
// moldura de página cheia (um só cabeçalho com as 3 abas), faixa de aviso única, migalhas, os tipos (dados de exemplo
// no formato de GET /exclusoes/tipos + META_TIPOS) e o CSS `.gx-*` (só tokens). Só apresentação.
//
// O que a versão ligada a dados (components/exclusao/ExclusaoPage.tsx) precisa preservar — vale para as 3 telas:
//  • Abas: Apagar / Pedidos (admin; operador vê "Meus pedidos") / Trilha (só admin). O contador de Pedidos = pendentes.
//  • Tipos vêm de GET /exclusoes/tipos (id, label, sem_filtro_data, dominio, plural, dica, cadastro, contagem), já
//    filtrados por `ocultarTipos` (prop de FormExclusao). Tipo sem META (os 11 do REGISTRO: secagem, movimento_lote,
//    safra, diárias…) hoje chega SEM dominio/plural/dica/contagem → completar META_TIPOS no backend (ver relatório).
//  • Aviso único: admin "exclui na hora"; os demais "solicitam e o administrador decide" (texto muda por papel).
//  • Este CSS deve migrar para o fim de `.gv-*` em globals.css (prefixo `.gx-`); está aqui só para a prévia não tocar
//    em arquivo compartilhado.
import React from "react";
import {
  AlertTriangle, ArrowLeftRight, Baby, Banknote, Boxes, CalendarCheck, CalendarClock, ChevronRight, ClipboardCheck,
  ClipboardList, Dna, Droplets, FileText, FlaskConical, HandCoins, HardHat, Heart, History, Layers, Milk, Package,
  PawPrint, Pill, Receipt, Scale, ShoppingCart, Stethoscope, Syringe, Tags, Trash2, Truck, Users, Wheat,
} from "lucide-react";
import { Selo } from "@/components/gerencial/kit";

export type Dominio = "reb" | "san" | "fin" | "est" | "pes" | "cad";
export type Icone = React.ComponentType<{ size?: number | string; "aria-hidden"?: boolean }>;

export type TipoEx = {
  id: string;
  label: string;          // texto completo (TIPOS[].label) — vai no título/tooltip e na migalha
  plural: string;         // META_TIPOS.plural — nome curto do bloco
  dica: string;           // META_TIPOS.dica — uma linha
  dominio: Dominio;
  cadastro?: boolean;     // META_TIPOS.cadastro — vai para o grupo recolhido
  contagem: number | null; // GET /tipos → contagem (hoje só 10 tipos contam; os demais viriam null)
  sem_filtro_data?: boolean;
  Icone: Icone;
  novo?: boolean;         // só apresentação: selo "Novo" no tipo recém-criado
  destaque?: boolean;     // só apresentação: bloco com tinta de ouro (os tipos que o dono mais procura)
};

export const DOMINIOS: { id: Dominio; nome: string; cor: string }[] = [
  { id: "reb", nome: "Rebanho e reprodução", cor: "var(--cat-reproducao)" },
  { id: "san", nome: "Sanidade", cor: "var(--cat-sanidade)" },
  { id: "fin", nome: "Financeiro", cor: "var(--cat-financeiro)" },
  { id: "est", nome: "Estoque", cor: "var(--cat-estoque)" },
  { id: "pes", nome: "Pessoal", cor: "var(--cat-gestao)" },
  { id: "cad", nome: "Cadastros", cor: "var(--cat-acesso)" },
];

// Os 34 tipos de GET /exclusoes/tipos (23 de TIPOS + 12 do REGISTRO, menos o "todos_lancamentos" que é o bloco largo)
// com plural/dica de META_TIPOS. Onde o texto da dica foi ENCURTADO para caber em uma linha, o original está no comentário.
export const TIPOS: TipoEx[] = [
  // Rebanho e reprodução
  { id: "diagnostico", label: "Diagnóstico de gestação (toque, retoque, perda)", plural: "Diagnósticos de gestação",
    dica: "Desfaz só o exame; a inseminação fica.", // original: "Desfaz só o exame (toque, retoque ou perda); a inseminação fica."
    dominio: "reb", contagem: 1126, Icone: Stethoscope, novo: true, destaque: true },
  { id: "servico", label: "Serviço / IA (a inseminação inteira)", plural: "Serviços / IA",
    dica: "Apaga a IA inteira, com o diagnóstico dela.", // original: "Apaga a inseminação inteira, com o diagnóstico dela; a anterior volta a valer."
    dominio: "reb", contagem: 1840, Icone: Heart, destaque: true },
  { id: "parto", label: "Parto / nascimento", plural: "Partos", dica: "Remove a lactação e a cria gerada.", dominio: "reb", contagem: 487, Icone: Baby },
  { id: "controle", label: "Controle leiteiro", plural: "Controles leiteiros", dica: "Some o registro de produção.", dominio: "reb", contagem: 3420, Icone: Milk },
  { id: "animal", label: "Animal (ficha)", plural: "Animais", dica: "Apaga a ficha e todo o histórico.", dominio: "reb", contagem: 612, Icone: PawPrint },
  { id: "movimento_lote", label: "Movimentação entre lotes", plural: "Movimentações de lote", dica: "O animal volta ao lote anterior.", dominio: "reb", contagem: 2135, Icone: ArrowLeftRight, sem_filtro_data: false },
  { id: "secagem", label: "Secagem", plural: "Secagens", dica: "A lactação é reaberta.", dominio: "reb", contagem: 238, Icone: Droplets },
  { id: "pesagem_corporal", label: "Pesagem corporal", plural: "Pesagens", dica: "Some o peso lançado.", dominio: "reb", contagem: 1207, Icone: Scale },
  { id: "evento_manual", label: "Evento manual da agenda", plural: "Eventos da agenda", dica: "Some o evento da agenda.", dominio: "reb", contagem: 64, Icone: CalendarClock },
  // Sanidade
  { id: "sanidade", label: "Sanidade", plural: "Sanidades", dica: "O remédio volta ao estoque.", dominio: "san", contagem: 2906, Icone: Syringe },
  { id: "protocolo_sanitario_lancamento", label: "Aplicação de protocolo sanitário (curativo/vacina)", plural: "Aplicações de protocolo", dica: "A aplicação sai; o protocolo continua.", dominio: "san", contagem: 312, Icone: ClipboardCheck },
  { id: "protocolo_iatf_lancamento", label: "Aplicação de protocolo hormonal (IATF)", plural: "Aplicações de IATF", dica: "A aplicação sai; o protocolo continua.", dominio: "san", contagem: 145, Icone: FlaskConical },
  { id: "calendario_sanitario", label: "Evento do calendário sanitário", plural: "Eventos do calendário", dica: "Some o evento do calendário.", dominio: "san", contagem: 58, Icone: CalendarCheck },
  { id: "exame_resultado", label: "Resultado de exame preventivo", plural: "Resultados de exame", dica: "Some o resultado lançado.", dominio: "san", contagem: 174, Icone: Pill },
  // Financeiro
  { id: "financeiro", label: "Financeiro", plural: "Lançamentos financeiros", dica: "Apaga a nota e suas parcelas.", dominio: "fin", contagem: 4718, Icone: Receipt },
  { id: "compra_animal", label: "Compra de animal", plural: "Compras de animal", dica: "Apaga a compra e o lançamento financeiro.", dominio: "fin", contagem: 36, Icone: ShoppingCart },
  { id: "compra_semen", label: "Compra de sêmen", plural: "Compras de sêmen", dica: "Apaga a compra; o estoque volta.", dominio: "fin", contagem: 22, Icone: Dna },
  { id: "venda_animal", label: "Venda de animal", plural: "Vendas de animal", dica: "Apaga a venda e o lançamento financeiro.", dominio: "fin", contagem: 71, Icone: HandCoins },
  { id: "entrega_leite", label: "Entrega de leite (mensal)", plural: "Entregas de leite", dica: "Some a entrega do mês.", dominio: "fin", contagem: 34, Icone: Truck },
  // Estoque
  { id: "estoque", label: "Estoque", plural: "Movimentos de estoque", dica: "O estoque volta ao valor anterior.", dominio: "est", contagem: 3870, Icone: Package },
  { id: "movimento_estoque", label: "Movimento de estoque (entrada/saída manual)", plural: "Entradas e saídas manuais", dica: "O saldo volta ao anterior.", dominio: "est", contagem: 912, Icone: Boxes },
  // Pessoal
  { id: "diaria", label: "Diária", plural: "Diárias", dica: "Some a diária lançada.", dominio: "pes", contagem: 214, Icone: CalendarCheck },
  { id: "diaria_pagamento", label: "Pagamento de diária", plural: "Pagamentos de diária", dica: "O pagamento volta a pendente.", dominio: "pes", contagem: 128, Icone: Banknote },
  { id: "empreitada", label: "Empreitada", plural: "Empreitadas", dica: "Some a empreitada lançada.", dominio: "pes", contagem: 17, Icone: HardHat },
  { id: "contrato", label: "Contrato (Pessoal)", plural: "Contratos", dica: "Some o contrato lançado.", dominio: "pes", contagem: 9, Icone: FileText },
  // Cadastros (recolhidos por padrão: raros e perigosos)
  { id: "lote", label: "Lote (cadastro)", plural: "Lotes", dica: "Os animais do lote ficam sem lote.", dominio: "cad", cadastro: true, contagem: 14, Icone: Layers, sem_filtro_data: true },
  { id: "fornecedor", label: "Fornecedor/fabricante/cliente/corretor", plural: "Fornecedores", dica: "As notas continuam, mas perdem a ligação.", dominio: "cad", cadastro: true, contagem: 87, Icone: Truck, sem_filtro_data: true },
  { id: "pessoa", label: "Pessoa", plural: "Pessoas", dica: "Só sai se não tiver folha nem vale.", dominio: "cad", cadastro: true, contagem: 23, Icone: Users, sem_filtro_data: true },
  { id: "doenca", label: "Doença", plural: "Doenças", dica: "Protocolos perdem a ligação.", dominio: "cad", cadastro: true, contagem: 19, Icone: AlertTriangle, sem_filtro_data: true },
  { id: "principio_ativo", label: "Princípio ativo", plural: "Princípios ativos", dica: "Cadastro auxiliar.", dominio: "cad", cadastro: true, contagem: 41, Icone: Pill, sem_filtro_data: true },
  { id: "motivo_movimentacao", label: "Motivo de movimentação", plural: "Motivos de movimentação", dica: "Cadastro auxiliar.", dominio: "cad", cadastro: true, contagem: 12, Icone: Tags, sem_filtro_data: true },
  { id: "evento_sanitario", label: "Evento sanitário", plural: "Eventos sanitários", dica: "Cadastro auxiliar.", dominio: "cad", cadastro: true, contagem: 26, Icone: ClipboardList, sem_filtro_data: true },
  { id: "protocolo_sanitario", label: "Protocolo sanitário (cadastro)", plural: "Protocolos sanitários", dica: "Cadastro auxiliar.", dominio: "cad", cadastro: true, contagem: 11, Icone: ClipboardList, sem_filtro_data: true },
  { id: "safra", label: "Safra (Agricultura)", plural: "Safras", dica: "Some a safra e o que dela depende.", dominio: "cad", cadastro: true, contagem: 6, Icone: Wheat },
];

export const TODOS: TipoEx = {
  id: "todos_lancamentos", label: "Todos os lançamentos (mais recentes primeiro)", plural: "Todos os lançamentos",
  dica: "Busca em todos os lançamentos — para quando você não sabe em qual tipo foi lançado.",
  dominio: "reb", contagem: 15274, Icone: Layers,
};

export const fmtN = (n: number | null) => (n == null ? "—" : n.toLocaleString("pt-BR"));
export const nomeCurto = (t: TipoEx) => t.plural.charAt(0).toUpperCase() + t.plural.slice(1);

export type AbaId = "apagar" | "pedidos" | "trilha";

const ABAS: { id: AbaId; rotulo: string; Icone: Icone }[] = [
  { id: "apagar", rotulo: "Apagar", Icone: Trash2 },
  { id: "pedidos", rotulo: "Pedidos", Icone: ClipboardList },
  { id: "trilha", rotulo: "Trilha", Icone: History },
];

/** Moldura de PÁGINA CHEIA (não gaveta): UM só cabeçalho (título + abas na mesma linha) e UMA faixa de aviso. */
export function MolduraExcluir({ children, pedidosPendentes = 2 }: { children: React.ReactNode; pedidosPendentes?: number }) {
  return (
    <div className="gv-quadro gx-quadro" style={{ ["--gv-largura" as string]: "100%" }}>
      <EstiloExcluir />
      <div className="gx-topo">
        <span className="gx-titulo"><Trash2 size={15} aria-hidden /> Excluir lançamento</span>
        <div className="gx-abas" role="tablist" aria-label="Excluir lançamento">
          {ABAS.map((a) => (
            <button key={a.id} type="button" role="tab" className="gx-aba" aria-selected={a.id === "apagar"}>
              <a.Icone size={14} aria-hidden />{a.rotulo}
              {a.id === "pedidos" && pedidosPendentes > 0 && <span className="gx-aba-n" title={`${pedidosPendentes} pedidos esperando decisão`}>{pedidosPendentes}</span>}
            </button>
          ))}
        </div>
        <span className="gv-espaco" style={{ flex: 1 }} />
        <Selo tom="info" titulo="Administrador: exclui na hora. Os demais usuários enviam um pedido.">Administrador · apaga na hora</Selo>
      </div>
      <div className="gv-corpo gx-corpo">
        <div className="gx-aviso" role="note">
          <AlertTriangle size={15} aria-hidden />
          <span><b>Exclusão apaga de verdade.</b> Administradores excluem na hora; os demais usuários só solicitam e o administrador decide.</span>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Migalhas: "Tipos › Diagnósticos de gestação › 11153". O que não é o último item volta um passo. */
export function Migalhas({ itens }: { itens: string[] }) {
  return (
    <nav aria-label="Onde você está" className="gx-migalhas">
      <ol>
        {itens.map((t, i) => {
          const ultimo = i === itens.length - 1;
          return (
            <li key={t}>
              {ultimo ? <span aria-current="page">{t}</span> : <button type="button" className="gx-link">{t}</button>}
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
.gx-comprovante { font-variant-numeric: tabular-nums; font-weight: 800; padding: 0.05rem 0.4rem; border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); background: var(--surface); }
`;
