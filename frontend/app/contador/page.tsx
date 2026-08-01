"use client";
// Painel do Contador — Financeiro somente leitura/exportação por padrão (ver
// proposta aprovada: vínculo UsuarioFazenda.contador, sem gate de plano).
// Duas exceções deliberadas: a aba Documentos (arquivo fiscal-contábil,
// sempre liberada) e a aba Ações extraordinárias (lançamento avulso/juros/
// chamado, atrás do cadeado por senha — ver frontend/lib/useCadeado.ts e
// backend/fazenda/auth.py::bloquear_escrita_contador). Não tem equivalente
// no app móvel (ver AuthShell.tsx e app/contador/layout.tsx).
import { useEffect, useMemo, useState } from "react";
import { Download, Paperclip } from "lucide-react";
import {
  fetchLancamentos, fetchPlanoContas, fetchOpcoesFinanceiro, fetchRmca, fetchPatrimonio,
  fetchFolhaPagamentoUnificada, fetchRelatorioCompraVendaAnimais, listarAnexosLancamento, urlAnexoLancamento,
  formatBRL, formatDate, type LinhaFolhaUnificada, type LinhaRelatorioCompraVendaAnimal, type AnexoLancamento,
} from "@/lib/api";
import { exportarMultiExcel, type SecaoFicha } from "@/lib/export";
import type { ContaPlano } from "@/lib/contaGerencial";
import { CORES_CONTADOR } from "./layout";
import { PainelDocumentos } from "@/components/contador/PainelDocumentos";
import { PainelExtraordinario } from "@/components/contador/PainelExtraordinario";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

type Lancamento = {
  id: number; numero_lancamento: string; tipo: string; valor: number; centro_custo: string; codigo_conta: string;
  descricao: string; fornecedor: string; numero_documento?: string | null;
  data_competencia: string | null; data_pagamento: string | null; data_vencimento: string | null;
};

type ItemPatrimonio = {
  id: number; tipo: string | null; nome: string; numero: string | null;
  data_imobilizacao: string | null; metodo_depreciacao: string | null;
  valor_total: number | null; depreciacao_acumulada: number | null; valor_atual: number | null;
};
type Patrimonio = { itens: ItemPatrimonio[]; valor_total: number; valor_atual_total: number };

type RmcaResp = {
  configurado: boolean;
  contas_receita: string[]; contas_custo: string[];
  gerencial: { receita_leite: number; custo_alimentacao: number; rmca: number };
  fisico: { receita_leite: number; custo_alimentacao: number; rmca: number; itens: { ingrediente: string; quantidade: number; valor_unitario: number; custo: number }[] };
};

const ABAS = [
  { id: "dre", label: "DRE" },
  { id: "rmca", label: "RMCA" },
  { id: "plano", label: "Plano de contas" },
  { id: "extrato", label: "Extrato" },
  { id: "patrimonio", label: "Patrimônio" },
  { id: "folha", label: "Folha de pagamento" },
  { id: "animais", label: "Compra/venda de animais" },
  { id: "documentos", label: "Documentos" },
  { id: "extraordinario", label: "Ações extraordinárias" },
] as const;
type Aba = (typeof ABAS)[number]["id"];

function primeiroDiaDoMes() {
  const h = new Date();
  return new Date(h.getFullYear(), h.getMonth(), 1).toISOString().slice(0, 10);
}
function hoje() {
  return new Date().toISOString().slice(0, 10);
}
function dentroPeriodo(data: string | null, inicio: string, fim: string) {
  if (!data) return false;
  return data >= inicio && data <= fim;
}

