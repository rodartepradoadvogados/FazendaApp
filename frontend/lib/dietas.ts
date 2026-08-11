// Formulação de Dietas — tipos e chamadas HTTP para /formulacao/* (motor
// NASEM/NRC Dairy 2021, ver backend/fazenda/rules/nutricao/). Espelha os
// schemas Pydantic de backend/fazenda/api/routers/formulacao_dietas.py —
// qualquer divergência de nome de campo é bug aqui, não lá (backend já
// testado, 79 testes). Segue o mesmo padrão de fetch do resto do site
// (authFetch/mensagemErroApi de lib/api.ts), sem cliente HTTP novo.
import { API, authFetch, baixarArquivoAutenticado, mensagemErroApi } from "@/lib/api";

// ── Vocabulário fechado (espelha fazenda/rules/nutricao/tipos.py) ──
export const CATEGORIAS_NASEM = [
  "Forragem", "Pastagem", "Concentrado energetico", "Concentrado proteico", "Proteina animal",
  "Suplemento de gordura", "Suplemento de acido graxo", "Acucar/alcool de acucar",
  "Vitaminico/mineral", "Leite/sucedaneo", "Outros",
] as const;
export type CategoriaNasem = (typeof CATEGORIAS_NASEM)[number];

export type EstadoFisiologico = "vaca_lactante" | "vaca_seca" | "novilha" | "bezerra";
// "bezerra" existe no banco/motor (fase futura) mas o motor rejeita — nunca
// oferecer no seletor da Etapa 2 (ver ESTADOS_FISIOLOGICOS_SELECIONAVEIS).
export const ESTADOS_FISIOLOGICOS_SELECIONAVEIS: { valor: EstadoFisiologico; rotulo: string }[] = [
  { valor: "vaca_lactante", rotulo: "Vaca lactante" },
  { valor: "vaca_seca", rotulo: "Vaca seca" },
  { valor: "novilha", rotulo: "Novilha" },
];

export type Raca = "Holandes" | "Jersey" | "Outra";
export const RACAS: Raca[] = ["Holandes", "Jersey", "Outra"];

export type EquacaoCms = 0 | 2 | 3 | 8 | 9 | 10 | 11;

// Como descontar o efeito da monensina sobre o consumo (ver consumo.py).
export type ModoMonensina = "kg" | "pct" | "manual";
export const OPCOES_MONENSINA: { valor: ModoMonensina; rotulo: string; nota: string }[] = [
  { valor: "kg", rotulo: "−0,30 kg de MS/dia",
    nota: "Desconto fixo em quilos. Vem da meta-análise de Duffield et al. (2008), que reuniu vários estudos com vaca leiteira e achou queda média de cerca de 0,3 kg de matéria seca por dia." },
  { valor: "pct", rotulo: "−2% do consumo",
    nota: "Desconto proporcional: acompanha o tamanho do animal, descontando mais de uma vaca de alto consumo e menos de uma novilha — ao contrário do valor fixo, que tira o mesmo peso das duas." },
  { valor: "manual", rotulo: "Informar a redução manualmente",
    nota: "Use quando você tem medição do próprio rebanho (consumo antes e depois de entrar com monensina)." },
];
export const OPCOES_EQ_CMS: { valor: EquacaoCms; rotulo: string; estados: EstadoFisiologico[] | null }[] = [
  { valor: 8, rotulo: "8 — Vaca lactante, fatores animais (padrão)", estados: ["vaca_lactante"] },
  { valor: 9, rotulo: "9 — Vaca lactante, fatores animais + FDN da dieta", estados: ["vaca_lactante"] },
  { valor: 10, rotulo: "10 — Vaca seca, NASEM 2021", estados: ["vaca_seca"] },
  { valor: 11, rotulo: "11 — Vaca seca, Hayirli et al. 2003", estados: ["vaca_seca"] },
  { valor: 2, rotulo: "2 — Novilha, fatores animais", estados: ["novilha"] },
  { valor: 3, rotulo: "3 — Novilha, fatores animais + FDN da dieta", estados: ["novilha"] },
  { valor: 0, rotulo: "0 — CMS informado manualmente", estados: null },
];

