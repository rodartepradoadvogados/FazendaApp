"use client";
// Ações extraordinárias do contador — pagamento de guia/imposto/multa,
// recálculo de juros e abertura de chamado, todas atrás do cadeado (ver
// frontend/lib/useCadeado.ts e backend/fazenda/auth.py::bloquear_escrita_contador).
import { useEffect, useState } from "react";
import { Send } from "lucide-react";
import {
  abrirChamado, calcularJuros, criarLancamentoExtraordinario, fetchChamados,
  type CalculoJuros, type Chamado,
} from "@/lib/api";
import { CampoMoeda } from "@/components/CampoMoeda";
import type { ContaPlano } from "@/lib/contaGerencial";
import { CORES_CONTADOR } from "@/app/contador/layout";
import { useCadeado } from "@/lib/useCadeado";
import { CadeadoWidget } from "./CadeadoWidget";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

const C = CORES_CONTADOR;
const estiloCard: React.CSSProperties = { background: C.painel, border: `1px solid ${C.borda}`, borderRadius: "4px", padding: "1.3rem" };
const estiloInput: React.CSSProperties = {
  background: C.painelAlt, color: C.texto, border: `1px solid ${C.borda}`, borderRadius: "3px",
  padding: "0.4rem 0.6rem", fontSize: "0.85rem", width: "100%",
};
const estiloLabel: React.CSSProperties = { fontSize: "0.68rem", color: C.mudo, display: "block", marginBottom: "0.2rem", textTransform: "uppercase", letterSpacing: "0.05em" };
const estiloBotao: React.CSSProperties = {
  background: C.cobre, color: "#fff", border: "none", borderRadius: "3px",
  padding: "0.5rem 0.9rem", fontSize: "0.8rem", fontWeight: 700, cursor: "pointer",
};
const estiloTh: React.CSSProperties = {
  textAlign: "left", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em",
  color: C.mudo, borderBottom: `1px solid ${C.bordaClara}`, padding: "0.5rem 0.6rem", fontWeight: 700,
};
const estiloTd: React.CSSProperties = { fontSize: "0.82rem", padding: "0.5rem 0.6rem", borderBottom: `1px solid ${C.borda}` };

function hoje() { return new Date().toISOString().slice(0, 10); }

