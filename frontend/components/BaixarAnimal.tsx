"use client";
import { useEffect, useMemo, useState } from "react";
import { Skull, AlertTriangle, Check, Search } from "lucide-react";
import { fetchAnimais, fetchOpcoesBaixa, criarBaixaAnimal, fetchFornecedores, marcarADescartar } from "@/lib/api";
import { RESPONSAVEIS } from "@/lib/constants";
import ComissaoCorretagemForm from "./ComissaoCorretagemForm";

type Animal = { numero: string; grupo_primario: string | null; categoria_abrev: string | null; ativo?: boolean };
type Fornecedor = { id: number; nome: string; tipo: string; ativo: boolean };

const LABEL_TIPO_BAIXA: Record<string, string> = {
  morte: "Morte", descarte_voluntario: "Descarte voluntário", descarte_involuntario: "Descarte involuntário",
};
const LABEL_MOTIVO: Record<string, string> = { venda: "Venda", abate: "Abate", acidente: "Acidente", doenca: "Doença" };

const selStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const hoje = () => new Date().toISOString().split("T")[0];

export default function BaixarAnimal() {
  const [animais, setAnimais] = useState<Animal[] | null>(null);
  const [opcoes, setOpcoes] = useState<{ tipos_baixa: string[]; motivos: string[]; motivos_doenca: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [busca, setBusca] = useState("");
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  // "definitiva" = saída do rebanho (morte/descarte/venda); "a_descartar" =
  // vaca segue ativa, mas sai das ações reprodutivas.
  const [modo, setModo] = useState<"definitiva" | "a_descartar">("definitiva");

  const [tipoBaixa, setTipoBaixa] = useState("");
  const [motivo, setMotivo] = useState("");
  const [motivoDoenca, setMotivoDoenca] = useState("");
  const [valor, setValor] = useState("");
  const [tipoValor, setTipoValor] = useState("por_animal");
  const [cliente, setCliente] = useState("");
  const [vendaRecria, setVendaRecria] = useState(false);
  const [dataBaixa, setDataBaixa] = useState(hoje());
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

  const carregar = () => {
    fetchAnimais().then((a: Animal[]) => setAnimais(a.filter((x) => x.ativo !== false))).catch((e) => setError(e.message));
    fetchOpcoesBaixa().then(setOpcoes).catch((e) => setError(e.message));
    fetchFornecedores().then(setFornecedores).catch(() => {});
  };
  useEffect(carregar, []);

  const candidatos = useMemo(() => {
    if (!animais) return [];
    return animais.filter((a) => !busca || a.numero.toLowerCase().includes(busca.toLowerCase()));
  }, [animais, busca]);

  const toggleAnimal = (numero: string) => setSelecionados((p) => {
    const n = new Set(p); n.has(numero) ? n.delete(numero) : n.add(numero); return n;
  });
  const toggleTodos = () => setSelecionados((p) =>
    p.size === candidatos.length && candidatos.length ? new Set() : new Set(candidatos.map((a) => a.numero))
  );

  const limpar = () => {
    setSelecionados(new Set()); setBusca(""); setTipoBaixa(""); setMotivo(""); setMotivoDoenca("");
    setValor(""); setTipoValor("por_animal"); setCliente(""); setVendaRecria(false); setObservacao("");
    setPagarComissao(false); setCorretorNome(""); setValorComissao(""); setFormaComissao("redirecionado");
  };

  const salvar = async () => {
    setMsg(null);
    if (!selecionados.size) { setMsg({ tipo: "erro", texto: "Selecione ao menos um animal." }); return; }
    if (modo === "a_descartar") {
      setSalvando(true);
      try {
        const r = await marcarADescartar({ animais: Array.from(selecionados), descartar: true, observacao: observacao || undefined });
        setMsg({ tipo: "sucesso", texto: `${r.afetados} animal(is) marcado(s) como "A descartar" — seguem ativos, fora das ações reprodutivas.` });
        limpar();
        carregar();
      } catch (e: any) {
        setMsg({ tipo: "erro", texto: e.message || "Erro ao marcar A descartar" });
      } finally { setSalvando(false); }
      return;
    }
    if (!tipoBaixa) { setMsg({ tipo: "erro", texto: "Selecione o tipo de baixa." }); return; }
    if (!motivo) { setMsg({ tipo: "erro", texto: "Selecione o motivo." }); return; }
    if (motivo === "doenca" && !motivoDoenca) { setMsg({ tipo: "erro", texto: "Selecione a doença/causa." }); return; }
    if (motivo === "venda" && (!valor || !cliente.trim())) { setMsg({ tipo: "erro", texto: "Venda exige valor e cliente." }); return; }
    if (motivo === "venda" && pagarComissao && (!corretorNome.trim() || !valorComissao)) {
      setMsg({ tipo: "erro", texto: "Informe o corretor e o valor da comissão." }); return;
    }

    setSalvando(true);
    try {
      const r = await criarBaixaAnimal({
        animais: Array.from(selecionados), tipo_baixa: tipoBaixa, motivo,
        motivo_doenca: motivo === "doenca" ? motivoDoenca : undefined,
        valor: motivo === "venda" ? Number(valor) : undefined,
        tipo_valor: motivo === "venda" ? tipoValor : undefined,
        cliente: motivo === "venda" ? cliente.trim() : undefined,
        venda_recria: motivo === "venda" ? vendaRecria : undefined,
        data_baixa: dataBaixa, observacao: observacao || undefined, responsavel: responsavel || undefined,
        pagar_comissao: motivo === "venda" ? pagarComissao : undefined,
        corretor_nome: motivo === "venda" && pagarComissao ? corretorNome.trim() : undefined,
        valor_comissao: motivo === "venda" && pagarComissao ? Number(valorComissao) : undefined,
        forma_comissao: motivo === "venda" && pagarComissao ? formaComissao : undefined,
      });
      setMsg({ tipo: "sucesso", texto: `${r.baixados} animal(is) baixado(s) com sucesso.` });
      limpar();
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao registrar baixa" });
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Skull size={22} style={{ color: "var(--red)" }} /> Baixar animal</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Saída definitiva do rebanho — morte ou descarte. O(s) animal(is) selecionado(s) ficam inativos ao salvar.
        </p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {(!animais || !opcoes) && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {animais && opcoes && (
        <div className="card">
          <div className="mb-3">
            <label style={labelStyle}>O que fazer</label>
            <div className="flex gap-4 mt-1" style={{ fontSize: "0.82rem" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
                <input type="radio" name="modo_baixa" checked={modo === "definitiva"} onChange={() => setModo("definitiva")} />
                Baixa definitiva (morte/descarte/venda)
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
                <input type="radio" name="modo_baixa" checked={modo === "a_descartar"} onChange={() => setModo("a_descartar")} />
                Marcar "A descartar" (segue ativa, sem reprodução)
              </label>
            </div>
          </div>
          <div className="mb-3">
            <label style={labelStyle}>Buscar animal (nº)</label>
            <div style={{ position: "relative", maxWidth: "260px" }}>
              <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
              <input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex.: 068" />
            </div>
          </div>

          <div style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden", marginBottom: "1rem" }}>
            <div style={{ background: "var(--surface-2)", padding: "0.55rem 0.9rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontSize: "0.85rem" }}>Animais ({candidatos.length}) — {selecionados.size} selecionado(s)</span>
              <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={toggleTodos}>
                {selecionados.size === candidatos.length && candidatos.length ? "Limpar seleção" : "Selecionar todos"}
              </button>
            </div>
            <div className="overflow-x-auto" style={{ maxHeight: "320px" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr><th></th><th>Nº</th><th>Lote atual</th><th>Categoria</th></tr></thead>
                <tbody>
                  {candidatos.map((a) => (
                    <tr key={a.numero} style={{ cursor: "pointer" }} onClick={() => toggleAnimal(a.numero)}>
                      <td><input type="checkbox" checked={selecionados.has(a.numero)} onChange={() => toggleAnimal(a.numero)} onClick={(e) => e.stopPropagation()} /></td>
                      <td style={{ fontWeight: 700 }}>{a.numero}</td>
                      <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.grupo_primario || "—"}</td>
                      <td style={{ fontSize: "0.75rem" }}>{a.categoria_abrev || "—"}</td>
                    </tr>
                  ))}
                  {!candidatos.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum animal no filtro.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          {modo === "a_descartar" && (
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              A(s) vaca(s) marcada(s) continua(m) no rebanho (ordenha, sanidade, movimentação), mas some(m) das candidatas a IATF,
              inseminação e demais ações reprodutivas. Use quando decidir descartar mais adiante, sem dar baixa agora.
            </p>
          )}

          {modo === "definitiva" && (
          <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
            <div><label style={labelStyle}>Tipo de baixa</label>
              <select style={selStyle} value={tipoBaixa} onChange={(e) => setTipoBaixa(e.target.value)}>
                <option value="">Selecione...</option>
                {opcoes.tipos_baixa.map((t) => <option key={t} value={t}>{LABEL_TIPO_BAIXA[t] || t}</option>)}
              </select></div>
            <div><label style={labelStyle}>Motivo</label>
              <select style={selStyle} value={motivo} onChange={(e) => setMotivo(e.target.value)}>
                <option value="">Selecione...</option>
                {opcoes.motivos.map((m) => <option key={m} value={m}>{LABEL_MOTIVO[m] || m}</option>)}
              </select></div>
            <div><label style={labelStyle}>Data da baixa</label>
              <input type="date" style={selStyle} value={dataBaixa} onChange={(e) => setDataBaixa(e.target.value)} /></div>
          </div>

          {motivo === "doenca" && (
            <div className="mb-3" style={{ maxWidth: "320px" }}>
              <label style={labelStyle}>Doença/causa</label>
              <select style={selStyle} value={motivoDoenca} onChange={(e) => setMotivoDoenca(e.target.value)}>
                <option value="">Selecione...</option>
                {opcoes.motivos_doenca.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
          )}

          {motivo === "venda" && (
            <>
              <div className="mb-3" style={{ maxWidth: "480px" }}>
                <label style={labelStyle}>O valor informado é...</label>
                <div className="flex gap-4 mt-1" style={{ fontSize: "0.82rem" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
                    <input type="radio" name="tipo_valor" checked={tipoValor === "por_animal"} onChange={() => setTipoValor("por_animal")} />
                    Por animal vendido
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
                    <input type="radio" name="tipo_valor" checked={tipoValor === "total"} onChange={() => setTipoValor("total")} />
                    Total da venda ({selecionados.size || 0} animal(is))
                  </label>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 mb-3" style={{ maxWidth: "480px" }}>
                <div><label style={labelStyle}>{tipoValor === "total" ? "Valor total (R$)" : "Valor por animal (R$)"}</label>
                  <input type="number" step="0.01" style={selStyle} value={valor} onChange={(e) => setValor(e.target.value)} /></div>
                <div><label style={labelStyle}>Cliente</label>
                  <input style={selStyle} value={cliente} onChange={(e) => setCliente(e.target.value)} placeholder="ex.: Frigorífico X" /></div>
              </div>
              {tipoValor === "total" && !!valor && !!selecionados.size && (
                <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "-0.5rem" }}>
                  Equivale a R$ {(Number(valor) / selecionados.size).toFixed(2)} por animal.
                </p>
              )}
              <label className="flex items-center gap-2" style={{ fontSize: "0.8rem", marginTop: "0.2rem" }}
                title="Marque quando for venda de animal de recria (novilha/bezerra), para simular a receita contra o custo de recria.">
                <input type="checkbox" checked={vendaRecria} onChange={(e) => setVendaRecria(e.target.checked)} /> Venda de recria (simular receita × custo de recria)
              </label>

              <ComissaoCorretagemForm
                pagarComissao={pagarComissao} setPagarComissao={setPagarComissao}
                corretorNome={corretorNome} setCorretorNome={setCorretorNome}
                valorComissao={valorComissao} setValorComissao={setValorComissao}
                formaComissao={formaComissao} setFormaComissao={setFormaComissao}
                corretores={corretores}
              />
            </>
          )}
          </>
          )}

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
            <Check size={14} /> {salvando ? "Salvando…" : modo === "a_descartar" ? `Marcar ${selecionados.size || ""} como "A descartar"` : `Baixar ${selecionados.size || ""} animal(is)`}
          </button>
        </div>
      )}
    </div>
  );
}
