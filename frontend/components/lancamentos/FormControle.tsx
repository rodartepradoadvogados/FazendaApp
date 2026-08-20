"use client";
import React, { useMemo, useState } from "react";
import { Download, Trash2 } from "lucide-react";
import {
  baixarModeloControleLeiteiro, criarControlesLeiteiros,
  preVisualizarControleLeiteiroPlanilha, confirmarControleLeiteiroPlanilha, type LinhaControleLeiteiroPreview,
} from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { Campo, inputStyle, lbl, nota } from "@/components/lancamentos/comumForms";
import { SelectAnimal } from "@/components/lancamentos/_shared";

// Planilha (Excel/.xlsx ou CSV) de controle leiteiro (por animal ou por
// lote): baixa o modelo, o usuário preenche fora do app e reanexa aqui —
// mas em vez de salvar direto ao enviar, mostra as linhas lidas numa
// tabela editável para revisar/corrigir antes de confirmar de fato.
function RevisarPlanilhaControleLeiteiro() {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [lendo, setLendo] = useState(false);
  const [linhas, setLinhas] = useState<LinhaControleLeiteiroPreview[] | null>(null);
  const [errosLeitura, setErrosLeitura] = useState<string[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [resultado, setResultado] = useState<{ criados: number } | null>(null);

  async function lerPlanilha() {
    if (!arquivo) return;
    setLendo(true); setErro(null); setResultado(null);
    try {
      const r = await preVisualizarControleLeiteiroPlanilha(arquivo);
      setLinhas(r.linhas);
      setErrosLeitura(r.erros);
    } catch (e: any) {
      setErro(e.message || "Erro ao ler a planilha");
    } finally {
      setLendo(false);
    }
  }

  function atualizarLinha(idx: number, patch: Partial<LinhaControleLeiteiroPreview>) {
    setLinhas((prev) => (prev ? prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)) : prev));
  }
  function removerLinha(idx: number) {
    setLinhas((prev) => (prev ? prev.filter((_, i) => i !== idx) : prev));
  }

  async function confirmar() {
    if (!linhas || !linhas.length) return;
    setSalvando(true); setErro(null);
    try {
      const r = await confirmarControleLeiteiroPlanilha(linhas);
      setResultado(r);
      setLinhas(null); setArquivo(null); setErrosLeitura([]);
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  }

  const num = (v: string) => (v.trim() === "" ? null : Number(v));

  return (
    <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
      <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--dourado-light)", marginBottom: "0.5rem" }}>
        Importar de planilha (Excel ou CSV)
      </p>

      {!linhas && (
        <>
          <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => baixarModeloControleLeiteiro("animal").catch(() => setErro("Erro ao baixar o modelo."))}>
              <Download size={13} /> Modelo por animal
            </button>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => baixarModeloControleLeiteiro("lote").catch(() => setErro("Erro ao baixar o modelo."))}>
              <Download size={13} /> Modelo por lote
            </button>
          </div>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
            Baixe o modelo, preencha fora do app e anexe aqui — antes de salvar, você revisa e pode corrigir os valores lidos.
          </p>
          <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
            <input type="file" accept=".xlsx,.xlsm,.csv" onChange={(e) => { setArquivo(e.target.files?.[0] || null); setResultado(null); setErro(null); }} style={{ fontSize: "0.8rem" }} />
            <button type="button" className="btn-primary" disabled={!arquivo || lendo} onClick={lerPlanilha}>{lendo ? "Lendo…" : "Ler planilha"}</button>
          </div>
        </>
      )}

      {resultado && (
        <p style={{ fontSize: "0.78rem", marginTop: "0.6rem", color: "var(--green-light)" }}>
          {resultado.criados} lançamento(s) salvo(s) com sucesso.
        </p>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{erro}</p>}

      {linhas && (
        <div className="mt-2">
          {errosLeitura.length > 0 && (
            <p style={{ fontSize: "0.76rem", color: "var(--amber)", marginBottom: "0.5rem" }}>
              {errosLeitura.length} linha(s) da planilha não puderam ser lidas e foram ignoradas:
              <span style={{ display: "block", color: "var(--text-muted)" }}>{errosLeitura.slice(0, 5).join("; ")}</span>
            </p>
          )}
          <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
            Revise os valores lidos abaixo — edite o que precisar antes de confirmar. Nada foi salvo ainda.
          </p>
          <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead>
                <tr>
                  <th>Nº</th><th>Data</th>
                  <th style={{ textAlign: "right" }}>1ª ordenha (kg)</th>
                  <th style={{ textAlign: "right" }}>2ª ordenha (kg)</th>
                  <th style={{ textAlign: "right" }}>3ª ordenha (kg)</th>
                  <th style={{ textAlign: "right" }}>Total (kg)</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {linhas.map((l, idx) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 700 }}>{l.numero_matriz}</td>
                    <td>
                      <input type="date" style={inputStyle} value={l.data_controle}
                        onChange={(e) => atualizarLinha(idx, { data_controle: e.target.value })} />
                    </td>
                    <td><input type="number" inputMode="decimal" style={{ ...inputStyle, textAlign: "right" }}
                      value={l.ordenha1_kg ?? ""} onChange={(e) => atualizarLinha(idx, { ordenha1_kg: num(e.target.value) })} /></td>
                    <td><input type="number" inputMode="decimal" style={{ ...inputStyle, textAlign: "right" }}
                      value={l.ordenha2_kg ?? ""} onChange={(e) => atualizarLinha(idx, { ordenha2_kg: num(e.target.value) })} /></td>
                    <td><input type="number" inputMode="decimal" style={{ ...inputStyle, textAlign: "right" }}
                      value={l.ordenha3_kg ?? ""} onChange={(e) => atualizarLinha(idx, { ordenha3_kg: num(e.target.value) })} /></td>
                    <td><input type="number" inputMode="decimal" style={{ ...inputStyle, textAlign: "right" }}
                      value={l.total_kg ?? ""} onChange={(e) => atualizarLinha(idx, { total_kg: num(e.target.value) })} /></td>
                    <td>
                      <button type="button" className="btn-ghost" title="Remover esta linha" onClick={() => removerLinha(idx)}>
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
                {!linhas.length && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma linha restante.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-2 mt-3">
            <button type="button" className="btn-primary" disabled={!linhas.length || salvando} onClick={confirmar}>
              {salvando ? "Salvando…" : `Confirmar e salvar (${linhas.length})`}
            </button>
            <button type="button" className="btn-ghost" onClick={() => { setLinhas(null); setErrosLeitura([]); }}>Cancelar</button>
          </div>
        </div>
      )}
    </div>
  );
}

