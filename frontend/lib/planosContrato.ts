// Lógica pura da tela de contratação (Painel CowData > Fazendas, web e mobile):
// dependências entre módulos, módulo base, o que deixa de aparecer ao remover
// módulo e rótulos de preço. Sem React nem fetch — testável com `npm test`.
// As regras vêm do servidor (GET /fazendas/catalogo/dependencias); aqui só se
// aplica o que ele devolve — o backend continua sendo quem valida (400).

export type Dependencias = Record<string, string[]>;
export type SelecaoModulos = Record<string, number | null | undefined>;

export const NOME_MODULO: Record<string, string> = {
  rebanho: "Rebanho", reprodutivo: "Reprodutivo", produtivo: "Produtivo", sanitario: "Sanitário",
  financeiro: "Financeiro (módulo)", planejamento: "Planejamento", pedidos: "Pedidos", estoque: "Estoque",
  alimentacao: "Alimentação", agricultura: "Agricultura/Plantio", consultor: "Consultor (Diamond)",
  formulacao_dietas: "Formulação de Dietas",
};

// O que o usuário da fazenda deixa de ver quando o módulo sai do contrato.
// Os dados NÃO são apagados — voltam a aparecer se o módulo for recontratado.
export const O_QUE_SOME: Record<string, string> = {
  rebanho: "Animais, lotes e a Capa com os indicadores do rebanho",
  reprodutivo: "Reprodução (cios, coberturas, prenhez)",
  produtivo: "Produção de leite e controle leiteiro",
  sanitario: "Sanidade (tratamentos, vacinas, carência)",
  financeiro: "Controle Financeiro, contas a pagar e a receber e os relatórios financeiros",
  planejamento: "Planejamento e orçamento",
  pedidos: "Pedidos e Cotações",
  estoque: "Estoque (saldos, entradas e saídas)",
  alimentacao: "Alimentação e dietas do rebanho",
  agricultura: "Agricultura e plantio (safras, talhões)",
  consultor: "O acesso do Consultor CowData",
  formulacao_dietas: "A Formulação de Dietas",
};

// Nome curto para frases ("Financeiro", não "Financeiro (módulo)").
function nome(m: string): string {
  return (NOME_MODULO[m] || m).replace(/\s*\(.*\)\s*$/, "");
}

function listaPt(itens: string[]): string {
  if (itens.length <= 1) return itens.join("");
  return `${itens.slice(0, -1).join(", ")} e ${itens[itens.length - 1]}`;
}

export function marcados(sel: SelecaoModulos): string[] {
  return Object.keys(sel).filter((m) => sel[m] != null);
}

// Módulos de que `modulo` precisa (inclui os indiretos).
function exigidosPor(modulo: string, deps: Dependencias, visto = new Set<string>()): string[] {
  const diretos = deps[modulo] || [];
  const out: string[] = [];
  for (const d of diretos) {
    if (visto.has(d)) continue;
    visto.add(d);
    out.push(d, ...exigidosPor(d, deps, visto));
  }
  return out;
}

// Quem depende de `modulo` (inclui os indiretos) entre os `ativos`.
function dependentesDe(modulo: string, ativos: string[], deps: Dependencias): string[] {
  return ativos.filter((a) => a !== modulo && exigidosPor(a, deps).includes(modulo));
}

export type ResultadoSelecao = { proximo: SelecaoModulos; aviso: string | null; bloqueado: boolean };

// Marca um módulo e marca junto o que ele exige ("Estoque exige Rebanho e
// Financeiro — marcamos para você"). Preço dos módulos adicionados = 0 (o
// operador ajusta depois se quiser cobrar à parte).
export function marcarModulo(sel: SelecaoModulos, modulo: string, deps: Dependencias): ResultadoSelecao {
  const proximo: SelecaoModulos = { ...sel, [modulo]: sel[modulo] ?? 0 };
  const faltavam = exigidosPor(modulo, deps).filter((d) => proximo[d] == null);
  for (const d of faltavam) proximo[d] = 0;
  const aviso = faltavam.length
    ? `${nome(modulo)} exige ${listaPt(exigidosPor(modulo, deps).map(nome))} — marcamos para você.`
    : null;
  return { proximo, aviso, bloqueado: false };
}

