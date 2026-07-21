import { HeartPulse, Landmark, Briefcase, BarChart3, Newspaper, Wheat, ClipboardList, Syringe, Smartphone } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type Banner = {
  slug: string;
  eyebrow: string;
  titulo: string;
  descricao: string;
  icon: LucideIcon;
  href: string;
};

// Banco completo de banners do hero da página de entrada. A cada dia só 4
// giram no carrossel (ver bannersDeHoje) — os demais ficam disponíveis para
// consulta na grade "Todos os temas" logo abaixo de "Tudo que a fazenda
// precisa, em um painel só". Cada banner é clicável e leva a uma página
// institucional própria (/sobre/*), pública, sem precisar de login.
export const BANNERS: Banner[] = [
  {
    slug: "reprodutivo",
    eyebrow: "Reprodutivo",
    titulo: "Reprodução sob controle, do cio ao diagnóstico",
    descricao: "Protocolos IATF, inseminação, diagnóstico de gestação, categorias do rebanho e a visão global da situação reprodutiva em tempo real.",
    icon: HeartPulse,
    href: "/sobre/reprodutivo",
  },
  {
    slug: "financeiro",
    eyebrow: "Gestão financeira",
    titulo: "Todo o financeiro da fazenda em um só painel",
    descricao: "Fluxo de caixa, DRE, livro caixa, RMCA, custo por litro, por vaca e por lote, e custo por hectare — métricas prontas, sem planilha.",
    icon: Landmark,
    href: "/sobre/financeiro",
  },
  {
    slug: "consultor",
    eyebrow: "Área do consultor",
    titulo: "Feita também para quem assessora a fazenda",
    descricao: "Em construção: o consultor importa planilhas simplificadas de manejo e já visualiza relatórios gerenciais e um construtor de relatório personalizado.",
    icon: Briefcase,
    href: "/sobre/consultor",
  },
  {
    slug: "indicadores",
    eyebrow: "Indicadores gerenciais",
    titulo: "A fazenda inteira, num único painel de decisão",
    descricao: "Indicadores gerenciais para decisão rápida — a visão global dos resultados da fazenda, sem precisar abrir uma tela por vez.",
    icon: BarChart3,
    href: "/sobre/indicadores",
  },
  {
    slug: "milk-news",
    eyebrow: "Milk News",
    titulo: "O mercado do leite, resumido todo santo dia",
    descricao: "Cotação, notícias do setor e conteúdo técnico de genética e manejo, compilados diariamente — com acesso direto às fontes originais.",
    icon: Newspaper,
    href: "/news",
  },
  {
    slug: "estoque-alimentacao",
    eyebrow: "Estoque & Alimentação",
    titulo: "Estoque e dieta calculados sozinhos",
    descricao: "Estoque mínimo com alerta automático de compra, cálculo de alimentação por lote e controle de gasto diário e mensal do rebanho.",
    icon: Wheat,
    href: "/sobre/estoque-alimentacao",
  },
  {
    slug: "pedidos-planejamento",
    eyebrow: "Pedidos & Planejamento",
    titulo: "Do orçamento ao pedido, sem perder o fio",
    descricao: "Controle de pedidos e orçamentos ligado ao planejamento financeiro — acompanhe o que foi pedido, aprovado e ainda falta chegar.",
    icon: ClipboardList,
    href: "/sobre/pedidos-planejamento",
  },
  {
    slug: "sanidade",
    eyebrow: "Sanidade",
    titulo: "Calendário sanitário que avisa antes de atrasar",
    descricao: "Protocolos preventivos e curativos, calendário sanitário automático e histórico clínico completo de cada animal do rebanho.",
    icon: Syringe,
    href: "/sobre/sanidade",
  },
  {
    slug: "app-campo",
    eyebrow: "App de campo",
    titulo: "O sistema também vai pro curral, offline",
    descricao: "Aplicativo enxuto para o dia a dia de campo — lançamentos rápidos que funcionam mesmo sem internet e sincronizam sozinhos depois.",
    icon: Smartphone,
    href: "/sobre/app-campo",
  },
];

function diaDoAno(d: Date): number {
  const inicio = new Date(d.getFullYear(), 0, 0);
  return Math.floor((d.getTime() - inicio.getTime()) / 86400000);
}

/** Seleciona 4 banners de forma circular a partir do dia do ano, então o
 * conjunto de hoje muda todo dia e, com o tempo, todos aparecem no giro. */
export function bannersDeHoje(agora: Date = new Date()): Banner[] {
  const total = BANNERS.length;
  const n = Math.min(4, total);
  const inicio = diaDoAno(agora) % total;
  return Array.from({ length: n }, (_, i) => BANNERS[(inicio + i) % total]);
}