export const CAMPOS_NUTRICIONAIS = [
  "ms_pct", "pb_pct", "fdn_pct", "fda_pct", "lignina_pct", "amido_pct", "acucares_pct", "ee_pct", "ag_pct",
  "cinzas_pct", "dndf48_fdn_pct",
  "pb_a_pct", "pb_b_pct", "pb_c_pct", "kd_pb_b_pct_h", "nnp_pb_pct", "pidn_pct", "pida_pct",
  "dig_amido_pct", "dig_pndr_pct", "dig_ag_pct",
  "ca_pct", "p_pct", "p_inorg_p_pct", "p_org_p_pct", "mg_pct", "k_pct", "na_pct", "cl_pct", "s_pct",
  "abs_ca", "abs_p_total", "abs_mg", "abs_na", "abs_cl", "abs_k",
  "custo_kg_mn",
] as const;
export type CampoNutricional = (typeof CAMPOS_NUTRICIONAIS)[number];

// Grupos para o drawer de detalhe por linha da grade (Etapa 1) — mesma
// ordem/agrupamento da docstring de AlimentoNutricional no backend.
export const GRUPOS_CAMPOS_NUTRICIONAIS: { titulo: string; campos: CampoNutricional[] }[] = [
  { titulo: "Base (% da MS, salvo indicado)", campos: ["ms_pct", "pb_pct", "fdn_pct", "fda_pct", "lignina_pct", "amido_pct", "acucares_pct", "ee_pct", "ag_pct", "cinzas_pct", "dndf48_fdn_pct"] },
  { titulo: "Fracionamento proteico (% da PB)", campos: ["pb_a_pct", "pb_b_pct", "pb_c_pct", "kd_pb_b_pct_h", "nnp_pb_pct", "pidn_pct", "pida_pct"] },
  { titulo: "Digestibilidades de referência", campos: ["dig_amido_pct", "dig_pndr_pct", "dig_ag_pct"] },
  { titulo: "Macrominerais (% da MS)", campos: ["ca_pct", "p_pct", "p_inorg_p_pct", "p_org_p_pct", "mg_pct", "k_pct", "na_pct", "cl_pct", "s_pct"] },
  { titulo: "Absorção (fração 0–1)", campos: ["abs_ca", "abs_p_total", "abs_mg", "abs_na", "abs_cl", "abs_k"] },
  { titulo: "Custo", campos: ["custo_kg_mn"] },
];

export const ROTULOS_CAMPOS_NUTRICIONAIS: Record<CampoNutricional, string> = {
  ms_pct: "MS %", pb_pct: "PB %", fdn_pct: "FDN %", fda_pct: "FDA %", lignina_pct: "Lignina %",
  amido_pct: "Amido %", acucares_pct: "Açúcares %", ee_pct: "EE %", ag_pct: "AG %", cinzas_pct: "Cinzas %",
  dndf48_fdn_pct: "dNDF48 (% da FDN)",
  pb_a_pct: "PB A %", pb_b_pct: "PB B %", pb_c_pct: "PB C %", kd_pb_b_pct_h: "Kd PB-B (%/h)",
  nnp_pb_pct: "NNP (% da PB)", pidn_pct: "PIDN %", pida_pct: "PIDA %",
  dig_amido_pct: "Dig. amido %", dig_pndr_pct: "Dig. PNDR %", dig_ag_pct: "Dig. AG %",
  ca_pct: "Ca %", p_pct: "P %", p_inorg_p_pct: "P inorgânico (% do P)", p_org_p_pct: "P orgânico (% do P)",
  mg_pct: "Mg %", k_pct: "K %", na_pct: "Na %", cl_pct: "Cl %", s_pct: "S %",
  abs_ca: "Absorção Ca", abs_p_total: "Absorção P total", abs_mg: "Absorção Mg", abs_na: "Absorção Na",
  abs_cl: "Absorção Cl", abs_k: "Absorção K",
  custo_kg_mn: "Custo (R$/kg MN)",
};

