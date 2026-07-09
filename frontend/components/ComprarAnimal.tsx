"use client";
import { useEffect, useMemo, useState } from "react";
import { ShoppingCart, Check } from "lucide-react";
import { criarCompraAnimal, fetchComprasAnimais, fetchFornecedores } from "@/lib/api";
import { RESPONSAVEIS } from "@/lib/constants";
import ComissaoCorretagemForm from "./ComissaoCorretagemForm";

type Fornecedor = { id: number; nome: string; tipo: string; ativo: boolean };
type Compra = {
  id: number; numero_animal: string; vendedor: string; valor: number; tipo_valor: string;
  data_compra: string; numero_lancamento_gerado: string | null;
};

const selStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const hoje = () => new Date().toISOString().split("T")[0];

function parseAnimais(texto: string): string[] {
  return Array.from(new Set(texto.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean)));
}

export default function ComprarAnimal() {
  const [animaisTexto, setAnimaisTexto] = useState("");
  const [vendedor, setVendedor] = useState("");
  const [valor, setValor] = useState("");
  const [tipoValor, setTipoValor] = useState("por_animal");
  const [dataCompra, setDataCompra] = useState(hoje());
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [pagarComissao, setPagarComissao] = useState(false);
  const [corretorNome, setCorretorNome] = useState("");
  const [valorComissao, setValorComissao] = useState("");
  const [formaComissao, setFormaComissao] = useState("redirecionado");
  const corretores = useMemo(() => fornecedores.filter((f) => f.tipo === "corretor" && f.ativo).map((f) => f.nome), [fornecedores]);

  const [historico, setHistorico] = useState<Compra[] | null>(null);

  const carregar = () => {
    fetchFornecedores().then(setFornecedores).catch(() => {});
    fetchComprasAnimais().then(setHistorico).catch(() => {});
  };
  useEffect(carregar, []);

  const animais = useMemo(() => parseAnimais(animaisTexto), [animaisTexto]);

  const limpar = () => {
    setAnimaisTexto(""); setVendedor(""); setValor(""); setTipoValor("por_animal");
    setObservacao(""); setPagarComissao(false); setCorretorNome(""); setValorComissao(""); setFormaComissao("redirecionado");
  };

  const salvar = async () => {
    setMsg(null);
    if (!animais.length) { setMsg({ tipo: "erro", texto: "Informe ao menos um número de animal." }); return; }
    if (!vendedor.trim()) { setMsg({ tipo: "erro", texto: "Informe o vendedor." }); return; }
    if (!valor) { setMsg({ tipo: "erro", texto: "Informe o valor da compra." }); return; }
    if (pagarComissao && (!corretorNome.trim() || !valorComissao)) {
      setMsg({ tipo: "erro", texto: "Informe o corretor e o valor da comissão." }); return;
    }

    setSalvando(true);
    try {
      const r = await criarCompraAnimal({
        animais, vendedor: vendedor.trim(), valor: Number(valor), tipo_valor: tipoValor,
        data_compra: dataCompra, observacao: observacao || undefined, responsavel: responsavel || undefined,
        pagar_comissao: pagarComissao,
        corretor_nome: pagarComissao ? corretorNome.trim() : undefined,
        valor_comissao: pagarComissao ? Number(valorComissao) : undefined,
        forma_comissao: pagarComissao ? formaComissao : undefined,
      });
      setMsg({ tipo: "sucesso", texto: `${r.comprados} animal(is) registrado(s) como comprado(s).` });
      limpar();
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao registrar compra" });
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><ShoppingCart size={22} style={{ color: "var(--dourado)" }} /> Comprar animal</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Registra a aquisição de animal(is) e gera a despesa correspondente no Financeiro. Não altera o cadastro/ficha do animal — isso segue o fluxo normal de importação/cadastro.
        </p>
      </div>

      <div className="card mb-4">
        <div className="mb-3">
          <label style={labelStyle}>Número(s) do(s) animal(is) — separe por vírgula, espaço ou linha</label>
          <textarea style={{ ...selStyle, minHeight: "60px", resize: "vertical" }} value={animaisTexto} onChange={(e) => setAnimaisTexto(e.target.value)} placeholder="ex.: 950, 951, 952" />
          {!!animais.length && <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>{animais.length} animal(is) reconhecido(s).</p>}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <div><label style={labelStyle}>Vendedor</label>
            <input style={selStyle} value={vendedor} onChange={(e) => setVendedor(e.target.value)} placeholder="ex.: Fazenda Y" /></div>
          <div><label style={labelStyle}>Data da compra</label>
            <input type="date" style={selStyle} value={dataCompra} onChange={(e) => setDataCompra(e.target.value)} /></div>
        </div>

        <div className="mb-3" style={{ maxWidth: "480px" }}>
          <label style={labelStyle}>O valor informado é...</label>
          <div className="flex gap-4 mt-1" style={{ fontSize: "0.82rem" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
              <input type="radio" name="tipo_valor_compra" checked={tipoValor === "por_animal"} onChange={() => setTipoValor("por_animal")} />
              Por animal comprado
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
              <input type="radio" name="tipo_valor_compra" checked={tipoValor === "total"} onChange={() => setTipoValor("total")} />
              Total da compra ({animais.length || 0} animal(is))
            </label>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 mb-3" style={{ maxWidth: "480px" }}>
          <div><label style={labelStyle}>{tipoValor === "total" ? "Valor total (R$)" : "Valor por animal (R$)"}</label>
            <input type="number" step="0.01" style={selStyle} value={valor} onChange={(e) => setValor(e.target.value)} /></div>
        </div>
        {tipoValor === "total" && !!valor && !!animais.length && (
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "-0.5rem" }}>
            Equivale a R$ {(Number(valor) / animais.length).toFixed(2)} por animal.
          </p>
        )}

        <ComissaoCorretagemForm
          pagarComissao={pagarComissao} setPagarComissao={setPagarComissao}
          corretorNome={corretorNome} setCorretorNome={setCorretorNome}
          valorComissao={valorComissao} setValorComissao={setValorComissao}
          formaComissao={formaComissao} setFormaComissao={setFormaComissao}
          corretores={corretores}
        />

        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <div><label style={labelStyle}>Responsável</label>
            <select style={selStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
              <option value="">Selecione...</option>
              {RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}
            </select></div>
          <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Observação (opcional)</label>
            <input style={selStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
        </div>

        {msg && (
          <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>
        )}
        <button className="btn-primary" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : `Registrar compra de ${animais.length || ""} animal(is)`}
        </button>
      </div>

      {historico && historico.length > 0 && (
        <div className="card">
          <div className="card-header mb-3">Compras registradas</div>
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr><th>Nº</th><th>Vendedor</th><th>Data</th><th style={{ textAlign: "right" }}>Valor (por animal)</th><th>Lançamento</th></tr></thead>
              <tbody>
                {historico.map((c) => (
                  <tr key={c.id}>
                    <td style={{ fontWeight: 700 }}>{c.numero_animal}</td>
                    <td style={{ fontSize: "0.8rem" }}>{c.vendedor}</td>
                    <td style={{ fontSize: "0.8rem" }}>{c.data_compra}</td>
                    <td style={{ textAlign: "right" }}>R$ {c.valor.toFixed(2)}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{c.numero_lancamento_gerado || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