// Desmarca um módulo e desmarca junto quem dependia dele. Recusa (bloqueado)
// se o contrato ficaria sem nenhum módulo base (rebanho ou financeiro).
export function desmarcarModulo(sel: SelecaoModulos, modulo: string, deps: Dependencias, base: string[]): ResultadoSelecao {
  const ativos = marcados(sel);
  const caem = [modulo, ...dependentesDe(modulo, ativos, deps)];
  const restantes = ativos.filter((m) => !caem.includes(m));
  if (base.length > 0 && !restantes.some((m) => base.includes(m))) {
    return {
      proximo: sel, bloqueado: true,
      aviso: `O contrato precisa de ${listaPt(base.map(nome))} (pelo menos um deles) — não dá para tirar ${nome(modulo)} sozinho.`,
    };
  }
  const proximo: SelecaoModulos = { ...sel };
  for (const m of caem) proximo[m] = null;
  const arrastados = caem.slice(1);
  const aviso = arrastados.length
    ? `${listaPt(arrastados.map(nome))} ${arrastados.length > 1 ? "exigem" : "exige"} ${nome(modulo)} — desmarcamos junto.`
    : null;
  return { proximo, aviso, bloqueado: false };
}

// Mensagem de por que a seleção atual não pode ser salva (ou null se ok).
export function validarSelecao(sel: SelecaoModulos, deps: Dependencias, base: string[]): string | null {
  const ativos = marcados(sel);
  if (ativos.length === 0) return "Marque pelo menos um módulo.";
  if (base.length > 0 && !ativos.some((m) => base.includes(m))) {
    return `O contrato precisa de ${listaPt(base.map(nome))} (pelo menos um deles).`;
  }
  for (const m of ativos) {
    const falta = (deps[m] || []).filter((d) => !ativos.includes(d));
    if (falta.length) return `${nome(m)} exige ${listaPt(falta.map(nome))}.`;
  }
  return null;
}

// Módulos que estavam ativos no contrato e não estarão depois de salvar.
export function modulosRemovidos(antes: string[], depois: string[]): string[] {
  const d = new Set(depois);
  return antes.filter((m) => !d.has(m));
}

export function textoRemocao(modulo: string): string {
  return `${nome(modulo)}: ${O_QUE_SOME[modulo] || "as telas deste módulo"}`;
}

export function ordenarPlanos(chaves: string[]): string[] {
  const ordem = ["standard", "silver", "gold", "diamond", "financeiro"];
  const conhecidos = ordem.filter((p) => chaves.includes(p));
  return [...conhecidos, ...chaves.filter((p) => !ordem.includes(p))];
}

export function brl(v: number | null | undefined): string {
  return v == null || Number.isNaN(v) ? "—" : `R$ ${v.toFixed(2).replace(".", ",")}`;
}

// "Preço fechado R$ 200,00 · catálogo hoje R$ 250,00" (nulo quando não há o que mostrar).
export function rotuloPrecoContrato(fechado: number | null | undefined, catalogoHoje: number | null | undefined): string | null {
  if (fechado == null && catalogoHoje == null) return null;
  if (fechado == null) return `Catálogo hoje ${brl(catalogoHoje)}`;
  if (catalogoHoje == null) return `Preço fechado ${brl(fechado)}`;
  return `Preço fechado ${brl(fechado)} · catálogo hoje ${brl(catalogoHoje)}`;
}

export function precoDiverge(fechado: number | null | undefined, catalogoHoje: number | null | undefined): boolean {
  return fechado != null && catalogoHoje != null && Math.abs(fechado - catalogoHoje) >= 0.005;
}

// Resultado do "Preparar financeiro" em linguagem simples.
export function resumoPreparo(r: {
  plano_contas_carregado: boolean; contas_criadas: number; regras_v2_ligadas: boolean; ja_preparado: boolean; mensagens: string[];
}): string {
  const partes: string[] = [];
  if (r.ja_preparado) partes.push("O financeiro desta fazenda já estava preparado — nada foi duplicado.");
  else {
    if (r.plano_contas_carregado) partes.push(`Plano de contas carregado (${r.contas_criadas} ${r.contas_criadas === 1 ? "conta criada" : "contas criadas"}).`);
    else partes.push("O plano de contas não foi carregado.");
    if (r.regras_v2_ligadas) partes.push("Regras do financeiro ligadas.");
  }
  if (r.mensagens?.length) partes.push(...r.mensagens);
  return partes.join(" ");
}