function LancamentoExtraordinario({ token, planoContas }: { token: string; planoContas: ContaPlano[] }) {
  const [descricao, setDescricao] = useState("");
  const [fornecedor, setFornecedor] = useState("");
  const [contaGerencial, setContaGerencial] = useState("");
  const [valor, setValor] = useState("");
  const [vencimento, setVencimento] = useState(hoje());
  const [enviando, setEnviando] = useState(false);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const registrar = async (e: React.FormEvent) => {
    e.preventDefault();
    const conta = planoContas.find((c) => c.codigo === contaGerencial);
    setEnviando(true); setErro(null); setMensagem(null);
    try {
      await criarLancamentoExtraordinario({
        tipo: "despesa",
        itens: [{
          produto: descricao, tipo_item: "servico", valor_total: Number(valor),
          codigo_conta_gerencial: conta?.codigo, nome_conta_gerencial: conta?.nome,
        }],
        fornecedor_cliente: fornecedor || undefined,
        data_vencimento: vencimento,
        data_emissao: hoje(),
      }, token);
      setMensagem(`Lançamento registrado — ${descricao}`);
      setDescricao(""); setFornecedor(""); setContaGerencial(""); setValor(""); setVencimento(hoje());
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div style={estiloCard}>
      <p style={{ margin: "0 0 0.4rem", fontWeight: 700, fontSize: "0.85rem" }}>Lançamento extraordinário</p>
      <p style={{ margin: "0 0 0.9rem", fontSize: "0.78rem", color: C.mudo }}>Pagamento de guia, imposto ou multa avulsa.</p>
      <form onSubmit={registrar} style={{ display: "grid", gap: "0.8rem", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))" }}>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={estiloLabel}>Descrição</label>
          <input style={estiloInput} value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder="Ex.: DARF — IRPJ 3º trimestre" required />
        </div>
        <div>
          <label style={estiloLabel}>Órgão/fornecedor</label>
          <input style={estiloInput} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)} placeholder="Ex.: Receita Federal" />
        </div>
        <div>
          <label style={estiloLabel}>Conta gerencial</label>
          <select style={estiloInput} value={contaGerencial} onChange={(e) => setContaGerencial(e.target.value)}>
            <option value="">Selecione…</option>
            {planoContas.filter((c) => c.ativa !== false).map((c) => <option key={c.codigo} value={c.codigo}>{c.nome}</option>)}
          </select>
        </div>
        <div>
          <label style={estiloLabel}>Valor (R$)</label>
          <CampoMoeda style={estiloInput} value={Number(valor) || 0} onChange={(v) => setValor(v ? String(v) : "")} />
        </div>
        <div>
          <label style={estiloLabel}>Vencimento</label>
          <input type="date" style={estiloInput} value={vencimento} onChange={(e) => setVencimento(e.target.value)} required />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <button type="submit" disabled={enviando || !descricao || !valor} style={{ ...estiloBotao, opacity: enviando || !descricao || !valor ? 0.6 : 1 }}>
            {enviando ? "Registrando…" : "Registrar lançamento"}
          </button>
        </div>
      </form>
      {mensagem && <p style={{ color: C.positivo, fontSize: "0.8rem", marginTop: "0.6rem" }}>{mensagem}</p>}
      {erro && <p style={{ color: C.negativo, fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
    </div>
  );
}

function RecalculoJuros({ token }: { token: string }) {
  const [valorOriginal, setValorOriginal] = useState("");
  const [vencimento, setVencimento] = useState("");
  const [referencia, setReferencia] = useState(hoje());
  const [percMulta, setPercMulta] = useState("2");
  const [percJuros, setPercJuros] = useState("1");
  const [resultado, setResultado] = useState<CalculoJuros | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const calcular = async (e: React.FormEvent) => {
    e.preventDefault();
    setCalculando(true); setErro(null); setResultado(null);
    try {
      const r = await calcularJuros({
        valor_original: Number(valorOriginal), data_vencimento: vencimento, data_referencia: referencia,
        percentual_multa: Number(percMulta), percentual_juros_mes: Number(percJuros),
      }, token);
      setResultado(r);
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setCalculando(false);
    }
  };

  return (
    <div style={estiloCard}>
      <p style={{ margin: "0 0 0.4rem", fontWeight: 700, fontSize: "0.85rem" }}>Recálculo de juros e multa</p>
      <p style={{ margin: "0 0 0.9rem", fontSize: "0.78rem", color: C.mudo }}>
        Calculadora — o resultado não é salvo sozinho; use o valor atualizado num lançamento extraordinário acima.
      </p>
      <form onSubmit={calcular} style={{ display: "grid", gap: "0.8rem", gridTemplateColumns: "repeat(auto-fit, minmax(9rem, 1fr))" }}>
        <div>
          <label style={estiloLabel}>Valor original (R$)</label>
          <CampoMoeda style={estiloInput} value={Number(valorOriginal) || 0} onChange={(v) => setValorOriginal(v ? String(v) : "")} />
        </div>
        <div>
          <label style={estiloLabel}>Vencimento original</label>
          <input type="date" style={estiloInput} value={vencimento} onChange={(e) => setVencimento(e.target.value)} required />
        </div>
        <div>
          <label style={estiloLabel}>Data de referência</label>
          <input type="date" style={estiloInput} value={referencia} onChange={(e) => setReferencia(e.target.value)} required />
        </div>
        <div>
          <label style={estiloLabel}>Multa (%)</label>
          <input type="number" step="0.1" style={estiloInput} value={percMulta} onChange={(e) => setPercMulta(e.target.value)} />
        </div>
        <div>
          <label style={estiloLabel}>Juros ao mês (%)</label>
          <input type="number" step="0.1" style={estiloInput} value={percJuros} onChange={(e) => setPercJuros(e.target.value)} />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <button type="submit" disabled={calculando || !valorOriginal || !vencimento} style={{ ...estiloBotao, opacity: calculando || !valorOriginal || !vencimento ? 0.6 : 1 }}>
            {calculando ? "Calculando…" : "Calcular"}
          </button>
        </div>
      </form>
      {resultado && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(7rem, 1fr))", gap: "0.6rem", marginTop: "1rem" }}>
          <div><p style={estiloLabel}>Dias em atraso</p><p style={{ margin: 0, fontWeight: 700 }}>{resultado.dias_atraso}</p></div>
          <div><p style={estiloLabel}>Multa</p><p style={{ margin: 0, fontWeight: 700 }}>R$ {resultado.valor_multa.toFixed(2)}</p></div>
          <div><p style={estiloLabel}>Juros</p><p style={{ margin: 0, fontWeight: 700 }}>R$ {resultado.valor_juros.toFixed(2)}</p></div>
          <div><p style={estiloLabel}>Valor atualizado</p><p style={{ margin: 0, fontWeight: 700, color: C.cobreClaro }}>R$ {resultado.valor_atualizado.toFixed(2)}</p></div>
        </div>
      )}
      {erro && <p style={{ color: C.negativo, fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
    </div>
  );
}

function AbrirChamado({ token }: { token: string }) {
  const [assunto, setAssunto] = useState("");
  const [descricao, setDescricao] = useState("");
  const [chamados, setChamados] = useState<Chamado[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const recarregar = () => fetchChamados().then(setChamados).catch(() => setChamados([]));
  useEffect(() => { recarregar(); }, []);

  const ord = useOrdenacao(chamados);

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnviando(true); setErro(null);
    try {
      await abrirChamado({ assunto, descricao }, token);
      setAssunto(""); setDescricao("");
      recarregar();
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div style={estiloCard}>
      <p style={{ margin: "0 0 0.9rem", fontWeight: 700, fontSize: "0.85rem" }}>Abrir chamado</p>
      <form onSubmit={enviar} style={{ display: "grid", gap: "0.8rem" }}>
        <div>
          <label style={estiloLabel}>Assunto</label>
          <input style={estiloInput} value={assunto} onChange={(e) => setAssunto(e.target.value)} required />
        </div>
        <div>
          <label style={estiloLabel}>Descrição</label>
          <textarea style={{ ...estiloInput, minHeight: "4rem", resize: "vertical" }} value={descricao} onChange={(e) => setDescricao(e.target.value)} required />
        </div>
        <div>
          <button type="submit" disabled={enviando || !assunto || !descricao} style={{ ...estiloBotao, display: "inline-flex", alignItems: "center", gap: "0.4rem", opacity: enviando || !assunto || !descricao ? 0.6 : 1 }}>
            <Send size={13} /> {enviando ? "Enviando…" : "Enviar chamado"}
          </button>
        </div>
      </form>
      {erro && <p style={{ color: C.negativo, fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}

      {chamados.length > 0 && (
        <table className="contador-th" style={{ width: "100%", borderCollapse: "collapse", marginTop: "1.2rem" }}>
          <thead><tr>
            <ThOrdenavel label="Assunto" campo="assunto" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
            <ThOrdenavel label="Status" campo="status" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
            <ThOrdenavel label="Aberto em" campo="criado_em" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          </tr></thead>
          <tbody>
            {ord.linhasOrdenadas.map((ch) => (
              <tr key={ch.id}>
                <td style={estiloTd}>{ch.assunto}</td>
                <td style={{ ...estiloTd, color: ch.status === "resolvido" ? C.positivo : C.cobreClaro }}>
                  {ch.status === "aberto" ? "Aberto" : ch.status === "em_andamento" ? "Em andamento" : "Resolvido"}
                </td>
                <td style={estiloTd}>{new Date(ch.criado_em).toLocaleDateString("pt-BR")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function PainelExtraordinario({ planoContas }: { planoContas: ContaPlano[] }) {
  const cadeado = useCadeado();
  return (
    <div>
      <CadeadoWidget cadeado={cadeado} />
      {cadeado.token && (
        <div style={{ display: "grid", gap: "1.2rem" }}>
          <LancamentoExtraordinario token={cadeado.token} planoContas={planoContas} />
          <RecalculoJuros token={cadeado.token} />
          <AbrirChamado token={cadeado.token} />
        </div>
      )}
    </div>
  );
}