// Colunas visíveis por padrão na grade principal (Etapa 1/4) — o resto fica
// no drawer de detalhe (ver GRUPOS_CAMPOS_NUTRICIONAIS acima).
export const CAMPOS_GRADE_PRINCIPAL: CampoNutricional[] = [
  "ms_pct", "pb_pct", "fdn_pct", "fda_pct", "amido_pct", "ee_pct", "ca_pct", "p_pct", "custo_kg_mn",
];

// ── Animal (Etapa 2) ──
export type AnimalPayload = {
  estado_fisiologico: EstadoFisiologico;
  raca: Raca;
  peso_vivo_kg: number;
  peso_maturo_kg: number;
  ecc: number;
  paridade: number;
  idade_dias?: number | null;
  del_dias?: number | null;
  dias_gestacao?: number | null;
  duracao_gestacao_dias: number;
  peso_bezerro_nascer_kg: number;
  del_concepcao?: number | null;
  idade_concepcao_1a_dias?: number | null;
  ganho_estrutura_kg_dia: number;
  ganho_reserva_kg_dia: number;
  producao_leite_kg_dia?: number | null;
  gordura_leite_pct?: number | null;
  proteina_leite_pct?: number | null;
  lactose_leite_pct: number;
  potencial_genetico_pl_305: number;
  temperatura_c: number;
  distancia_sala_m: number;
  viagens_sala_dia: number;
  desnivel_diario_m: number;
  eq_cms: EquacaoCms;
  cms_informado_kg_dia?: number | null;
  usa_monensina: boolean;
  monensina_modo?: ModoMonensina;
  monensina_reducao_manual?: number | null;
  eq_microbiana: 1;
  usa_dndf48: 0;
};

export function animalPadrao(): AnimalPayload {
  return {
    estado_fisiologico: "vaca_lactante", raca: "Holandes", peso_vivo_kg: 0, peso_maturo_kg: 680,
    ecc: 3.0, paridade: 1.0, idade_dias: null, del_dias: null, dias_gestacao: null,
    duracao_gestacao_dias: 283, peso_bezerro_nascer_kg: 44.1, del_concepcao: null, idade_concepcao_1a_dias: null,
    ganho_estrutura_kg_dia: 0, ganho_reserva_kg_dia: 0, producao_leite_kg_dia: null, gordura_leite_pct: null,
    proteina_leite_pct: null, lactose_leite_pct: 4.78, potencial_genetico_pl_305: 280, temperatura_c: 24,
    distancia_sala_m: 0, viagens_sala_dia: 4, desnivel_diario_m: 0, eq_cms: 8, cms_informado_kg_dia: null,
    usa_monensina: false, eq_microbiana: 1, usa_dndf48: 0,
  };
}

// ── Ingrediente da grade (Etapas 1/4) ──
export type OrigemItemGrade = "biblioteca" | "bromatologica" | "template" | "manual";

export type ItemGrade = {
  id?: number; // presente só quando veio de GET /simulacoes/{id} (persistido)
  ordem?: number;
  nome: string;
  categoria_nasem: CategoriaNasem;
  conc_pct: number;
  proporcao_ms_pct: number;
  origem: OrigemItemGrade;
  alimento_id?: number | null;
  alimento_nutricional_id?: number | null;
  analise_bromatologica_id?: number | null;
  campos_editados?: string[] | null;
  // Faixa típica de inclusão na dieta (% da MS TOTAL da dieta), puxada da
  // biblioteca junto com o teor de MS — só orientação visual pro
  // nutricionista na Etapa 1 (grade), o backend ignora estes dois campos no
  // cálculo (não fazem parte de CampoNutricional/IngredienteIn).
  inclusao_min_pct?: number | null;
  inclusao_max_pct?: number | null;
} & { [K in CampoNutricional]?: number | null };

