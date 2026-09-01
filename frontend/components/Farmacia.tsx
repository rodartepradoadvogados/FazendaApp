"use client";
// Farmácia — a aba única que junta o catálogo de INDICAÇÕES (doença/manejo:
// reprodutivo, produtivo, preventivo, suporte) com os PRINCÍPIOS que tratam
// cada uma (ordenados por prioridade) e as MARCAS comerciais de cada
// princípio, já com bula e carência formatada. O catálogo nasce global
// (mesmo documento base para todas as fazendas) — dose e carência do padrão
// são só um ponto de partida, editável a qualquer momento. Editar qualquer
// campo do padrão (bula, prioridade, nota) PERSONALIZA a indicação
// automaticamente, num passo só: o backend clona pra fazenda e já aplica a
// edição no clone (ver PUT /farmacia/medicamentos/{id} e PUT
// /farmacia/indicacoes/{id} no backend). O botão "Personalizar para minha
// fazenda" (POST/DELETE .../personalizar) continua disponível pra quem
// prefere clonar antes de editar, mas deixou de ser pré-requisito.
import { useEffect, useMemo, useState } from "react";
import {
  Search, Lock, Pencil, ChevronDown, ChevronRight, AlertTriangle, Ban, ExternalLink, RotateCcw, Check, X,
  Beaker, Building2, Pill, Syringe, Tags, GitCompareArrows,
} from "lucide-react";
import {
  fetchIndicacoesCatalogo, personalizarIndicacao,
  atualizarMarcaFarmacia, atualizarVinculoIndicacao, fetchFarmaciaDetalhe, restaurarCatalogoPrincipios,
  fetchFarmaciaPrincipios, definirEstoqueMinimoFarmacia,
  fetchPrincipiosFarmaciaCowData, fetchCategoriasMedicamentoFarmaciaCowData,
  fetchClassificacoesMedicamentoFarmaciaCowData, fetchLaboratoriosFarmaciaCowData,
  fetchCategoriasFarmaciaCowData, fetchSubstitutivosPorFiltro, fetchSubstitutivosDeMedicamento,
  type IndicacaoCatalogo, type PrincipioIndicacaoCatalogo, type MarcaIndicacaoCatalogo, type PrincipioFarmacia,
  type EixoFiltroSubstitutivos, type MedicamentoFarmaciaCowData, type MedicamentoSubstituto,
} from "@/lib/api";
import { carenciaNaoInformada } from "@/lib/carencia";
import { VIAS_APLICACAO } from "@/lib/constants";
import { normalizarBusca as normalizar } from "@/lib/busca";

function num(v?: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
}

const TIPO_INFO: Record<string, { label: string; cor: string }> = {
  doenca: { label: "Doença", cor: "var(--cat-sanidade)" },
  reprodutivo: { label: "Reprodutivo", cor: "var(--cat-reproducao)" },
  produtivo: { label: "Produtivo", cor: "var(--blue)" },
  preventivo: { label: "Preventivo", cor: "var(--dourado-light)" },
  suporte: { label: "Suporte", cor: "var(--cat-acesso)" },
};
const TIPOS_FILTRO: [string, string][] = [
  ["", "Todas"], ["doenca", "Doenças"], ["reprodutivo", "Reprodutivo"],
  ["produtivo", "Produtivo"], ["preventivo", "Preventivo"], ["suporte", "Suporte"],
];
// Seção 1 (ordem pedida pelo usuário, 01/09/2026): Doenças/Reprodutivo/
// Produtivo/Preventivo/Suporte/Todas — igual TIPOS_FILTRO, só reordenado
// como tabs de navegação (em vez de pílulas soltas) quando dentro do Painel
// CowData. Seção 2: as 5 abas do catálogo de farmácia propriamente dito —
// "Medicamentos" é o browse por indicação já existente (CardIndicacao); as
// outras 4 são catálogos "nome + ativo" simples, cadastrados em
// FarmaciaCadastroCentral e aqui só consultados.
const SECAO1_ABAS_CATALOGO: [string, string][] = [
  ["doenca", "Doenças"], ["reprodutivo", "Reprodutivo"], ["produtivo", "Produtivo"],
  ["preventivo", "Preventivo"], ["suporte", "Suporte"], ["", "Todas"],
];
const SECAO2_ABAS_CATALOGO = [
  { chave: "medicamentos", label: "Medicamentos", icone: Syringe },
  { chave: "principios", label: "Princípios ativos", icone: Pill },
  { chave: "categoriasMedicamento", label: "Categorias", icone: Tags },
  { chave: "classificacoesMedicamento", label: "Classificação do medicamento", icone: Beaker },
  { chave: "laboratorios", label: "Laboratórios", icone: Building2 },
] as const;
// Seção 3 — só existe em Catálogo (Fase E, 01/09/2026): tabela dinâmica de
// cruzamento de medicamentos por atributos clínicos coincidentes.
const SECAO3_ABAS_CATALOGO = [
  { chave: "substitutivos", label: "Substitutivos", icone: GitCompareArrows },
] as const;
type Secao2AbaCatalogo = (typeof SECAO2_ABAS_CATALOGO)[number]["chave"] | (typeof SECAO3_ABAS_CATALOGO)[number]["chave"];

// Eixos disponíveis pro 1º filtro de Substitutivos — Seção 1 (indicação) +
// os catálogos "nome + ativo" da Seção 2 (Medicamentos fica de fora: não faz
// sentido cruzar "por medicamento", o pivô já É o medicamento escolhido no
// 2º passo).
const EIXOS_SUBSTITUTIVOS: { chave: EixoFiltroSubstitutivos; label: string }[] = [
  { chave: "doenca", label: "Indicação (doença/finalidade)" },
  { chave: "principio", label: "Princípio ativo" },
  { chave: "categoria", label: "Categoria (medicamento)" },
  { chave: "classificacao", label: "Classificação do medicamento" },
  { chave: "laboratorio", label: "Laboratório" },
];

const secaoLabelStyle: React.CSSProperties = {
  fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em",
  color: "var(--text-muted)", margin: "0 0 0.4rem",
};

