// Nome de exibição de cada página, pelo pathname — usado só pelo título das
// guias do sistema de abas (ver TabsShell/lib/tabs.ts): mostra sempre o nome
// da PÁGINA atual, nunca da sub-aba dentro dela. Lista deliberadamente
// separada da Sidebar (que filtra por permissão do usuário) — aqui precisa
// de todo mundo, mesmo quem o usuário atual não pode ver.
const ROTULO_POR_ROTA: { href: string; rotulo: string }[] = [
  { href: "/agenda", rotulo: "Agenda" },
  { href: "/lancamentos", rotulo: "Lançamentos" },
  { href: "/rebanho", rotulo: "Rebanho" },
  { href: "/historico", rotulo: "Histórico" },
  { href: "/sanidade", rotulo: "Sanidade" },
  { href: "/alimentacao", rotulo: "Alimentação" },
  { href: "/estoque", rotulo: "Estoque" },
  { href: "/indicadores", rotulo: "Indicadores" },
  { href: "/relatorios", rotulo: "Listas" },
  { href: "/analise-relatorios", rotulo: "Relatórios" },
  { href: "/financeiro", rotulo: "Controle Financeiro" },
  { href: "/pedidos", rotulo: "Pedidos" },
  { href: "/usuarios", rotulo: "Controle de Acesso" },
  { href: "/portal", rotulo: "Portal" },
  { href: "/consultor", rotulo: "Consultor" },
  { href: "/configuracoes", rotulo: "Configurações" },
  { href: "/news", rotulo: "Milk News" },
  { href: "/app", rotulo: "Fazenda" },
];

export function rotuloDaPagina(pathname: string): string {
  if (pathname === "/") return "Capa";
  // Rota mais específica primeiro (ex.: "/analise-relatorios" antes de
  // teria colidido com um prefixo genérico) — mesma regra de match por
  // prefixo já usada em Sidebar.tsx (path === href || path.startsWith(href)).
  const encontrado = ROTULO_POR_ROTA
    .slice()
    .sort((a, b) => b.href.length - a.href.length)
    .find((r) => pathname === r.href || pathname.startsWith(r.href + "/"));
  return encontrado?.rotulo || "Fazenda";
}