export function itemGradeVazio(categoria: CategoriaNasem = "Outros"): ItemGrade {
  const item: ItemGrade = {
    nome: "", categoria_nasem: categoria, conc_pct: categoria === "Forragem" || categoria === "Pastagem" ? 0 : 100,
    proporcao_ms_pct: 0, origem: "manual", alimento_id: null, alimento_nutricional_id: null,
    analise_bromatologica_id: null, campos_editados: [],
  };
  for (const campo of CAMPOS_NUTRICIONAIS) item[campo] = null;
  return item;
}

// ── Resultado do motor (POST /calcular, campo `resultado` da simulação) ──
export type MineralBalanco = { nome: string; unidade: string; fornecido_absorvido: number; exigencia: number; balanco: number };

export type IngredienteResultado = {
  nome: string; categoria_nasem: string; proporcao_ms_pct: number;
  kg_materia_seca_dia: number; kg_materia_natural_dia: number; custo_dia: number;
};

export type LinhaBalanco = {
  nutriente: string; unidade: string; exigencia: number; fornecido: number; balanco: number;
  situacao: "adequado" | "deficit" | "excesso";
};

export type Aviso = { codigo: string; severidade: "info" | "atencao" | "bloqueante"; mensagem: string };

export type Resultado = {
  motor_versao: string;
  animal: {
    estado_fisiologico: string; raca: string; peso_vivo_kg: number; peso_metabolico_kg: number;
    peso_maturo_kg: number; peso_vazio_kg: number; peso_maturo_vazio_kg: number; razao_peso_vazio: number;
  };
  consumo: {
    cms_kg_dia: number; equacao_usada: number; cms_pct_pv: number; cms_g_kg_pv075: number;
    // As DUAS estimativas da categoria, sempre calculadas (ver consumo.py):
    // a "sem fibra" só olha o animal, a "com fibra" também lê a dieta. A
    // diferença entre elas é o quanto a fibra está travando o consumo.
    cms_sem_fibra_kg_dia: number; cms_com_fibra_kg_dia: number;
    equacao_sem_fibra: number; equacao_com_fibra: number;
    fibra_limita_kg_dia: number; fibra_e_limitante: boolean;
    monensina_reducao_kg_dia: number;
  };
  dieta: Record<string, number> & { perfis?: Record<string, number | string>[] };
  digestao: Record<string, number | Record<string, number>>;
  energia: Record<string, number | boolean | null>;
  microbiana: Record<string, number>;
  proteina: {
    manutencao: Record<string, number>;
    suprimento: Record<string, number>;
    exigencias: Record<string, number | boolean>;
    balanco_g: number;
    leite_permitido_por_pm_kg_dia: number | null;
    nitrogenio_urinario_g_dia: number;
  };
  mantenca: Record<string, number>;
  gestacao: Record<string, number | boolean>;
  corpo: Record<string, number>;
  leite: Record<string, number>;
  minerais: {
    calcio: MineralBalanco; fosforo: MineralBalanco; magnesio: MineralBalanco; sodio: MineralBalanco;
    cloro: MineralBalanco; potassio: MineralBalanco; enxofre: MineralBalanco; dcad_meq_kg: number;
  };
  ingredientes: IngredienteResultado[];
  balanco: LinhaBalanco[];
  avisos: Aviso[];
};

// ── Simulações ──
export type StatusSimulacao = "rascunho" | "concluida" | "aplicada" | "arquivada";

export type SimulacaoResumo = {
  id: number; nome: string; lote: number | null; status: StatusSimulacao; etapa_atual: number;
  calculado_em: string | null; aplicada_em: string | null; criado_em: string; atualizado_em: string;
  usuario_id: number | null; usuario_nome: string | null;
  cms_kg_dia: number | null; balanco_ell_mcal: number | null; balanco_pm_g: number | null; custo_dia: number | null;
};