function AbaBotaoCatalogo({ ativo, onClick, children, icone: Icone }: {
  ativo: boolean; onClick: () => void; children: React.ReactNode; icone?: React.ComponentType<{ size?: number }>;
}) {
  return (
    <button onClick={onClick} style={{
      fontSize: "0.8rem", padding: "0.4rem 0.85rem", borderRadius: 999, cursor: "pointer", fontWeight: ativo ? 700 : 500,
      display: "inline-flex", alignItems: "center", gap: "0.4rem",
      border: "1px solid " + (ativo ? "var(--dourado)" : "var(--border)"),
      background: ativo ? "var(--pill-active-bg)" : "transparent",
      color: ativo ? "var(--pill-active-fg)" : "var(--text-muted)",
    }}>
      {Icone && <Icone size={14} />}{children}
    </button>
  );
}

// Catálogo "nome + ativo" simples (Categoria/Classificação do medicamento,
// Laboratório, Princípios ativos) — só consulta; cadastrar/editar continua
// sendo tarefa exclusiva de Painel CowData › Farmácia › Cadastrar.
function CatalogoLeituraSimples({ descricao, fetch: buscar }: {
  descricao: string; fetch: () => Promise<{ id: number; nome: string; ativo?: boolean }[]>;
}) {
  const [lista, setLista] = useState<{ id: number; nome: string; ativo?: boolean }[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { buscar().then(setLista).catch((e: any) => setErro(e.message)); }, [buscar]);

  return (
    <div>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.8rem", maxWidth: "62ch" }}>{descricao}</p>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}
      {!lista ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>
      ) : lista.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nada cadastrado ainda — cadastre em Painel CowData › Farmácia › Cadastrar.</p>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
          {lista.map((item) => (
            <span key={item.id} style={{
              display: "inline-flex", alignItems: "center", gap: "0.4rem", padding: "0.3rem 0.65rem",
              borderRadius: 999, border: "1px solid var(--border)", background: "var(--surface-2)", fontSize: "0.8rem",
              color: item.ativo === false ? "var(--text-muted)" : "var(--text)", opacity: item.ativo === false ? 0.6 : 1,
            }}>
              {item.nome}{item.ativo === false && " (inativa)"}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const input: React.CSSProperties = {
  padding: "0.4rem 0.55rem", borderRadius: 6, fontSize: "0.82rem",
  background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)",
};
const labelStyle: React.CSSProperties = { fontSize: "0.68rem", color: "var(--text-muted)" };

// Fase E (01/09/2026) — 1º nível da tabela de Substitutivos: pra cada eixo,
// qual catálogo buscar as opções específicas.
const FETCH_ITENS_EIXO_SUBSTITUTIVOS: Record<EixoFiltroSubstitutivos, () => Promise<{ id: number; nome: string }[]>> = {
  doenca: fetchCategoriasFarmaciaCowData, principio: fetchPrincipiosFarmaciaCowData,
  categoria: fetchCategoriasMedicamentoFarmaciaCowData, classificacao: fetchClassificacoesMedicamentoFarmaciaCowData,
  laboratorio: fetchLaboratoriosFarmaciaCowData,
};

// Tabela dinâmica de cruzamento: escolhe um eixo + item → lista de
// medicamentos que batem → clique num deles → ranking dos demais por
// atributos clínicos coincidentes (laboratório não conta ponto).
function SubstitutivosView() {
  const [eixo, setEixo] = useState<EixoFiltroSubstitutivos>("principio");
  const [itensEixo, setItensEixo] = useState<{ id: number; nome: string }[] | null>(null);
  const [itemId, setItemId] = useState<number | "">("");
  const [medicamentos, setMedicamentos] = useState<MedicamentoFarmaciaCowData[] | null>(null);
  const [pivoId, setPivoId] = useState<number | null>(null);
  const [substitutos, setSubstitutos] = useState<MedicamentoSubstituto[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setItensEixo(null); setItemId(""); setMedicamentos(null); setPivoId(null); setSubstitutos(null); setErro(null);
    FETCH_ITENS_EIXO_SUBSTITUTIVOS[eixo]().then(setItensEixo).catch((e: any) => setErro(e.message));
  }, [eixo]);

  useEffect(() => {
    setPivoId(null); setSubstitutos(null);
    if (itemId === "") { setMedicamentos(null); return; }
    setMedicamentos(null); setErro(null);
    fetchSubstitutivosPorFiltro(eixo, Number(itemId)).then(setMedicamentos).catch((e: any) => setErro(e.message));
  }, [eixo, itemId]);

  useEffect(() => {
    if (pivoId == null) { setSubstitutos(null); return; }
    setSubstitutos(null); setErro(null);
    fetchSubstitutivosDeMedicamento(pivoId).then(setSubstitutos).catch((e: any) => setErro(e.message));
  }, [pivoId]);

  const nomePivo = medicamentos?.find((m) => m.id === pivoId)?.nome_comercial;

  return (
    <div>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.9rem", maxWidth: "68ch" }}>
        Escolha um filtro — indicação, princípio ativo, categoria, classificação ou laboratório — pra achar os
        medicamentos que batem nele, depois clique num deles pra ver os demais ranqueados pelo número de atributos
        clínicos em comum (princípio ativo, indicação, categoria e classificação do medicamento — laboratório não
        conta ponto, aparece só como informação no card).
      </p>

      <div className="flex items-end gap-2 flex-wrap" style={{ marginBottom: "1rem" }}>
        <div>
          <label style={labelStyle}>Filtrar por</label>
          <select style={{ ...input, width: 230 }} value={eixo} onChange={(e) => setEixo(e.target.value as EixoFiltroSubstitutivos)}>
            {EIXOS_SUBSTITUTIVOS.map((o) => <option key={o.chave} value={o.chave}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Item</label>
          <select style={{ ...input, width: 230 }} value={itemId} disabled={!itensEixo}
            onChange={(e) => setItemId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">{itensEixo ? "Selecione…" : "Carregando…"}</option>
            {(itensEixo || []).map((i) => <option key={i.id} value={i.id}>{i.nome}</option>)}
          </select>
        </div>
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}

      {itemId !== "" && (
        !medicamentos ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>
        ) : medicamentos.length === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum medicamento bate nesse filtro.</p>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "1.1rem" }}>
            {medicamentos.map((m) => (
              <button key={m.id} onClick={() => setPivoId(m.id)} style={{
                fontSize: "0.8rem", padding: "0.35rem 0.75rem", borderRadius: 999, cursor: "pointer", fontWeight: pivoId === m.id ? 700 : 500,
                border: "1px solid " + (pivoId === m.id ? "var(--dourado)" : "var(--border)"),
                background: pivoId === m.id ? "var(--pill-active-bg)" : "var(--surface-2)",
                color: pivoId === m.id ? "var(--pill-active-fg)" : "var(--text)",
              }}>
                {m.nome_comercial}
              </button>
            ))}
          </div>
        )
      )}

      {pivoId != null && (
        <div>
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
            Substitutos de <strong style={{ color: "var(--text)" }}>{nomePivo}</strong>, do mais pro menos parecido:
          </p>
          {!substitutos ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>
          ) : substitutos.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum outro medicamento do catálogo compartilha algum atributo clínico com este.</p>
          ) : (
            <div className="space-y-2">
              {substitutos.map((s) => <CardSubstituto key={s.id} s={s} />)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CardSubstituto({ s }: { s: MedicamentoSubstituto }) {
  const c = s.coincidencias;
  const partes: string[] = [];
  if (c.principio_ativo_ids.length) partes.push(`${c.principio_ativo_ids.length} princípio(s) ativo(s)`);
  if (c.doenca_ids.length) partes.push(`${c.doenca_ids.length} indicação(ões)`);
  if (c.categoria_medicamento_ids.length) partes.push(`${c.categoria_medicamento_ids.length} categoria(s)`);
  if (c.classificacao_medicamento_ids.length) partes.push(`${c.classificacao_medicamento_ids.length} classificação(ões)`);
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)", padding: "0.65rem 0.8rem" }}>
      <div className="flex items-center gap-2 flex-wrap">
        <strong style={{ fontSize: "0.85rem" }}>{s.nome_comercial}</strong>
        {s.laboratorio && <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>— {s.laboratorio}</span>}
        <span style={{
          marginLeft: "auto", fontSize: "0.7rem", fontWeight: 800, color: "var(--dourado-light)",
          border: "1px solid var(--dourado)", borderRadius: 999, padding: "0.1rem 0.55rem",
        }}>
          {s.pontuacao_substituto} coincidência{s.pontuacao_substituto === 1 ? "" : "s"}
        </span>
      </div>
      <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", margin: "0.3rem 0 0" }}>{partes.join(" · ")}</p>
    </div>
  );
}

function labelPrioridade(p: number): string {
  return p === 1 ? "1ª ESCOLHA" : `${p}ª OPÇÃO`;
}

// Situação de estoque do princípio dentro do card — mesma leitura semafórica
// da Farmácia antiga, com o subconjunto de campos que o catálogo expõe.
function statusEstoque(p: PrincipioIndicacaoCatalogo): { cor: string; label: string } {
  if (p.precisa_inicializar) return { cor: "var(--amber)", label: "Inicializar estoque" };
  if (p.abaixo_minimo) return { cor: "var(--red)", label: "Abaixo do mínimo" };
  if (p.total_apresentacoes > 0) return { cor: "var(--green-light)", label: `${num(p.total_apresentacoes)} em estoque` };
  return { cor: "var(--text-muted)", label: "Sem estoque cadastrado" };
}

// `contextoGlobal`: true quando renderizado dentro do Painel CowData (ver
// app/painel-cowdata/farmacia/page.tsx) — ali o token de quem chama não tem
// fazenda_id (fid=null), então o backend (ver atualizar_marca/atualizar_
// principio em farmacia.py) nunca entra no ramo de "clonar pra minha
// fazenda": edita direto a linha global (fazenda_id=None), que é o
// catálogo-padrão visto por TODAS as fazendas. Só muda textos/afordances
// que assumiriam uma fazenda específica — nenhuma chamada de API muda.
//
// No modo da fazenda (contextoGlobal ausente), agrupa duas telas: o
// Catálogo (abaixo) e o Painel de Conciliação de estoque mínimo — que só
// faz sentido por fazenda (estoque físico é sempre de UM tenant), por isso
// nunca aparece no Painel CowData.
// Configurações > Cadastro > Farmácia (fazenda): a partir da Fase F
// (01/09/2026), o Catálogo saiu daqui — não é uma tela de cadastro, é
// consulta, e passou a viver em Sanidade > Catálogo (somente leitura, ver
// components/sanidade/CatalogoFarmaciaConsulta.tsx). Aqui sobra só o Painel
// de Conciliação de estoque mínimo, que É ação de configuração por fazenda.
export default function Farmacia({ contextoGlobal }: { contextoGlobal?: boolean } = {}) {
  if (contextoGlobal) return <CatalogoFarmacia contextoGlobal />;
  return <PainelEstoqueMinimo />;
}

export function CatalogoFarmacia({ contextoGlobal, somenteLeitura }: { contextoGlobal?: boolean; somenteLeitura?: boolean } = {}) {
  const [catalogo, setCatalogo] = useState<IndicacaoCatalogo[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [tipoFiltro, setTipoFiltro] = useState("");
  const [soPersonalizadas, setSoPersonalizadas] = useState(false);
  const [restaurando, setRestaurando] = useState(false);
  const [msgRestaurar, setMsgRestaurar] = useState<string | null>(null);
  // Seção 2 — só existe dentro do Painel CowData (contextoGlobal); a
  // fazenda continua vendo só o browse por indicação (Fase F vai extrair
  // isso pra Sanidade, somente leitura).
  const [secao2, setSecao2] = useState<Secao2AbaCatalogo>("medicamentos");

  const carregar = () => fetchIndicacoesCatalogo().then(setCatalogo).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  const restaurar = async () => {
    setRestaurando(true); setMsgRestaurar(null);
    try {
      const r = await restaurarCatalogoPrincipios();
      await carregar();
      setMsgRestaurar(`Catálogo restaurado: ${r.criados} adicionado(s), ${r.total} no total.`);
    } catch (e: any) {
      setMsgRestaurar(e.message || "Erro ao restaurar catálogo");
    } finally {
      setRestaurando(false);
    }
  };

  const lista = useMemo(() => {
    let l = catalogo || [];
    if (tipoFiltro) l = l.filter((i) => i.tipo === tipoFiltro);
    if (soPersonalizadas) l = l.filter((i) => i.personalizada);
    const q = normalizar(busca.trim());
    if (q) {
      l = l.filter((i) =>
        normalizar(i.nome).includes(q) ||
        i.principios.some((p) => normalizar(p.nome).includes(q) || p.marcas.some((m) => normalizar(m.nome_comercial).includes(q))));
    }
    return l;
  }, [catalogo, tipoFiltro, soPersonalizadas, busca]);

  return (
    <div>
      {contextoGlobal && (
        <>
          <p style={secaoLabelStyle}>Seção 1 — Indicações</p>
          <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
            {SECAO1_ABAS_CATALOGO.map(([id, label]) => (
              <AbaBotaoCatalogo key={id || "todas"} ativo={secao2 === "medicamentos" && tipoFiltro === id}
                onClick={() => { setTipoFiltro(id); setSecao2("medicamentos"); }}>{label}</AbaBotaoCatalogo>
            ))}
          </div>
          <p style={secaoLabelStyle}>Seção 2 — Catálogo de farmácia</p>
          <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
            {SECAO2_ABAS_CATALOGO.map(({ chave, label, icone }) => (
              <AbaBotaoCatalogo key={chave} ativo={secao2 === chave} onClick={() => setSecao2(chave)} icone={icone}>{label}</AbaBotaoCatalogo>
            ))}
          </div>
          <p style={secaoLabelStyle}>Seção 3 — Substitutivos</p>
          <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
            {SECAO3_ABAS_CATALOGO.map(({ chave, label, icone }) => (
              <AbaBotaoCatalogo key={chave} ativo={secao2 === chave} onClick={() => setSecao2(chave)} icone={icone}>{label}</AbaBotaoCatalogo>
            ))}
          </div>
        </>
      )}

      {(!contextoGlobal || secao2 === "medicamentos") ? (
        <>
          <div className="flex items-center justify-between gap-2 mb-2" style={{ flexWrap: "wrap" }}>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", flex: "1 1 320px", margin: 0 }}>
              {somenteLeitura
                ? "Uma indicação (doença ou finalidade de manejo) por card, com os princípios ativos indicados — em ordem de prioridade — e as marcas comerciais de cada um, com bula e carência. Reflexo do catálogo mantido pelo Painel CowData — para personalizar, use Configurações > Cadastro > Farmácia."
                : contextoGlobal
                ? "Uma indicação (doença ou finalidade de manejo) por card, com os princípios ativos indicados — em ordem de prioridade — e as marcas comerciais de cada um, com bula e carência. Este é o catálogo-padrão CowData: qualquer edição feita aqui vale imediatamente para todas as fazendas que ainda não personalizaram esta indicação."
                : "Uma indicação (doença ou finalidade de manejo) por card, com os princípios ativos indicados — em ordem de prioridade — e as marcas comerciais de cada um, com bula e carência. O catálogo é o mesmo padrão para todas as fazendas — dose e carência são só um ponto de partida: edite qualquer campo que uma cópia é criada automaticamente só para a sua fazenda, sem afetar as demais."}
            </p>
            {!somenteLeitura && (
              <button className="btn-ghost" style={{ fontSize: "0.75rem", display: "inline-flex", alignItems: "center", gap: "0.35rem", whiteSpace: "nowrap" }}
                onClick={restaurar} disabled={restaurando}
                title="(Re)carrega o catálogo padrão de princípios ativos (documento base) — só adiciona o que estiver faltando, nunca sobrescreve edições.">
                <RotateCcw size={13} /> {restaurando ? "Restaurando…" : "Restaurar catálogo"}
              </button>
            )}
          </div>
          {msgRestaurar && <p style={{ color: "var(--green-light)", fontSize: "0.78rem", marginBottom: "0.6rem" }}>{msgRestaurar}</p>}

          <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
            <div style={{ position: "relative", flex: "1 1 240px", maxWidth: 340 }}>
              <Search size={14} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
              <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar indicação, princípio ou marca…"
                style={{ ...input, width: "100%", paddingLeft: "1.8rem" }} />
            </div>
            {!contextoGlobal && TIPOS_FILTRO.map(([id, label]) => (
              <button key={id || "todas"} onClick={() => setTipoFiltro(id)}
                style={{ fontSize: "0.76rem", padding: "0.32rem 0.75rem", borderRadius: 999, cursor: "pointer",
                  border: "1px solid " + (tipoFiltro === id ? "var(--dourado)" : "var(--border)"),
                  background: tipoFiltro === id ? "var(--pill-active-bg)" : "transparent",
                  color: tipoFiltro === id ? "var(--pill-active-fg)" : "var(--text-muted)", fontWeight: tipoFiltro === id ? 700 : 500 }}>
                {label}
              </button>
            ))}
            {!contextoGlobal && (
              <button onClick={() => setSoPersonalizadas((v) => !v)}
                style={{ fontSize: "0.76rem", padding: "0.32rem 0.75rem", borderRadius: 999, cursor: "pointer",
                  display: "inline-flex", alignItems: "center", gap: "0.3rem",
                  border: "1px solid " + (soPersonalizadas ? "var(--dourado)" : "var(--border)"),
                  background: soPersonalizadas ? "var(--pill-active-bg)" : "transparent",
                  color: soPersonalizadas ? "var(--pill-active-fg)" : "var(--text-muted)", fontWeight: soPersonalizadas ? 700 : 500 }}>
                <Pencil size={12} /> Só personalizadas
              </button>
            )}
          </div>

          {erro && <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}
          {!catalogo ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>
          ) : lista.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma indicação encontrada.</p>
          ) : (
            <div className="space-y-2">
              {lista.map((ind) => <CardIndicacao key={ind.id} ind={ind} onMudou={carregar} contextoGlobal={contextoGlobal} somenteLeitura={somenteLeitura} />)}
            </div>
          )}
        </>
      ) : secao2 === "principios" ? (
        <CatalogoLeituraSimples
          descricao="Lista fechada de princípios ativos — a mesma usada ao cadastrar um medicamento, tanto no Painel CowData quanto em cada fazenda."
          fetch={fetchPrincipiosFarmaciaCowData} />
      ) : secao2 === "categoriasMedicamento" ? (
        <CatalogoLeituraSimples
          descricao="Categoria (medicamento): antimicrobiano, anti-inflamatório, antibiótico... — cumulativa, um medicamento pode ter mais de uma."
          fetch={fetchCategoriasMedicamentoFarmaciaCowData} />
      ) : secao2 === "classificacoesMedicamento" ? (
        <CatalogoLeituraSimples
          descricao="Classificação do medicamento — eixo próprio, independente de Categoria, também cumulativo."
          fetch={fetchClassificacoesMedicamentoFarmaciaCowData} />
      ) : secao2 === "laboratorios" ? (
        <CatalogoLeituraSimples
          descricao="Laboratório — fabricante do medicamento, usado tanto aqui quanto no cadastro de item de estoque de cada fazenda."
          fetch={fetchLaboratoriosFarmaciaCowData} />
      ) : (
        <SubstitutivosView />
      )}
    </div>
  );
}

// Painel de Conciliação — pedido do usuário (31/08/2026): "estoque mínimo...
// tem que ser em unidade de medida. Ex.: Sincrogest — 3 pacotes de 10 + 2
// pacotes de 5 — mínimo: 12 unidades, e não pacotes." E: "muito cuidado com
// o que vai acontecer no meu banco de dados... precisa ter uma forma de ter
// um motor para eu adequar, me orientando quanto a como fazer a
// compatibilização." Por isso NADA é convertido sozinho: cada princípio que
// já tem estoque físico e ainda usa a regra antiga (mínimo em número de
// frascos/pacotes) aparece aqui pra você decidir o número certo, em
// PrincipioAtivo.unidade_base — um de cada vez (nunca em lote).
function PainelEstoqueMinimo() {
  const [lista, setLista] = useState<PrincipioFarmacia[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = () => fetchFarmaciaPrincipios().then(setLista).catch((e: any) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  const comEstoque = useMemo(() => (lista || []).filter((p) => p.qtd_marcas_estoque > 0), [lista]);
  const pendentes = useMemo(() => comEstoque.filter((p) => p.precisa_reconciliar_minimo), [comEstoque]);
  const conciliados = useMemo(() => comEstoque.filter((p) => !p.precisa_reconciliar_minimo), [comEstoque]);

  return (
    <div>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "1rem", maxWidth: "62ch" }}>
        O mínimo de cada princípio ativo passa a ser um número na unidade de medida dele (ml, litro, unidade…), não mais
        uma contagem de frascos/pacotes — assim, itens de tamanhos diferentes do mesmo remédio somam certo. Nada muda
        sozinho: enquanto você não definir o mínimo de um princípio aqui, ele continua na regra antiga (por frasco).
      </p>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}
      {!lista ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Carregando…</p>
      ) : comEstoque.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum princípio ativo com item de estoque ainda.</p>
      ) : (
        <>
          {pendentes.length > 0 && (
            <div style={{ marginBottom: "1.4rem" }}>
              <h3 style={{ fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--amber)", margin: "0 0 0.6rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <AlertTriangle size={13} /> Ainda usando a regra antiga ({pendentes.length})
              </h3>
              <div className="space-y-2">
                {pendentes.map((p) => <LinhaEstoqueMinimo key={p.id} p={p} onMudou={carregar} />)}
              </div>
            </div>
          )}
          {conciliados.length > 0 && (
            <div>
              <h3 style={{ fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--green-light)", margin: "0 0 0.6rem" }}>
                Já conciliados ({conciliados.length})
              </h3>
              <div className="space-y-2">
                {conciliados.map((p) => <LinhaEstoqueMinimo key={p.id} p={p} onMudou={carregar} />)}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function LinhaEstoqueMinimo({ p, onMudou }: { p: PrincipioFarmacia; onMudou: () => void }) {
  const [editando, setEditando] = useState(false);
  const [valor, setValor] = useState(p.estoque_minimo_base != null ? String(p.estoque_minimo_base) : "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const semUnidade = !p.unidade_base;

  const salvar = async () => {
    const n = Number(valor);
    if (!valor.trim() || Number.isNaN(n) || n < 0) { setErro("Informe um número válido."); return; }
    setSalvando(true); setErro(null);
    try { await definirEstoqueMinimoFarmacia(p.id, n); setEditando(false); onMudou(); }
    catch (e: any) { setErro(e.message || "Erro ao salvar"); }
    finally { setSalvando(false); }
  };

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)", padding: "0.65rem 0.8rem" }}>
      <div className="flex items-center gap-2 flex-wrap">
        <span style={{ fontWeight: 700, flex: "1 1 160px" }}>{p.nome}</span>
        <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
          {p.total_base != null ? `${num(p.total_base)} ${p.unidade_base}` : "—"} em estoque
        </span>
        {p.abaixo_minimo && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.7rem", fontWeight: 700, color: "var(--red)" }}>
            <AlertTriangle size={11} /> abaixo do mínimo
          </span>
        )}
        {!editando ? (
          <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => { setEditando(true); setErro(null); }} disabled={semUnidade}
            title={semUnidade ? "Cadastre a unidade de medida deste princípio antes" : "Definir mínimo"}>
            <Pencil size={11} /> {p.minimo_modo === "base" ? `Mínimo: ${num(p.estoque_minimo_base!)} ${p.unidade_base}` : "Definir mínimo em " + (p.unidade_base || "unidade")}
          </button>
        ) : (
          <span className="flex items-center gap-2">
            <input type="number" min={0} autoFocus value={valor} onChange={(e) => setValor(e.target.value)}
              style={{ width: 90, padding: "0.3rem 0.5rem", borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.82rem" }} />
            <span style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{p.unidade_base}</span>
            <button className="btn-primary" style={{ fontSize: "0.72rem" }} onClick={salvar} disabled={salvando}>
              <Check size={12} /> {salvando ? "Salvando…" : "Salvar"}
            </button>
            <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setEditando(false)}><X size={12} /></button>
          </span>
        )}
      </div>
      {p.minimo_modo === "apresentacoes" && !editando && (
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", margin: "0.35rem 0 0" }}>
          Regra antiga em uso: mínimo de {num(p.estoque_minimo_apresentacoes)} frasco(s)/pacote(s), sem olhar o tamanho de cada um.
        </p>
      )}
      {p.itens.length > 0 && (
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", margin: "0.35rem 0 0" }}>
          {p.itens.map((it) => `${it.nome} (${num(it.saldo)} ${it.unidade || ""})`).join(" + ")}
        </p>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.72rem", margin: "0.35rem 0 0" }}>{erro}</p>}
    </div>
  );
}

function CardIndicacao({ ind, onMudou, contextoGlobal, somenteLeitura }: {
  ind: IndicacaoCatalogo; onMudou: () => void; contextoGlobal?: boolean; somenteLeitura?: boolean;
}) {
  const [aberto, setAberto] = useState(false);
  const [processando, setProcessando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [avisoPersonalizacao, setAvisoPersonalizacao] = useState(false);
  const tipoInfo = TIPO_INFO[ind.tipo] || { label: ind.tipo, cor: "var(--text-muted)" };

  // Repassado aos filhos (princípio/marca): quando a edição de um campo do
  // padrão dispara a personalização automática (`personalizou_automaticamente`
  // na resposta do PUT), avisa aqui e recarrega a lista.
  const onMudouFilho = (personalizouAutomaticamente?: boolean) => {
    if (personalizouAutomaticamente) setAvisoPersonalizacao(true);
    onMudou();
  };

  const personalizar = async () => {
    setProcessando(true); setErro(null);
    try { await personalizarIndicacao(ind.id); onMudou(); }
    catch (e: any) { setErro(e.message || "Erro ao personalizar"); }
    finally { setProcessando(false); }
  };
  // "Voltar ao padrão" (despersonalizar) foi removido a pedido do usuário
  // (31/08/2026) — reverter em lote assustava mais do que ajudava. Qualquer
  // ajuste numa indicação personalizada agora é sempre feito campo a campo
  // (editar bula/prioridade um de cada vez), nunca um botão de "desfazer tudo".

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.7rem 0.9rem", background: "var(--surface-2)" }}>
        <button onClick={() => setAberto((v) => !v)}
          style={{ display: "flex", alignItems: "center", gap: "0.6rem", flex: 1, minWidth: 0, background: "none", border: "none", cursor: "pointer", color: "var(--text)", textAlign: "left", padding: 0 }}>
          {aberto ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <span style={{
            fontSize: "0.64rem", fontWeight: 800, letterSpacing: "0.03em", textTransform: "uppercase",
            color: tipoInfo.cor, border: "1px solid " + tipoInfo.cor, borderRadius: 4, padding: "0.1rem 0.4rem", flexShrink: 0,
          }}>
            {tipoInfo.label}
          </span>
          <span style={{ flex: 1, minWidth: 0 }}>
            <span style={{ fontWeight: 700 }}>{ind.nome}</span>
            {ind.descricao && <span style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted)" }}>{ind.descricao}</span>}
          </span>
          <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", flexShrink: 0 }}>
            {ind.principios.length} princípio{ind.principios.length === 1 ? "" : "s"}
          </span>
        </button>
        <span style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: "0.4rem" }}>
          {ind.personalizada ? (
            <span title="Personalizada para a sua fazenda" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.68rem", fontWeight: 700, color: "var(--dourado-light)" }}>
              <Pencil size={12} /> Personalizada
            </span>
          ) : contextoGlobal || somenteLeitura ? (
            <span title="Catálogo-padrão CowData — edições aqui valem para todas as fazendas que não personalizaram esta indicação." style={{ display: "inline-flex", color: "var(--text-muted)" }}>
              <Lock size={14} />
            </span>
          ) : (
            <>
              <span title="Este é o padrão CowData. Ao editar qualquer campo, uma cópia passa a valer só para a sua fazenda." style={{ display: "inline-flex", color: "var(--text-muted)" }}>
                <Lock size={14} />
              </span>
              <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={personalizar} disabled={processando}>
                {processando ? "Aguarde…" : "Personalizar para minha fazenda"}
              </button>
            </>
          )}
        </span>
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem", padding: "0.4rem 0.9rem 0" }}>{erro}</p>}
      {avisoPersonalizacao && (
        <p style={{
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
          color: "var(--dourado-light)", fontSize: "0.76rem", padding: "0.4rem 0.9rem", margin: 0,
          background: "rgba(184,134,11,0.08)", borderTop: "1px solid var(--border)",
        }}>
          <span>Esta indicação agora é personalizada da sua fazenda.</span>
          <button onClick={() => setAvisoPersonalizacao(false)} style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", display: "inline-flex", flexShrink: 0 }} title="Dispensar aviso">
            <X size={13} />
          </button>
        </p>
      )}

      {aberto && (
        <div style={{ padding: "0.85rem" }}>
          {ind.principios.length === 0 ? (
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Nenhum princípio ativo indicado ainda para esta indicação.</p>
          ) : (
            <div className="space-y-3">
              {ind.principios.map((p) => (
                <PrincipioBloco key={p.id} p={p} indicacaoPersonalizada={ind.personalizada} onMudou={onMudouFilho} contextoGlobal={contextoGlobal} somenteLeitura={somenteLeitura} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PrincipioBloco({ p, indicacaoPersonalizada, onMudou, contextoGlobal, somenteLeitura }: {
  p: PrincipioIndicacaoCatalogo; indicacaoPersonalizada: boolean; onMudou: (personalizouAutomaticamente?: boolean) => void;
  contextoGlobal?: boolean; somenteLeitura?: boolean;
}) {
  const [editandoVinculo, setEditandoVinculo] = useState(false);
  const [prioridade, setPrioridade] = useState(String(p.prioridade));
  const [nota, setNota] = useState(p.nota || "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const status = statusEstoque(p);
  const primeiraEscolha = p.prioridade === 1;

  const salvarVinculo = async () => {
    setSalvando(true); setErro(null);
    try {
      const r = await atualizarVinculoIndicacao(p.indicacao_id, { prioridade: Number(prioridade) || 1, nota: nota.trim() || null });
      setEditandoVinculo(false);
      onMudou(r.personalizou_automaticamente);
    } catch (e: any) { setErro(e.message || "Erro ao salvar"); }
    finally { setSalvando(false); }
  };

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-2)", padding: "0.65rem 0.8rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
        <span style={{
          fontSize: "0.66rem", fontWeight: 800, borderRadius: 4, padding: "0.15rem 0.4rem", flexShrink: 0, whiteSpace: "nowrap",
          ...(primeiraEscolha
            ? { border: "1px solid var(--dourado)", color: "var(--dourado-light)", background: "rgba(184,134,11,0.12)" }
            : { border: "1px solid var(--border)", color: "var(--text-muted)" }),
        }}>
          {labelPrioridade(p.prioridade)}
        </span>
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: status.cor, flexShrink: 0 }} title={status.label} />
        <span style={{ flex: 1, minWidth: 0, fontWeight: 700 }}>
          {p.nome}
          {p.categoria_software && <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.72rem" }}> · {p.categoria_software}</span>}
        </span>
        <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", flexShrink: 0 }}>{status.label}</span>
        {!indicacaoPersonalizada && (
          <span title={contextoGlobal ? "Catálogo-padrão CowData — vale para todas as fazendas." : "Este é o padrão CowData. Ao editar, uma cópia passa a valer só para a sua fazenda."} style={{ display: "inline-flex", color: "var(--text-muted)" }}>
            <Lock size={11} />
          </span>
        )}
        {!somenteLeitura && (
          <button className="btn-ghost" style={{ fontSize: "0.68rem", padding: "0.15rem 0.5rem" }} onClick={() => setEditandoVinculo((v) => !v)}
            title={indicacaoPersonalizada || contextoGlobal ? "Editar prioridade/nota" : "Editar prioridade/nota — cria uma cópia para a sua fazenda"}>
            <Pencil size={11} />
          </button>
        )}
      </div>
      {p.nota && !editandoVinculo && <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", margin: "0.3rem 0 0" }}>{p.nota}</p>}

      {editandoVinculo && (
        <div className="flex items-end gap-2" style={{ marginTop: "0.5rem", flexWrap: "wrap" }}>
          <div><label style={labelStyle}>Prioridade</label>
            <input type="number" min={1} style={{ ...input, width: 80 }} value={prioridade} onChange={(e) => setPrioridade(e.target.value)} /></div>
          <div style={{ flex: "1 1 200px" }}><label style={labelStyle}>Nota</label>
            <input style={{ ...input, width: "100%" }} value={nota} onChange={(e) => setNota(e.target.value)} placeholder="opcional" /></div>
          <button className="btn-primary" style={{ fontSize: "0.72rem" }} onClick={salvarVinculo} disabled={salvando}>
            <Check size={12} /> {salvando ? "Salvando…" : "Salvar"}
          </button>
          <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setEditandoVinculo(false)}><X size={12} /></button>
          {erro && <span style={{ color: "var(--red)", fontSize: "0.74rem" }}>{erro}</span>}
        </div>
      )}

      {p.marcas.length === 0 ? (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Nenhuma marca comercial cadastrada para este princípio.</p>
      ) : (
        <div className="space-y-2" style={{ marginTop: "0.55rem" }}>
          {p.marcas.map((m) => <MarcaLinha key={m.id} m={m} principioId={p.id} onMudou={onMudou} contextoGlobal={contextoGlobal} somenteLeitura={somenteLeitura} />)}
        </div>
      )}
    </div>
  );
}

function MarcaLinha({ m, principioId, onMudou, contextoGlobal, somenteLeitura }: {
  m: MarcaIndicacaoCatalogo; principioId: number; onMudou: (personalizouAutomaticamente?: boolean) => void;
  contextoGlobal?: boolean; somenteLeitura?: boolean;
}) {
  const [editando, setEditando] = useState(false);
  const semInfo = carenciaNaoInformada(m.carencia);

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface)", padding: "0.55rem 0.7rem" }}>
      <div className="flex items-start justify-between gap-2" style={{ flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 220px", minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
            {m.nome_comercial}
            {m.laboratorio && <span style={{ fontWeight: 400, fontSize: "0.72rem", color: "var(--text-muted)" }}>— {m.laboratorio}</span>}
            {!m.editavel && (
              <span title={contextoGlobal ? "Catálogo-padrão CowData — vale para todas as fazendas." : "Este é o padrão CowData. Ao editar, uma cópia passa a valer só para a sua fazenda."} style={{ display: "inline-flex", color: "var(--text-muted)" }}>
                <Lock size={12} />
              </span>
            )}
            {m.link_bula && (
              <a href={m.link_bula} target="_blank" rel="noopener noreferrer" title="Ver bula"
                style={{ color: "var(--dourado-light)", display: "inline-flex" }}>
                <ExternalLink size={12} />
              </a>
            )}
          </div>
          {m.uso_principal && <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>{m.uso_principal}</div>}
          <div style={{ fontSize: "0.76rem", color: "var(--text)", marginTop: "0.15rem" }}>
            {m.dose_texto || (m.dose_padrao != null ? `${num(m.dose_padrao)} ${m.unidade_dose || ""}` : "Dose não informada")}
            {m.via_padrao && <span style={{ color: "var(--text-muted)" }}> · {m.via_padrao}</span>}
          </div>
        </div>

        {!somenteLeitura && (
          <button className="btn-ghost" style={{ fontSize: "0.7rem", flexShrink: 0 }} onClick={() => setEditando((v) => !v)}
            title={m.editavel || contextoGlobal ? "Editar bula" : "Editar bula — cria uma cópia para a sua fazenda"}>
            <Pencil size={12} /> {editando ? "Fechar" : "Editar bula"}
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap" style={{ marginTop: "0.45rem" }}>
        {m.carencia.proibido_lactacao ? (
          <span style={{
            display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.72rem", fontWeight: 800,
            color: "#fff", background: "var(--red)", border: "1px solid var(--red)", borderRadius: 999, padding: "0.2rem 0.65rem",
          }}>
            <Ban size={12} /> NÃO USAR EM LACTAÇÃO
          </span>
        ) : (
          <span style={{ fontSize: "0.72rem", fontWeight: semInfo ? 500 : 600, color: semInfo ? "var(--text-muted)" : "var(--text)", fontStyle: semInfo ? "italic" : "normal" }}>
            {m.carencia.texto}
          </span>
        )}
        {(m.alerta_gestacao || m.alerta) && (
          <span title={m.alerta || undefined} style={{
            display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.7rem", fontWeight: 700,
            color: "var(--amber)", background: "rgba(217,119,6,0.1)", border: "1px solid var(--amber)", borderRadius: 999, padding: "0.15rem 0.55rem",
          }}>
            <AlertTriangle size={11} /> {m.alerta_gestacao ? "Atenção — gestação" : "Alerta"}
          </span>
        )}
      </div>

      {editando && (
        <FormEdicaoMarca principioId={principioId} marcaId={m.id}
          onSalvo={(personalizouAutomaticamente) => { setEditando(false); onMudou(personalizouAutomaticamente); }}
          onCancelar={() => setEditando(false)} />
      )}
    </div>
  );
}

// Formulário de bula — carrega o registro COMPLETO da marca (via
// /farmacia/principios/{id}, que devolve todos os campos de MedicamentoComercial)
// antes de editar, porque o PUT /farmacia/medicamentos/{id} substitui a marca
// inteira: usar só os campos do catálogo (que não inclui dose_base/
// dose_referencia_kg/ativo) apagaria esses campos ao salvar.
function FormEdicaoMarca({ principioId, marcaId, onSalvo, onCancelar }: {
  principioId: number; marcaId: number; onSalvo: (personalizouAutomaticamente?: boolean) => void; onCancelar: () => void;
}) {
  const [form, setForm] = useState<Record<string, any> | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    fetchFarmaciaDetalhe(principioId)
      .then((d: any) => {
        if (cancelado) return;
        const full = (d.marcas || []).find((mm: any) => mm.id === marcaId);
        if (!full) { setErro("Marca não encontrada"); return; }
        setForm({ ...full });
      })
      .catch((e: any) => !cancelado && setErro(e.message || "Erro ao carregar a marca"))
      .finally(() => !cancelado && setCarregando(false));
    return () => { cancelado = true; };
  }, [principioId, marcaId]);

  const salvar = async () => {
    if (!form) return;
    setSalvando(true); setErro(null);
    try {
      const r = await atualizarMarcaFarmacia(marcaId, {
        ...form,
        dose_padrao: form.dose_padrao === "" ? null : Number(form.dose_padrao),
        dose_referencia_kg: form.dose_referencia_kg === "" ? null : Number(form.dose_referencia_kg),
        carencia_leite_dias: form.carencia_leite_dias === "" || form.carencia_leite_dias == null ? null : Number(form.carencia_leite_dias),
        carencia_carne_dias: form.carencia_carne_dias === "" || form.carencia_carne_dias == null ? null : Number(form.carencia_carne_dias),
      });
      onSalvo(r.personalizou_automaticamente);
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar a bula");
    } finally {
      setSalvando(false);
    }
  };

  if (carregando) return <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Carregando…</p>;
  if (!form) return <p style={{ fontSize: "0.76rem", color: "var(--red)", marginTop: "0.5rem" }}>{erro || "Não foi possível carregar."}</p>;

  const set = (k: string, v: any) => setForm((f) => (f ? { ...f, [k]: v } : f));

  return (
    <div style={{ marginTop: "0.6rem", padding: "0.6rem", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6 }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-2">
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Uso principal</label>
          <input style={{ ...input, width: "100%" }} value={form.uso_principal || ""} onChange={(e) => set("uso_principal", e.target.value)} /></div>
        <div><label style={labelStyle}>Concentração</label>
          <input style={{ ...input, width: "100%" }} value={form.concentracao || ""} onChange={(e) => set("concentracao", e.target.value)} /></div>

        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Dose (texto exibido)</label>
          <input style={{ ...input, width: "100%" }} value={form.dose_texto || ""} onChange={(e) => set("dose_texto", e.target.value)} placeholder="ex.: 1 ml/50kg PV" /></div>
        <div><label style={labelStyle}>Via</label>
          <select style={{ ...input, width: "100%" }} value={form.via_padrao || ""} onChange={(e) => set("via_padrao", e.target.value)}>
            <option value="">—</option>{VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
          </select></div>

        <div><label style={labelStyle}>Dose padrão</label>
          <input type="number" inputMode="decimal" style={{ ...input, width: "100%" }} value={form.dose_padrao ?? ""} onChange={(e) => set("dose_padrao", e.target.value)} /></div>
        <div><label style={labelStyle}>Unidade da dose</label>
          <input style={{ ...input, width: "100%" }} value={form.unidade_dose || ""} onChange={(e) => set("unidade_dose", e.target.value)} placeholder="ml, unidade…" /></div>
        <div><label style={labelStyle}>Laboratório</label>
          <input style={{ ...input, width: "100%" }} value={form.laboratorio || ""} onChange={(e) => set("laboratorio", e.target.value)} /></div>

        <div style={{ gridColumn: "span 3" }}><label style={labelStyle}>Link da bula</label>
          <input style={{ ...input, width: "100%" }} value={form.link_bula || ""} onChange={(e) => set("link_bula", e.target.value)} placeholder="https://…" /></div>

        <div><label style={labelStyle}>Carência do leite (dias)</label>
          <input type="number" min={0} style={{ ...input, width: "100%" }} value={form.carencia_leite_dias ?? ""} onChange={(e) => set("carencia_leite_dias", e.target.value)} disabled={!!form.proibido_lactacao} /></div>
        <div><label style={labelStyle}>Carência da carne (dias)</label>
          <input type="number" min={0} style={{ ...input, width: "100%" }} value={form.carencia_carne_dias ?? ""} onChange={(e) => set("carencia_carne_dias", e.target.value)} /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.76rem" }}>
          <input type="checkbox" checked={!!form.proibido_lactacao} onChange={(e) => set("proibido_lactacao", e.target.checked)} /> Não usar em lactação</label></div>

        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Alerta (texto)</label>
          <input style={{ ...input, width: "100%" }} value={form.alerta || ""} onChange={(e) => set("alerta", e.target.value)} placeholder="opcional" /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.76rem" }}>
          <input type="checkbox" checked={!!form.alerta_gestacao} onChange={(e) => set("alerta_gestacao", e.target.checked)} /> Alerta de gestação</label></div>
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.76rem", marginBottom: "0.4rem" }}>{erro}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.74rem" }} onClick={salvar} disabled={salvando}>
          <Check size={13} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.74rem" }} onClick={onCancelar}>
          <X size={13} /> Cancelar
        </button>
      </div>
    </div>
  );
}