const estiloCard: React.CSSProperties = {
  background: CORES_CONTADOR.painel, border: `1px solid ${CORES_CONTADOR.borda}`, borderRadius: "4px", padding: "1.3rem",
};
const estiloInput: React.CSSProperties = {
  background: CORES_CONTADOR.painelAlt, color: CORES_CONTADOR.texto, border: `1px solid ${CORES_CONTADOR.borda}`,
  borderRadius: "3px", padding: "0.4rem 0.6rem", fontSize: "0.85rem",
};
const estiloTh: React.CSSProperties = {
  textAlign: "left", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em",
  color: CORES_CONTADOR.mudo, borderBottom: `1px solid ${CORES_CONTADOR.bordaClara}`, padding: "0.5rem 0.6rem", fontWeight: 700,
};
const estiloTd: React.CSSProperties = {
  fontSize: "0.82rem", padding: "0.5rem 0.6rem", borderBottom: `1px solid ${CORES_CONTADOR.borda}`, fontVariantNumeric: "tabular-nums",
};
// Cabeçalhos ordenáveis (ThOrdenavel, ver components/Ordenavel.tsx) renderizam
// um <th> sem estilo próprio de cor/borda — como o Painel do Contador não usa
// a classe .fazenda-table (paleta deliberadamente distinta, ver layout.tsx),
// aplicamos o mesmo visual de estiloTh via CSS de classe (propriedades como
// padding/border não herdam do <thead>, então precisam de uma regra própria).
const ESTILO_TH_ORDENAVEL = `
  .contador-th thead th {
    padding: 0.5rem 0.6rem;
    border-bottom: 1px solid ${CORES_CONTADOR.bordaClara};
    text-align: left;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: ${CORES_CONTADOR.mudo};
    font-weight: 700;
  }
`;