// Cabeçalho completo (GET /simulacoes/{id}) — todos os campos de AnimalPayload
// mais os metadados da simulação (sim.model_dump() no backend).
export type SimulacaoCabecalho = AnimalPayload & {
  id: number; fazenda_id: number; nome: string; lote: number | null; status: StatusSimulacao; etapa_atual: number;
  motor_versao: string | null; calculado_em: string | null;
  dieta_lancamento_id: number | null; aplicada_em: string | null; aplicada_por_usuario_id: number | null;
  criado_em: string; atualizado_em: string; usuario_id: number | null;
  // Overrides manuais da coluna "Exigência" da Etapa 4, {nutriente: valor} —
  // ver PainelBalanco.tsx e docstring de DietaSimulacao.exigencias_editadas_json.
  exigencias_editadas: Record<string, number>;
};

export type SimulacaoDetalhe = {
  cabecalho: SimulacaoCabecalho;
  itens: ItemGrade[];
  resultado: Resultado | null;
  avisos: Aviso[] | null;
};

export async function listarSimulacoes(params?: { lote?: number; status?: StatusSimulacao }): Promise<SimulacaoResumo[]> {
  const qs = new URLSearchParams();
  if (params?.lote != null) qs.set("lote", String(params.lote));
  if (params?.status) qs.set("status", params.status);
  const res = await authFetch(`${API}/formulacao/simulacoes${qs.toString() ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`Simulações error: ${res.status}`);
  return res.json();
}

export async function criarSimulacao(dados: { nome: string; lote?: number | null }): Promise<SimulacaoResumo> {
  const res = await authFetch(`${API}/formulacao/simulacoes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao criar simulação"); }
  return res.json();
}

export async function obterSimulacao(id: number): Promise<SimulacaoDetalhe> {
  const res = await authFetch(`${API}/formulacao/simulacoes/${id}`);
  if (!res.ok) throw new Error(`Simulação error: ${res.status}`);
  return res.json();
}

// Erros dedicados para os dois 409 do PUT — a tela distingue "já aplicada"
// (ofereça duplicar) de "editada em outra aba" (ofereça recarregar).
export class SimulacaoAplicadaError extends Error {}
export class SimulacaoConflitoError extends Error {}

export async function salvarSimulacao(
  id: number,
  dados: {
    animal: AnimalPayload; itens: ItemGrade[]; etapa_atual: number; atualizado_em?: string | null;
    exigencias_editadas?: Record<string, number> | null;
  },
): Promise<{ cabecalho: SimulacaoCabecalho; itens: ItemGrade[]; resultado: Resultado }> {
  const res = await authFetch(`${API}/formulacao/simulacoes/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (res.status === 409) {
    const d = await res.json().catch(() => ({}));
    const msg = mensagemErroApi(d.detail) || "Conflito ao salvar a simulação.";
    if (msg.toLowerCase().includes("aplicada")) throw new SimulacaoAplicadaError(msg);
    throw new SimulacaoConflitoError(msg);
  }
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar simulação"); }
  return res.json();
}

export async function excluirSimulacao(id: number): Promise<void> {
  const res = await authFetch(`${API}/formulacao/simulacoes/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir simulação"); }
}

export async function duplicarSimulacao(id: number, nome: string): Promise<{ cabecalho: SimulacaoCabecalho; itens: ItemGrade[] }> {
  const res = await authFetch(`${API}/formulacao/simulacoes/${id}/duplicar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nome }),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao duplicar simulação"); }
  return res.json();
}

export type AplicarDietaPayload = {
  lote: number; data_abertura: string; base_quantidade: "total" | "animal";
  responsavel?: string | null; data_prevista_encerramento?: string | null; encerrar_anterior: boolean;
};

export class DietaAtivaConflitoError extends Error {}

export async function aplicarSimulacao(
  id: number, dados: AplicarDietaPayload,
): Promise<{ dieta_lancamento_id: number; itens_criados: number; qtd_animais: number }> {
  const res = await authFetch(`${API}/formulacao/simulacoes/${id}/aplicar`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (res.status === 409) {
    const d = await res.json().catch(() => ({}));
    throw new DietaAtivaConflitoError(mensagemErroApi(d.detail) || "Já existe uma dieta ativa neste lote.");
  }
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao aplicar a simulação"); }
  return res.json();
}

// Cálculo ao vivo (stateless) — Etapa 4 chama com debounce + AbortController;
// um abort deliberado chega aqui como DOMException("AbortError"), o chamador
// deve ignorá-lo (não é falha de cálculo, é substituição pela chamada seguinte).
export async function calcularDieta(
  animal: AnimalPayload, itens: ItemGrade[], signal?: AbortSignal, exigenciasEditadas?: Record<string, number> | null,
): Promise<Resultado> {
  const res = await authFetch(`${API}/formulacao/calcular`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ animal, itens, exigencias_editadas: exigenciasEditadas || undefined }), signal,
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao calcular a dieta"); }
  return res.json();
}

// ── Biblioteca de alimentos (Etapa 1 + aba "Biblioteca de referência") ──
export type EntradaBiblioteca = {
  id: number; alimento_id: number | null; nome: string; categoria_nasem: string; conc_pct: number;
  fonte: string | null; observacao: string | null; ativo: boolean;
  inclusao_min_pct: number | null; inclusao_max_pct: number | null;
  // eh_mestre: item da biblioteca padrão CowData, ainda não copiado por esta
  // fazenda. eh_copia_editada: já é cópia desta fazenda de um item mestre
  // (editado ou ocultado) — controla o rótulo do botão excluir ("Restaurar
  // padrão CowData" em vez de "Excluir") na aba de biblioteca.
  eh_mestre: boolean; eh_copia_editada: boolean;
  valores: { [K in CampoNutricional]?: number | null } & Record<string, number | null | undefined>;
};

export type AlimentoCadastradoResumo = { id: number; nome: string; sem_composicao: boolean };

export type ListarAlimentosResponse = { biblioteca: EntradaBiblioteca[]; cadastrados: AlimentoCadastradoResumo[] };

export async function listarAlimentos(busca?: string): Promise<ListarAlimentosResponse> {
  const qs = busca?.trim() ? `?busca=${encodeURIComponent(busca.trim())}` : "";
  const res = await authFetch(`${API}/formulacao/alimentos${qs}`);
  if (!res.ok) throw new Error(`Alimentos error: ${res.status}`);
  return res.json();
}

export type ResolverAlimentoResponse = {
  nome: string; categoria_nasem: string; conc_pct: number; origem: "biblioteca" | "bromatologica" | "template";
  alimento_nutricional_id: number | null; analise_bromatologica_id: number | null;
  inclusao_min_pct: number | null; inclusao_max_pct: number | null;
  valores: { [K in CampoNutricional]?: number | null };
};

export async function resolverAlimento(alimentoId: number): Promise<ResolverAlimentoResponse> {
  const res = await authFetch(`${API}/formulacao/alimentos/${alimentoId}/resolver`);
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao resolver o alimento"); }
  return res.json();
}

export type AlimentoNutricionalPayload = {
  alimento_id?: number | null; nome: string; categoria_nasem: CategoriaNasem; conc_pct: number;
  fonte?: string | null; observacao?: string | null;
  inclusao_min_pct?: number | null; inclusao_max_pct?: number | null;
  valores: Record<string, number | null | undefined>;
};

export async function atualizarAlimentoNaBiblioteca(id: number, dados: AlimentoNutricionalPayload): Promise<EntradaBiblioteca> {
  const res = await authFetch(`${API}/formulacao/alimentos/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar o alimento"); }
  return res.json();
}

export type ExcluirAlimentoResposta = { acao: "excluido" | "restaurado" | "oculto" | "ja_oculto"; mensagem: string };

export async function excluirAlimentoDaBiblioteca(id: number): Promise<ExcluirAlimentoResposta> {
  const res = await authFetch(`${API}/formulacao/alimentos/${id}`, { method: "DELETE" });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao excluir o alimento"); }
  return res.json();
}

export function baixarModeloBibliotecaAlimentos() {
  return baixarArquivoAutenticado("/formulacao/alimentos/modelo", "biblioteca_alimentos_modelo.xlsx");
}

export type ImportarBibliotecaResposta = { criados: number; atualizados: number; avisos: string[]; erros: string[] };

export async function importarBibliotecaAlimentos(file: File): Promise<ImportarBibliotecaResposta> {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`${API}/formulacao/alimentos/importar`, { method: "POST", body: form });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao importar a planilha"); }
  return res.json();
}

export type EntradaSemente = { nome: string; categoria_nasem: string; conc_pct: number; fonte?: string } & Record<string, number | string | undefined>;

export type TemplatesResponse = {
  categorias: Record<string, { [K in CampoNutricional]?: number | null }>;
  biblioteca_semente: EntradaSemente[];
};

export async function listarTemplates(): Promise<TemplatesResponse> {
  const res = await authFetch(`${API}/formulacao/templates`);
  if (!res.ok) throw new Error(`Templates error: ${res.status}`);
  return res.json();
}

export async function salvarAlimentoNaBiblioteca(dados: AlimentoNutricionalPayload): Promise<EntradaBiblioteca> {
  const res = await authFetch(`${API}/formulacao/alimentos`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados),
  });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao salvar na biblioteca"); }
  return res.json();
}