// Upload de planilha (Excel/.xlsx ou CSV) — usado tanto em Controle leiteiro
// (por animal ou por lote, um botão de modelo cada) quanto em Qualidade do
// leite (um modelo só). O parser do backend identifica o formato sozinho.
export function FormControle({ animais, lotesLact }: { animais: AnimalRow[]; lotesLact: string[] }) {
  const [modo, setModo] = useState<"vaca" | "lote" | "planilha">("vaca");
  const [vaca, setVaca] = useState("");
  const [lote, setLote] = useState("");
  const [nOrd, setNOrd] = useState(2);
  const [ord, setOrd] = useState<string[]>(["", "", ""]);
  const [porVaca, setPorVaca] = useState<Record<string, string[]>>({});
  const [dataControle, setDataControle] = useState(() => new Date().toISOString().slice(0, 10));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const del = useMemo(() => animais.find((a) => a.numero === vaca)?.del_dias ?? null, [animais, vaca]);
  // Controle leiteiro é só de quem está em lactação: em lote de lactação
  // (01/02/03) ou com DEL em curso (> 0).
  const animaisLact = useMemo(
    () => animais.filter((a) => (a.grupo_primario && lotesLact.includes(a.grupo_primario)) || ((a.del_dias ?? 0) > 0)),
    [animais, lotesLact],
  );
  const total = ord.slice(0, nOrd).reduce((s, v) => s + (Number(v) || 0), 0);

  // Vacas do lote selecionado — abre a listagem individual pra pesagem de cada uma.
  const vacasDoLote = useMemo(() => (lote ? animais.filter((a) => a.grupo_primario === lote) : []), [animais, lote]);
  const ordVacas = useOrdenacao(vacasDoLote);
  const setOrdVaca = (numero: string, idx: number, valor: string) =>
    setPorVaca((p) => { const arr = [...(p[numero] || ["", "", ""])]; arr[idx] = valor; return { ...p, [numero]: arr }; });
  const totalVaca = (numero: string) => (porVaca[numero] || []).slice(0, nOrd).reduce((s, v) => s + (Number(v) || 0), 0);
  const totalLote = vacasDoLote.reduce((s, a) => s + totalVaca(a.numero), 0);

  function limpar() {
    setOrd(["", "", ""]);
    setPorVaca({});
  }

  async function salvar() {
    setErro(null); setSucesso(null);
    // Ordenha em branco vira `null` (não lançada), nunca `0` — um `0` gravado
    // como se fosse ordenha real puxaria a média de manhã/noite para baixo.
    const ordenhaOuNull = (v: string) => (v.trim() === "" ? null : Number(v));
    const entradas = modo === "vaca"
      ? (vaca ? [{ numero_matriz: vaca, ordenhas: ord.slice(0, nOrd).map(ordenhaOuNull) }] : [])
      : vacasDoLote.map((a) => ({ numero_matriz: a.numero, ordenhas: (porVaca[a.numero] || []).slice(0, nOrd).map(ordenhaOuNull) }))
          .filter((e) => e.ordenhas.some((v) => v !== null));
    if (!entradas.length) { setErro(modo === "vaca" ? "Selecione a vaca e informe ao menos uma ordenha." : "Informe a pesagem de ao menos uma vaca do lote."); return; }
    setSalvando(true);
    try {
      const r = await criarControlesLeiteiros({ data_controle: dataControle, entradas });
      setSucesso(`${r.criados} ${r.criados === 1 ? "pesagem" : "pesagens"} lançada${r.criados === 1 ? "" : "s"} com sucesso.`);
      limpar();
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar controle leiteiro");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Modalidade">
          <select style={inputStyle} value={modo} onChange={(e) => { setModo(e.target.value as any); setErro(null); setSucesso(null); }}>
            <option value="vaca">Por vaca</option>
            <option value="lote">Por lote</option>
            <option value="planilha">Importar de planilha</option>
          </select>
        </Campo>
        {modo !== "planilha" && (
          <Campo label="Nº de ordenhas">
            <select style={inputStyle} value={nOrd} onChange={(e) => setNOrd(Number(e.target.value))}>
              <option value={2}>2 ordenhas</option>
              <option value={3}>3 ordenhas</option>
            </select>
          </Campo>
        )}
        {modo === "vaca" && (
          <>
            <Campo label="Vaca (só em lactação)"><SelectAnimal animais={animaisLact} value={vaca} onChange={setVaca} placeholder="Selecione a vaca em lactação…" /></Campo>
            <Campo label="DEL (automático)"><input style={{ ...inputStyle, opacity: 0.8 }} value={del != null ? `${del} dias` : "—"} readOnly /></Campo>
          </>
        )}
        {modo === "lote" && (
          <Campo label="Lote">
            <select style={inputStyle} value={lote} onChange={(e) => setLote(e.target.value)}>
              <option value="">Selecione…</option>
              {lotesLact.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </Campo>
        )}
        {modo !== "planilha" && (
          <Campo label="Data do controle"><input type="date" style={inputStyle} value={dataControle} onChange={(e) => setDataControle(e.target.value)} /></Campo>
        )}
      </div>
      </div>

      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      {modo === "planilha" && (
        <RevisarPlanilhaControleLeiteiro />
      )}

      {modo !== "planilha" && (modo === "vaca" ? (
        <div className="mt-3">
          <label style={lbl}>Quilos por ordenha</label>
          <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
            {Array.from({ length: nOrd }, (_, i) => (
              <div key={i}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{i + 1}ª ordenha</span>
                <input type="number" inputMode="decimal" style={{ ...inputStyle, width: "7rem" }} value={ord[i]}
                  onChange={(e) => setOrd((p) => { const n = [...p]; n[i] = e.target.value; return n; })} placeholder="kg" />
              </div>
            ))}
            <div>
              <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Total do dia</span>
              <div style={{ ...inputStyle, width: "7rem", fontWeight: 700, color: "var(--green-light)" }}>{total.toFixed(1)} kg</div>
            </div>
          </div>
        </div>
      ) : lote ? (
        <div className="card mt-3" style={{ padding: 0 }}>
          <div className="card-header m-3 flex items-center justify-between">
            <span>Vacas do lote {lote} ({vacasDoLote.length})</span>
            <span style={{ fontSize: "0.78rem", color: "var(--green-light)", fontWeight: 700 }}>Total do lote: {totalLote.toFixed(1)} kg</span>
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: "460px" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Nº" campo="numero" coluna={ordVacas.coluna} dir={ordVacas.dir} ordenar={ordVacas.ordenar} />
                  <ThOrdenavel label="DEL" campo="del_dias" coluna={ordVacas.coluna} dir={ordVacas.dir} ordenar={ordVacas.ordenar} />
                  {Array.from({ length: nOrd }, (_, i) => <th key={i} style={{ textAlign: "right" }}>{i + 1}ª ordenha (kg)</th>)}
                  <th style={{ textAlign: "right" }}>Total</th>
                </tr>
              </thead>
              <tbody>
                {ordVacas.linhasOrdenadas.map((a) => (
                  <tr key={a.numero}>
                    <td style={{ fontWeight: 700 }}>{a.numero}</td>
                    <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{a.del_dias ?? "—"}</td>
                    {Array.from({ length: nOrd }, (_, i) => (
                      <td key={i}>
                        <input type="number" inputMode="decimal" style={{ ...inputStyle, textAlign: "right" }}
                          value={(porVaca[a.numero] || [])[i] || ""} onChange={(e) => setOrdVaca(a.numero, i, e.target.value)} placeholder="kg" />
                      </td>
                    ))}
                    <td style={{ textAlign: "right", fontWeight: 700, color: "var(--green-light)" }}>{totalVaca(a.numero).toFixed(1)}</td>
                  </tr>
                ))}
                {!vacasDoLote.length && <tr><td colSpan={nOrd + 3} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma vaca neste lote.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p style={nota}>Selecione um lote para ver a listagem de vacas e lançar a pesagem individual de todas de uma vez.</p>
      ))}

      {modo !== "planilha" && erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {modo !== "planilha" && sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

      {modo !== "planilha" && (
        <div className="flex items-center gap-3 mt-4">
          <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
        </div>
      )}
      </div>
      </div>
    </>
  );
}