function Kpi({ titulo, valor, cor }: { titulo: string; valor: string; cor?: string }) {
  return (
    <div style={{ ...estiloCard, padding: "0.9rem 1.1rem" }}>
      <p style={{ margin: 0, fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em", color: CORES_CONTADOR.mudo }}>{titulo}</p>
      <p style={{ margin: "0.3rem 0 0", fontSize: "1.3rem", fontWeight: 700, color: cor || CORES_CONTADOR.texto, fontVariantNumeric: "tabular-nums" }}>{valor}</p>
    </div>
  );
}

function AnexosLinha({ numeroLancamento }: { numeroLancamento: string }) {
  const [aberto, setAberto] = useState(false);
  const [anexos, setAnexos] = useState<AnexoLancamento[] | null>(null);
  const carregar = () => {
    if (aberto) { setAberto(false); return; }
    setAberto(true);
    if (anexos === null) listarAnexosLancamento(numeroLancamento).then(setAnexos).catch(() => setAnexos([]));
  };
  return (
    <span style={{ position: "relative" }}>
      <button type="button" onClick={carregar} title="Ver anexos"
        style={{ background: "none", border: "none", padding: 0, color: CORES_CONTADOR.cobreClaro, cursor: "pointer", display: "inline-flex", alignItems: "center" }}>
        <Paperclip size={13} />
      </button>
      {aberto && (
        <div style={{
          position: "absolute", top: "1.4rem", right: 0, zIndex: 10, minWidth: "12rem",
          background: CORES_CONTADOR.painelAlt, border: `1px solid ${CORES_CONTADOR.bordaClara}`, borderRadius: "3px", padding: "0.5rem",
        }}>
          {anexos === null && <p style={{ fontSize: "0.75rem", color: CORES_CONTADOR.mudo, margin: 0 }}>Carregando…</p>}
          {anexos?.length === 0 && <p style={{ fontSize: "0.75rem", color: CORES_CONTADOR.mudo, margin: 0 }}>Sem anexos.</p>}
          {anexos?.map((a) => (
            <a key={a.id} href={urlAnexoLancamento(a.id)} target="_blank" rel="noreferrer"
              style={{ display: "block", fontSize: "0.75rem", color: CORES_CONTADOR.texto, textDecoration: "none", padding: "0.15rem 0" }}>
              {a.nome_arquivo}
            </a>
          ))}
        </div>
      )}
    </span>
  );
}

export default function PainelContadorPage() {
  const [aba, setAba] = useState<Aba>("dre");
  const [lancamentos, setLancamentos] = useState<Lancamento[]>([]);
  const [planoContas, setPlanoContas] = useState<ContaPlano[]>([]);
  const [centros, setCentros] = useState<string[]>([]);
  const [patrimonio, setPatrimonio] = useState<Patrimonio | null>(null);
  const [folha, setFolha] = useState<LinhaFolhaUnificada[]>([]);
  const [animais, setAnimais] = useState<LinhaRelatorioCompraVendaAnimal[]>([]);
  const [rmca, setRmca] = useState<RmcaResp | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [exportando, setExportando] = useState(false);

  const [inicio, setInicio] = useState(primeiroDiaDoMes());
  const [fim, setFim] = useState(hoje());
  const [centro, setCentro] = useState("");
  const [tipoExtrato, setTipoExtrato] = useState<"ambos" | "receita" | "despesa">("ambos");

  useEffect(() => {
    Promise.all([
      fetchLancamentos(), fetchPlanoContas(), fetchOpcoesFinanceiro(), fetchPatrimonio(),
      fetchFolhaPagamentoUnificada(), fetchRelatorioCompraVendaAnimais({}),
    ])
      .then(([lc, pc, op, pat, fp, an]) => {
        setLancamentos(lc.lancamentos || []);
        setPlanoContas(pc);
        setCentros(op.centros_custo || []);
        setPatrimonio(pat);
        setFolha(fp);
        setAnimais(an);
      })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, []);

  useEffect(() => {
    fetchRmca(inicio, fim).then(setRmca).catch(() => setRmca(null));
  }, [inicio, fim]);

  const nomePorCodigo = useMemo(() => new Map(planoContas.map((c) => [c.codigo, c.nome])), [planoContas]);

  const noPeriodo = useMemo(
    () => lancamentos.filter((l) => dentroPeriodo(l.data_competencia, inicio, fim) && (!centro || l.centro_custo === centro)),
    [lancamentos, inicio, fim, centro],
  );

  const dre = useMemo(() => {
    const porConta = new Map<string, { receita: number; despesa: number }>();
    for (const l of noPeriodo) {
      const acc = porConta.get(l.codigo_conta) || { receita: 0, despesa: 0 };
      if (l.tipo === "receita") acc.receita += l.valor; else acc.despesa += l.valor;
      porConta.set(l.codigo_conta, acc);
    }
    const linhas = Array.from(porConta.entries()).map(([codigo, v]) => ({ codigo, nome: nomePorCodigo.get(codigo) || codigo, ...v }));
    const receitas = linhas.filter((l) => l.receita > 0).sort((a, b) => b.receita - a.receita);
    const despesas = linhas.filter((l) => l.despesa > 0).sort((a, b) => b.despesa - a.despesa);
    const receitaTotal = linhas.reduce((a, l) => a + l.receita, 0);
    const despesaTotal = linhas.reduce((a, l) => a + l.despesa, 0);
    return { receitas, despesas, receitaTotal, despesaTotal, resultado: receitaTotal - despesaTotal };
  }, [noPeriodo, nomePorCodigo]);

  const extratoFiltrado = useMemo(
    () => noPeriodo.filter((l) => tipoExtrato === "ambos" || l.tipo === tipoExtrato)
      .sort((a, b) => (b.data_competencia || "").localeCompare(a.data_competencia || "")),
    [noPeriodo, tipoExtrato],
  );

  const animaisNoPeriodo = useMemo(
    () => animais.filter((a) => a.data >= inicio && a.data <= fim),
    [animais, inicio, fim],
  );

  const folhaNoPeriodo = useMemo(
    () => folha.filter((f) => dentroPeriodo(f.data_vencimento, inicio, fim)),
    [folha, inicio, fim],
  );

  const ordReceitas = useOrdenacao(dre.receitas);
  const ordDespesas = useOrdenacao(dre.despesas);
  const ordPlano = useOrdenacao(planoContas);
  const ordExtrato = useOrdenacao(extratoFiltrado);
  const ordPatrimonio = useOrdenacao(patrimonio?.itens || []);
  const ordFolha = useOrdenacao(folhaNoPeriodo);
  const ordAnimais = useOrdenacao(animaisNoPeriodo);

  const exportarFechamentoMensal = async () => {
    setExportando(true);
    try {
      const secoes: SecaoFicha[] = [
        {
          titulo: "DRE — Receitas", linhas: dre.receitas,
          colunas: [{ header: "Conta", key: "nome", width: 30 }, { header: "Valor", key: "receita", width: 16 }],
        },
        {
          titulo: "DRE — Despesas", linhas: dre.despesas,
          colunas: [{ header: "Conta", key: "nome", width: 30 }, { header: "Valor", key: "despesa", width: 16 }],
        },
        {
          titulo: "Extrato", linhas: extratoFiltrado,
          colunas: [
            { header: "Data", key: "data_competencia", width: 12 }, { header: "Tipo", key: "tipo", width: 10 },
            { header: "Fornecedor/Cliente", key: "fornecedor", width: 24 }, { header: "Descrição", key: "descricao", width: 28 },
            { header: "Centro de custo", key: "centro_custo", width: 18 }, { header: "Valor", key: "valor", width: 14 },
            { header: "Pagamento", key: "data_pagamento", width: 12 },
          ],
        },
        {
          titulo: "Patrimônio", linhas: patrimonio?.itens || [],
          colunas: [
            { header: "Nome", key: "nome", width: 26 }, { header: "Tipo", key: "tipo", width: 14 },
            { header: "Valor total", key: "valor_total", width: 14 }, { header: "Depreciação acum.", key: "depreciacao_acumulada", width: 16 },
            { header: "Valor atual", key: "valor_atual", width: 14 },
          ],
        },
        {
          titulo: "Folha de pagamento", linhas: folha.filter((f) => dentroPeriodo(f.data_vencimento, inicio, fim)),
          colunas: [
            { header: "Pessoa", key: "pessoa_nome", width: 22 }, { header: "Descrição", key: "descricao", width: 26 },
            { header: "Valor", key: "valor", width: 14 }, { header: "Vencimento", key: "data_vencimento", width: 12 },
            { header: "Pagamento", key: "data_pagamento", width: 12 }, { header: "Status", key: "status", width: 10 },
          ],
        },
      ].filter((s) => s.linhas.length > 0);
      await exportarMultiExcel(`Fechamento mensal (${formatDate(inicio)} a ${formatDate(fim)})`, secoes, "fechamento_mensal");
    } catch {
      // erro já mostrado ao usuário dentro de exportarMultiExcel (lib/export.ts)
    } finally {
      setExportando(false);
    }
  };

  if (carregando) return <p style={{ color: CORES_CONTADOR.mudo }}>Carregando…</p>;
  if (erro) return <p style={{ color: CORES_CONTADOR.negativo }}>Não foi possível carregar os dados financeiros: {erro}</p>;

  return (
    <div>
      <style>{ESTILO_TH_ORDENAVEL}</style>
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-end", gap: "0.8rem", marginBottom: "1.2rem" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.7rem", alignItems: "flex-end" }}>
          <div>
            <label style={{ fontSize: "0.68rem", color: CORES_CONTADOR.mudo, display: "block", marginBottom: "0.2rem" }}>Início</label>
            <input type="date" style={estiloInput} value={inicio} onChange={(e) => setInicio(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: "0.68rem", color: CORES_CONTADOR.mudo, display: "block", marginBottom: "0.2rem" }}>Fim</label>
            <input type="date" style={estiloInput} value={fim} onChange={(e) => setFim(e.target.value)} />
          </div>
          {centros.length > 0 && (
            <div>
              <label style={{ fontSize: "0.68rem", color: CORES_CONTADOR.mudo, display: "block", marginBottom: "0.2rem" }}>Centro de custo</label>
              <select style={estiloInput} value={centro} onChange={(e) => setCentro(e.target.value)}>
                <option value="">Todos</option>
                {centros.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}
        </div>
        <button type="button" onClick={exportarFechamentoMensal} disabled={exportando}
          style={{
            display: "flex", alignItems: "center", gap: "0.4rem", background: CORES_CONTADOR.cobre, color: "#fff",
            border: "none", borderRadius: "3px", padding: "0.55rem 0.9rem", fontSize: "0.8rem", fontWeight: 700, cursor: "pointer",
          }}>
          <Download size={14} /> {exportando ? "Gerando…" : "Fechamento mensal (Excel)"}
        </button>
      </div>

      <div style={{ display: "flex", gap: "0.2rem", borderBottom: `1px solid ${CORES_CONTADOR.borda}`, marginBottom: "1.3rem", flexWrap: "wrap" }}>
        {ABAS.map((t) => (
          <button key={t.id} type="button" onClick={() => setAba(t.id)}
            style={{
              background: "none", border: "none", borderBottom: aba === t.id ? `2px solid ${CORES_CONTADOR.cobre}` : "2px solid transparent",
              color: aba === t.id ? CORES_CONTADOR.cobreClaro : CORES_CONTADOR.mudo, fontWeight: aba === t.id ? 700 : 500,
              fontSize: "0.82rem", padding: "0.6rem 0.8rem", cursor: "pointer",
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {aba === "dre" && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(9rem, 1fr))", gap: "0.8rem", marginBottom: "1.2rem" }}>
            <Kpi titulo="Receita" valor={formatBRL(dre.receitaTotal)} cor={CORES_CONTADOR.positivo} />
            <Kpi titulo="Despesa" valor={formatBRL(dre.despesaTotal)} cor={CORES_CONTADOR.negativo} />
            <Kpi titulo="Resultado" valor={formatBRL(dre.resultado)} cor={dre.resultado >= 0 ? CORES_CONTADOR.positivo : CORES_CONTADOR.negativo} />
            <Kpi titulo="Margem" valor={dre.receitaTotal > 0 ? `${((dre.resultado / dre.receitaTotal) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%` : "—"} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }} className="contador-grid-2">
            <div style={estiloCard}>
              <p style={{ margin: "0 0 0.7rem", fontFamily: "inherit", fontWeight: 700, fontSize: "0.85rem" }}>Receitas por conta</p>
              <table className="contador-th" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr>
                  <ThOrdenavel label="Conta" campo="nome" coluna={ordReceitas.coluna} dir={ordReceitas.dir} ordenar={ordReceitas.ordenar} />
                  <ThOrdenavel label="Valor" campo="receita" coluna={ordReceitas.coluna} dir={ordReceitas.dir} ordenar={ordReceitas.ordenar} alinhar="right" />
                </tr></thead>
                <tbody>
                  {ordReceitas.linhasOrdenadas.map((l) => (
                    <tr key={l.codigo}><td style={estiloTd}>{l.nome}</td><td style={{ ...estiloTd, textAlign: "right", color: CORES_CONTADOR.positivo }}>{formatBRL(l.receita)}</td></tr>
                  ))}
                  {dre.receitas.length === 0 && <tr><td style={estiloTd} colSpan={2}>Sem receitas no período.</td></tr>}
                </tbody>
              </table>
            </div>
            <div style={estiloCard}>
              <p style={{ margin: "0 0 0.7rem", fontWeight: 700, fontSize: "0.85rem" }}>Despesas por conta</p>
              <table className="contador-th" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr>
                  <ThOrdenavel label="Conta" campo="nome" coluna={ordDespesas.coluna} dir={ordDespesas.dir} ordenar={ordDespesas.ordenar} />
                  <ThOrdenavel label="Valor" campo="despesa" coluna={ordDespesas.coluna} dir={ordDespesas.dir} ordenar={ordDespesas.ordenar} alinhar="right" />
                </tr></thead>
                <tbody>
                  {ordDespesas.linhasOrdenadas.map((l) => (
                    <tr key={l.codigo}><td style={estiloTd}>{l.nome}</td><td style={{ ...estiloTd, textAlign: "right", color: CORES_CONTADOR.negativo }}>{formatBRL(l.despesa)}</td></tr>
                  ))}
                  {dre.despesas.length === 0 && <tr><td style={estiloTd} colSpan={2}>Sem despesas no período.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {aba === "rmca" && (
        <div>
          {!rmca && <p style={{ color: CORES_CONTADOR.mudo }}>Carregando…</p>}
          {rmca && (
            <>
              {!rmca.configurado && (
                <div style={{ ...estiloCard, borderColor: CORES_CONTADOR.cobre, marginBottom: "1rem" }}>
                  <p style={{ fontSize: "0.82rem", margin: 0, color: CORES_CONTADOR.cobreClaro }}>
                    Nenhuma conta gerencial está marcada como receita do leite ou custo de alimentação — a versão gerencial fica zerada até a fazenda configurar isso.
                  </p>
                </div>
              )}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }} className="contador-grid-2">
                <div style={estiloCard}>
                  <p style={{ margin: "0 0 0.8rem", fontWeight: 700, fontSize: "0.85rem" }}>RMCA gerencial</p>
                  <div style={{ display: "grid", gap: "0.6rem" }}>
                    <Kpi titulo="Receita do leite" valor={formatBRL(rmca.gerencial.receita_leite)} cor={CORES_CONTADOR.positivo} />
                    <Kpi titulo="Custo de alimentação" valor={formatBRL(rmca.gerencial.custo_alimentacao)} cor={CORES_CONTADOR.negativo} />
                    <Kpi titulo="RMCA" valor={formatBRL(rmca.gerencial.rmca)} cor={rmca.gerencial.rmca >= 0 ? CORES_CONTADOR.positivo : CORES_CONTADOR.cobreClaro} />
                  </div>
                </div>
                <div style={estiloCard}>
                  <p style={{ margin: "0 0 0.8rem", fontWeight: 700, fontSize: "0.85rem" }}>RMCA físico</p>
                  <div style={{ display: "grid", gap: "0.6rem" }}>
                    <Kpi titulo="Receita do leite" valor={formatBRL(rmca.fisico.receita_leite)} cor={CORES_CONTADOR.positivo} />
                    <Kpi titulo="Custo de alimentação" valor={formatBRL(rmca.fisico.custo_alimentacao)} cor={CORES_CONTADOR.negativo} />
                    <Kpi titulo="RMCA" valor={formatBRL(rmca.fisico.rmca)} cor={rmca.fisico.rmca >= 0 ? CORES_CONTADOR.positivo : CORES_CONTADOR.cobreClaro} />
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {aba === "plano" && (
        <div style={estiloCard}>
          <table className="contador-th" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr>
              <ThOrdenavel label="Código" campo="codigo" coluna={ordPlano.coluna} dir={ordPlano.dir} ordenar={ordPlano.ordenar} />
              <ThOrdenavel label="Nome" campo="nome" coluna={ordPlano.coluna} dir={ordPlano.dir} ordenar={ordPlano.ordenar} />
              <ThOrdenavel label="Natureza" campo="natureza" coluna={ordPlano.coluna} dir={ordPlano.dir} ordenar={ordPlano.ordenar} />
              <ThOrdenavel label="Fixo/Variável" campo="tipo_fixo_variavel" coluna={ordPlano.coluna} dir={ordPlano.dir} ordenar={ordPlano.ordenar} />
              <ThOrdenavel label="Ativa" campo="ativa" coluna={ordPlano.coluna} dir={ordPlano.dir} ordenar={ordPlano.ordenar} />
            </tr></thead>
            <tbody>
              {ordPlano.linhasOrdenadas.map((c) => (
                <tr key={c.codigo}>
                  <td style={estiloTd}>{c.codigo}</td><td style={estiloTd}>{c.nome}</td>
                  <td style={estiloTd}>{c.natureza || "—"}</td><td style={estiloTd}>{c.tipo_fixo_variavel || "—"}</td>
                  <td style={estiloTd}>{c.ativa === false ? "Inativa" : "Ativa"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {aba === "extrato" && (
        <div style={estiloCard}>
          <div style={{ marginBottom: "0.9rem" }}>
            <select style={estiloInput} value={tipoExtrato} onChange={(e) => setTipoExtrato(e.target.value as any)}>
              <option value="ambos">Todos</option>
              <option value="receita">Receitas</option>
              <option value="despesa">Despesas</option>
            </select>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="contador-th" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Data" campo="data_competencia" coluna={ordExtrato.coluna} dir={ordExtrato.dir} ordenar={ordExtrato.ordenar} />
                  <ThOrdenavel label="Fornecedor/Cliente" campo="fornecedor" coluna={ordExtrato.coluna} dir={ordExtrato.dir} ordenar={ordExtrato.ordenar} />
                  <ThOrdenavel label="Descrição" campo="descricao" coluna={ordExtrato.coluna} dir={ordExtrato.dir} ordenar={ordExtrato.ordenar} />
                  <ThOrdenavel label="Conta" campo="codigo_conta" coluna={ordExtrato.coluna} dir={ordExtrato.dir} ordenar={ordExtrato.ordenar} />
                  <ThOrdenavel label="Centro de custo" campo="centro_custo" coluna={ordExtrato.coluna} dir={ordExtrato.dir} ordenar={ordExtrato.ordenar} />
                  <ThOrdenavel label="Valor" campo="valor" coluna={ordExtrato.coluna} dir={ordExtrato.dir} ordenar={ordExtrato.ordenar} alinhar="right" />
                  <ThOrdenavel label="Pagamento" campo="data_pagamento" coluna={ordExtrato.coluna} dir={ordExtrato.dir} ordenar={ordExtrato.ordenar} />
                  <th style={estiloTh}></th>
                </tr>
              </thead>
              <tbody>
                {ordExtrato.linhasOrdenadas.map((l) => (
                  <tr key={l.id}>
                    <td style={estiloTd}>{formatDate(l.data_competencia || "")}</td>
                    <td style={estiloTd}>{l.fornecedor}</td>
                    <td style={estiloTd}>{l.descricao}</td>
                    <td style={estiloTd}>{nomePorCodigo.get(l.codigo_conta) || l.codigo_conta}</td>
                    <td style={estiloTd}>{l.centro_custo}</td>
                    <td style={{ ...estiloTd, textAlign: "right", color: l.tipo === "receita" ? CORES_CONTADOR.positivo : CORES_CONTADOR.negativo }}>{formatBRL(l.valor)}</td>
                    <td style={estiloTd}>{l.data_pagamento ? formatDate(l.data_pagamento) : "Em aberto"}</td>
                    <td style={estiloTd}><AnexosLinha numeroLancamento={l.numero_lancamento} /></td>
                  </tr>
                ))}
                {extratoFiltrado.length === 0 && <tr><td style={estiloTd} colSpan={8}>Sem lançamentos no período.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {aba === "patrimonio" && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(9rem, 1fr))", gap: "0.8rem", marginBottom: "1.2rem" }}>
            <Kpi titulo="Valor de aquisição" valor={formatBRL(patrimonio?.valor_total || 0)} />
            <Kpi titulo="Valor atual (após depreciação)" valor={formatBRL(patrimonio?.valor_atual_total || 0)} cor={CORES_CONTADOR.cobreClaro} />
          </div>
          <div style={{ ...estiloCard, overflowX: "auto" }}>
            <table className="contador-th" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Nome" campo="nome" coluna={ordPatrimonio.coluna} dir={ordPatrimonio.dir} ordenar={ordPatrimonio.ordenar} />
                  <ThOrdenavel label="Tipo" campo="tipo" coluna={ordPatrimonio.coluna} dir={ordPatrimonio.dir} ordenar={ordPatrimonio.ordenar} />
                  <ThOrdenavel label="Imobilização" campo="data_imobilizacao" coluna={ordPatrimonio.coluna} dir={ordPatrimonio.dir} ordenar={ordPatrimonio.ordenar} />
                  <ThOrdenavel label="Valor total" campo="valor_total" coluna={ordPatrimonio.coluna} dir={ordPatrimonio.dir} ordenar={ordPatrimonio.ordenar} alinhar="right" />
                  <ThOrdenavel label="Depreciação acum." campo="depreciacao_acumulada" coluna={ordPatrimonio.coluna} dir={ordPatrimonio.dir} ordenar={ordPatrimonio.ordenar} alinhar="right" />
                  <ThOrdenavel label="Valor atual" campo="valor_atual" coluna={ordPatrimonio.coluna} dir={ordPatrimonio.dir} ordenar={ordPatrimonio.ordenar} alinhar="right" />
                </tr>
              </thead>
              <tbody>
                {ordPatrimonio.linhasOrdenadas.map((i) => (
                  <tr key={i.id}>
                    <td style={estiloTd}>{i.nome}</td><td style={estiloTd}>{i.tipo || "—"}</td>
                    <td style={estiloTd}>{i.data_imobilizacao ? formatDate(i.data_imobilizacao) : "—"}</td>
                    <td style={{ ...estiloTd, textAlign: "right" }}>{i.valor_total != null ? formatBRL(i.valor_total) : "—"}</td>
                    <td style={{ ...estiloTd, textAlign: "right" }}>{i.depreciacao_acumulada != null ? formatBRL(i.depreciacao_acumulada) : "—"}</td>
                    <td style={{ ...estiloTd, textAlign: "right", color: CORES_CONTADOR.cobreClaro }}>{i.valor_atual != null ? formatBRL(i.valor_atual) : "—"}</td>
                  </tr>
                ))}
                {(patrimonio?.itens || []).length === 0 && <tr><td style={estiloTd} colSpan={6}>Sem itens de patrimônio cadastrados.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {aba === "folha" && (
        <div style={{ ...estiloCard, overflowX: "auto" }}>
          <table className="contador-th" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <ThOrdenavel label="Pessoa" campo="pessoa_nome" coluna={ordFolha.coluna} dir={ordFolha.dir} ordenar={ordFolha.ordenar} />
                <ThOrdenavel label="Descrição" campo="descricao" coluna={ordFolha.coluna} dir={ordFolha.dir} ordenar={ordFolha.ordenar} />
                <ThOrdenavel label="Valor" campo="valor" coluna={ordFolha.coluna} dir={ordFolha.dir} ordenar={ordFolha.ordenar} alinhar="right" />
                <ThOrdenavel label="Vencimento" campo="data_vencimento" coluna={ordFolha.coluna} dir={ordFolha.dir} ordenar={ordFolha.ordenar} />
                <ThOrdenavel label="Pagamento" campo="data_pagamento" coluna={ordFolha.coluna} dir={ordFolha.dir} ordenar={ordFolha.ordenar} />
                <ThOrdenavel label="Status" campo="status" coluna={ordFolha.coluna} dir={ordFolha.dir} ordenar={ordFolha.ordenar} />
              </tr>
            </thead>
            <tbody>
              {ordFolha.linhasOrdenadas.map((f) => (
                <tr key={`${f.tipo}-${f.origem_id}`}>
                  <td style={estiloTd}>{f.pessoa_nome}</td><td style={estiloTd}>{f.descricao}</td>
                  <td style={{ ...estiloTd, textAlign: "right" }}>{formatBRL(f.valor)}</td>
                  <td style={estiloTd}>{f.data_vencimento ? formatDate(f.data_vencimento) : "—"}</td>
                  <td style={estiloTd}>{f.data_pagamento ? formatDate(f.data_pagamento) : "—"}</td>
                  <td style={{ ...estiloTd, color: f.status === "pago" ? CORES_CONTADOR.positivo : CORES_CONTADOR.cobreClaro }}>{f.status === "pago" ? "Pago" : "Pendente"}</td>
                </tr>
              ))}
              {folhaNoPeriodo.length === 0 && <tr><td style={estiloTd} colSpan={6}>Sem lançamentos de folha no período.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {aba === "animais" && (
        <div style={{ ...estiloCard, overflowX: "auto" }}>
          <table className="contador-th" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <ThOrdenavel label="Data" campo="data" coluna={ordAnimais.coluna} dir={ordAnimais.dir} ordenar={ordAnimais.ordenar} />
                <ThOrdenavel label="Tipo" campo="tipo" coluna={ordAnimais.coluna} dir={ordAnimais.dir} ordenar={ordAnimais.ordenar} />
                <ThOrdenavel label="Animal" campo="numero_animal" coluna={ordAnimais.coluna} dir={ordAnimais.dir} ordenar={ordAnimais.ordenar} />
                <ThOrdenavel label="Contraparte" campo="contraparte" coluna={ordAnimais.coluna} dir={ordAnimais.dir} ordenar={ordAnimais.ordenar} />
                <ThOrdenavel label="Valor" campo="valor" coluna={ordAnimais.coluna} dir={ordAnimais.dir} ordenar={ordAnimais.ordenar} alinhar="right" />
                <ThOrdenavel label="GTA" campo="gta" coluna={ordAnimais.coluna} dir={ordAnimais.dir} ordenar={ordAnimais.ordenar} />
                <ThOrdenavel label="Documento" campo="numero_documento" coluna={ordAnimais.coluna} dir={ordAnimais.dir} ordenar={ordAnimais.ordenar} />
              </tr>
            </thead>
            <tbody>
              {ordAnimais.linhasOrdenadas.map((a, i) => (
                <tr key={i}>
                  <td style={estiloTd}>{formatDate(a.data)}</td>
                  <td style={{ ...estiloTd, color: a.tipo === "compra" ? CORES_CONTADOR.negativo : CORES_CONTADOR.positivo }}>{a.tipo === "compra" ? "Compra" : "Venda"}</td>
                  <td style={estiloTd}>{a.numero_animal}</td><td style={estiloTd}>{a.contraparte}</td>
                  <td style={{ ...estiloTd, textAlign: "right" }}>{formatBRL(a.valor)}</td>
                  <td style={estiloTd}>{a.gta || "—"}</td><td style={estiloTd}>{a.numero_documento || "—"}</td>
                </tr>
              ))}
              {animaisNoPeriodo.length === 0 && <tr><td style={estiloTd} colSpan={7}>Sem compra/venda de animais no período.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {aba === "documentos" && <PainelDocumentos />}

      {aba === "extraordinario" && <PainelExtraordinario planoContas={planoContas} />}
    </div>
  );
}