// ── Contexto do lote (Etapa 2) ──
export type ContextoLote = {
  lote: number; nome: string | null; qtd_animais: number;
  del_medio: number | null; media_cl: number | null;
  peso_vivo_kg: number | null; ecc: number | null; del_dias: number | null; producao_leite_kg_dia: number | null;
  campos_estimados: string[];
};

export async function contextoFormulacao(lote: number): Promise<ContextoLote> {
  const res = await authFetch(`${API}/formulacao/contexto/${lote}`);
  if (!res.ok) throw new Error(`Contexto do lote error: ${res.status}`);
  return res.json();
}

// ── Construtores de linha da grade a partir das 3 origens da Etapa 1 ──
export function itemGradeDeResolucao(alimentoId: number, r: ResolverAlimentoResponse): ItemGrade {
  const item = itemGradeVazio(r.categoria_nasem as CategoriaNasem);
  item.nome = r.nome;
  item.conc_pct = r.conc_pct;
  item.origem = r.origem;
  item.alimento_id = alimentoId;
  item.alimento_nutricional_id = r.alimento_nutricional_id;
  item.analise_bromatologica_id = r.analise_bromatologica_id;
  item.inclusao_min_pct = r.inclusao_min_pct;
  item.inclusao_max_pct = r.inclusao_max_pct;
  for (const campo of CAMPOS_NUTRICIONAIS) item[campo] = r.valores[campo] ?? null;
  return item;
}

