import { HeartPulse, Milk, Syringe, Wheat, Landmark, Boxes, Baby, ListChecks } from "lucide-react";
import type { LucideIcon } from "lucide-react";

// Dados estáticos da landing pública (T8) — sem chamada de API: é vitrine de
// marketing, os mesmos 8 módulos comerciais e os mesmos 5 planos que o resto
// do produto já usa (não é conteúdo inventado para esta tela).

export type ModuloLanding = { chave: string; titulo: string; texto: string; icon: LucideIcon; cor: string };

// Os 8 módulos, na mesma nomenclatura e no mesmo agrupamento que
// ROTA_MODULO/MODULO_CONTRATO (lib/api.ts) e a Sidebar já usam — "Central de
// Protocolos" é o rótulo real da Sidebar (não "Protocolos"), e como cruza
// Reprodução/Sanidade/Produção não tem uma cor --cat-* própria: leva o
// dourado "sem categoria", mesmo tratamento que já recebe no Menu do app
// (ver app/app/menu/page.tsx::itemProtocolos).
export const MODULOS: ModuloLanding[] = [
  { chave: "reproducao", titulo: "Reprodução", texto: "Protocolos IATF, inseminação, diagnóstico de gestação e o histórico reprodutivo completo de cada matriz.", icon: HeartPulse, cor: "var(--cat-reproducao)" },
  { chave: "producao", titulo: "Produção", texto: "Controle leiteiro, qualidade do leite (CCS/CPP/gordura/proteína), secagem e indicadores de produtividade.", icon: Milk, cor: "var(--cat-producao)" },
  { chave: "sanidade", titulo: "Sanidade", texto: "Calendário sanitário preventivo, aplicações e o histórico clínico de cada animal do rebanho.", icon: Syringe, cor: "var(--cat-sanidade)" },
  { chave: "alimentacao", titulo: "Alimentação", texto: "Dieta por lote, consumo e necessidade mensal de ração calculados sozinhos, sem planilha.", icon: Wheat, cor: "var(--cat-alimentacao)" },
  { chave: "financeiro", titulo: "Financeiro", texto: "Contas a pagar/receber, fluxo de caixa, DRE, RMCA e o custo real por litro, por vaca e por lote.", icon: Landmark, cor: "var(--cat-financeiro)" },
  { chave: "estoque", titulo: "Estoque", texto: "Insumos com estoque mínimo e alerta automático de compra — nunca mais falta ração ou remédio.", icon: Boxes, cor: "var(--cat-estoque)" },
  { chave: "recria", titulo: "Recria", texto: "Bezerras e novilhas acompanhadas do nascimento à primeira cria, com pesagem e ganho de peso.", icon: Baby, cor: "var(--cat-recria)" },
  { chave: "protocolos", titulo: "Central de Protocolos", texto: "Cadastro, lançamento, acompanhamento e histórico de IATF, sanitário, indução de lactação e protocolos customizados — tudo num único lugar.", icon: ListChecks, cor: "var(--dourado-light)" },
];

// Preço em branco de propósito (decisão do dono do produto para o
// lançamento da landing, T8) — uma única constante, fácil de trocar depois
// por um valor real (ou por um preço por plano) sem caçar strings espalhadas
// pelo arquivo. Card mantém a mesma altura com ou sem número aqui.
export const PRECO_PLACEHOLDER = "R$ ____ /mês";

export type PlanoLanding = {
  chave: string;
  nome: string;
  resumo: string;
  itens: string[];
  destaque?: boolean; // Gold: selo "Mais escolhido"
  sobMedida?: boolean; // último plano: layout invertido, sem preço, CTA de orçamento
};

// Catálogo fechado — mesmos 4 planos e mesmos módulos inclusos de
// PLANOS_CATALOGO (backend/fazenda/models/planos.py), mais "Sob Medida"
// (contrato avulso, módulo a módulo, sem seguir pacote fechado). Preço real
// de cada um já existe no backend (250/350/420/500) mas fica de fora daqui
// de propósito — ver PRECO_PLACEHOLDER acima.
export const PLANOS: PlanoLanding[] = [
  {
    chave: "standard",
    nome: "Standard",
    resumo: "Para começar a organizar o rebanho e a reprodução.",
    itens: ["Rebanho", "Reprodução"],
  },
  {
    chave: "silver",
    nome: "Silver",
    resumo: "O ciclo produtivo completo, com sanidade e financeiro.",
    itens: ["Rebanho", "Reprodução", "Produção", "Sanidade", "Financeiro"],
  },
  {
    chave: "gold",
    nome: "Gold",
    resumo: "A fazenda inteira em um só painel — o plano mais escolhido.",
    itens: ["Rebanho", "Reprodução", "Produção", "Sanidade", "Financeiro", "Estoque", "Alimentação", "Pedidos & Planejamento"],
    destaque: true,
  },
  {
    chave: "diamond",
    nome: "Diamond",
    resumo: "Tudo do Gold, mais acesso dedicado para o consultor técnico.",
    itens: ["Todos os módulos do Gold", "Acesso do consultor técnico", "Área de relatórios do consultor"],
  },
  {
    chave: "sob-medida",
    nome: "Sob Medida",
    resumo: "Só os módulos que a sua fazenda precisa, montados um a um — do jeito que fizer sentido para o seu negócio.",
    itens: ["Escolha módulo por módulo", "Sem pacote fechado", "Preço combinado com a sua operação"],
    sobMedida: true,
  },
];