// Adiciona direto na grade um item da biblioteca (mestre CowData ou próprio
// da fazenda) sem passar pelo cadastro de Alimento — mesmo espírito de
// itemGradeDaSemente, mas lendo da biblioteca de verdade (mestre + fazenda,
// ver aba "Biblioteca de referência") em vez da lista estática de 12 itens.
export function itemGradeDaBiblioteca(e: EntradaBiblioteca): ItemGrade {
  const item = itemGradeVazio(e.categoria_nasem as CategoriaNasem);
  item.nome = e.nome;
  item.conc_pct = e.conc_pct;
  item.origem = "biblioteca";
  item.alimento_id = e.alimento_id;
  item.alimento_nutricional_id = e.id;
  item.inclusao_min_pct = e.inclusao_min_pct;
  item.inclusao_max_pct = e.inclusao_max_pct;
  for (const campo of CAMPOS_NUTRICIONAIS) item[campo] = e.valores[campo] ?? null;
  return item;
}

export function itemGradeDaSemente(s: EntradaSemente): ItemGrade {
  const item = itemGradeVazio(s.categoria_nasem as CategoriaNasem);
  item.nome = s.nome;
  item.conc_pct = Number(s.conc_pct) || 0;
  item.origem = "template";
  for (const campo of CAMPOS_NUTRICIONAIS) {
    const v = s[campo];
    item[campo] = typeof v === "number" ? v : null;
  }
  return item;
}
