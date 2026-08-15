"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Scale } from "lucide-react";
import { criarPesagensCorporais, fetchRelatorioPesagemCorporal, fetchPesagens, type PesagemLinha, formatDate, baixarModeloPesagemCorporal, importarPesagemCorporalPlanilha } from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { UploadPlanilha } from "@/components/UploadPlanilha";
import { UltimosLancados } from "@/components/lancamentos/UltimosLancados";

const COLUNAS_PESAGEM = [
  { header: "Nº", key: "numero_matriz" }, { header: "Lote", key: "grupo_primario" },
  { header: "Nº pesagens", key: "num_pesagens" }, { header: "1ª pesagem (data)", key: "primeira_data_fmt" },
  { header: "1ª pesagem (kg)", key: "primeira_peso" }, { header: "Última pesagem (data)", key: "ultima_data_fmt" },
  { header: "Última pesagem (kg)", key: "ultima_peso" }, { header: "GMD (kg/dia)", key: "gmd_kg_dia" }, { header: "GPD (kg/dia)", key: "gpd_kg_dia" },
];

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };
const nota: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", marginLeft: "0.35rem" };

function Campo({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return <div style={full ? { gridColumn: "1 / -1" } : undefined}><label style={lbl}>{label}</label>{children}</div>;
}

type Linha = {
  numero_matriz: string; grupo_primario: string | null;
  primeira_data: string; primeira_peso: number; ultima_data: string; ultima_peso: number;
  gmd_kg_dia: number | null; gpd_kg_dia: number | null; num_pesagens: number;
};

export function FormPesagemCorporal({ animais, lotes }: { animais: AnimalRow[]; lotes: string[] }) {
  // Lançamento
  const [modo, setModo] = useState<"vaca" | "lote" | "planilha">("vaca");
  const [vaca, setVaca] = useState("");
  const [lote, setLote] = useState("");
  const [peso, setPeso] = useState("");
  const [porVaca, setPorVaca] = useState<Record<string, string>>({});
  const [dataPesagem, setDataPesagem] = useState(() => new Date().toISOString().slice(0, 10));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const vacasDoLote = useMemo(() => (lote ? animais.filter((a) => a.grupo_primario === lote) : []), [animais, lote]);
  const ordVacas = useOrdenacao(vacasDoLote);

  // G13 — "últimos lançados": conferir/corrigir as pesagens recém-digitadas
  // sem sair da tela de Lançamentos.
  const [recentes, setRecentes] = useState<PesagemLinha[]>([]);
  const carregarRecentes = useCallback(() => {
    fetchPesagens({ limite: 10 }).then((d) => setRecentes(d.pesagens)).catch(() => setRecentes([]));
  }, []);
  useEffect(carregarRecentes, [carregarRecentes]);

  function limpar() {
    setPeso("");
    setPorVaca({});
  }

  async function salvar() {
    setErro(null); setSucesso(null);
    const entradas = modo === "vaca"
      ? (vaca && Number(peso) > 0 ? [{ numero_matriz: vaca, peso_kg: Number(peso) }] : [])
      : vacasDoLote.map((a) => ({ numero_matriz: a.numero, peso_kg: Number(porVaca[a.numero]) || 0 })).filter((e) => e.peso_kg > 0);
    if (!entradas.length) { setErro(modo === "vaca" ? "Selecione o animal e informe o peso." : "Informe o peso de ao menos um animal do lote."); return; }
    setSalvando(true);
    try {
      const r = await criarPesagensCorporais({ data_pesagem: dataPesagem, entradas });
      setSucesso(`${r.criados} ${r.criados === 1 ? "pesagem lançada" : "pesagens lançadas"} com sucesso.`);
      limpar();
      atualizarRelatorio();
      carregarRecentes();
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar pesagem corporal");
    } finally {
      setSalvando(false);
    }
  }

  // Relatório de GMD/GPD
  const [relTipo, setRelTipo] = useState<"animal" | "lote" | "todos">("todos");
  const [relAnimal, setRelAnimal] = useState("");
  const [relLote, setRelLote] = useState("");
  const [relIni, setRelIni] = useState("");
  const [relFim, setRelFim] = useState("");
  const [linhas, setLinhas] = useState<Linha[] | null>(null);
  const [carregandoRel, setCarregandoRel] = useState(false);

  const atualizarRelatorio = () => {
    setCarregandoRel(true);
    fetchRelatorioPesagemCorporal({
      numero_matriz: relTipo === "animal" ? relAnimal || undefined : undefined,
      grupo: relTipo === "lote" ? relLote || undefined : undefined,
      data_inicio: relIni || undefined,
      data_fim: relFim || undefined,
    }).then((d) => setLinhas(d.linhas)).catch(() => setLinhas([])).finally(() => setCarregandoRel(false));
  };
  useEffect(atualizarRelatorio, [relTipo, relAnimal, relLote, relIni, relFim]);

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Modalidade">
          <select style={inputStyle} value={modo} onChange={(e) => { setModo(e.target.value as any); setErro(null); setSucesso(null); }}>
            <option value="vaca">Por animal</option>
            <option value="lote">Por lote</option>
            <option value="planilha">Importar de planilha</option>
          </select>
        </Campo>
        {modo !== "planilha" && (
          <Campo label="Data da pesagem"><input type="date" style={inputStyle} value={dataPesagem} onChange={(e) => setDataPesagem(e.target.value)} /></Campo>
        )}
        {modo === "vaca" && (
          <Campo label="Animal" full><AnimalPicker animais={animais} value={vaca} onChange={setVaca} placeholder="Selecione o animal…" /></Campo>
        )}
        {modo === "lote" && (
          <Campo label="Lote" full>
            <select style={inputStyle} value={lote} onChange={(e) => setLote(e.target.value)}>
              <option value="">Selecione…</option>
              {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </Campo>
        )}
      </div>

      {modo === "planilha" && (
        <UploadPlanilha
          modelos={[{ label: "Baixar modelo", baixar: baixarModeloPesagemCorporal }]}
          onImportar={importarPesagemCorporalPlanilha}
        />
      )}

      {modo !== "planilha" && (modo === "vaca" ? (
        <div className="mt-3">
          <label style={lbl}>Peso (kg)</label>
          <input type="number" inputMode="decimal" style={{ ...inputStyle, width: "10rem" }} value={peso} onChange={(e) => setPeso(e.target.value)} placeholder="kg" />
        </div>
      ) : lote ? (
        <div className="card mt-3" style={{ padding: 0 }}>
          <div className="card-header m-3">Animais do lote {lote} ({vacasDoLote.length})</div>
          <div className="overflow-x-auto" style={{ maxHeight: "460px" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Nº" campo="numero" coluna={ordVacas.coluna} dir={ordVacas.dir} ordenar={ordVacas.ordenar} />
                  <ThOrdenavel label="Idade (meses)" campo="idade_meses" coluna={ordVacas.coluna} dir={ordVacas.dir} ordenar={ordVacas.ordenar} />
                  <th style={{ textAlign: "right" }}>Peso (kg)</th>
                </tr>
              </thead>
              <tbody>
                {ordVacas.linhasOrdenadas.map((a) => (
                  <tr key={a.numero}>
                    <td style={{ fontWeight: 700 }}>{a.numero}</td>
                    <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{(a as any).idade_meses ?? "—"}</td>
                    <td>
                      <input type="number" inputMode="decimal" style={{ ...inputStyle, textAlign: "right" }}
                        value={porVaca[a.numero] || ""} onChange={(e) => setPorVaca((p) => ({ ...p, [a.numero]: e.target.value }))} placeholder="kg" />
                    </td>
                  </tr>
                ))}
                {!vacasDoLote.length && <tr><td colSpan={3} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhum animal neste lote.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p style={nota}>Selecione um lote para ver a listagem de animais e lançar o peso de todos de uma vez.</p>
      ))}

      {modo !== "planilha" && erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {modo !== "planilha" && sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

      {modo !== "planilha" && (
        <div className="flex items-center gap-3 mt-4 mb-2">
          <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
        </div>
      )}

      <div className="card mt-4">
        <div className="card-header mb-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
          <span className="flex items-center gap-2"><Scale size={14} /> Relatório de crescimento (GMD / GPD)</span>
          <ExportarBotoes
            titulo="Relatório de crescimento (GMD/GPD)" nomeArquivoBase="pesagem_corporal"
            colunas={COLUNAS_PESAGEM}
            linhas={(linhas || []).map((l) => ({ ...l, primeira_data_fmt: formatDate(l.primeira_data), ultima_data_fmt: formatDate(l.ultima_data) }))}
          />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <Campo label="Ver">
            <select style={inputStyle} value={relTipo} onChange={(e) => { setRelTipo(e.target.value as any); setRelAnimal(""); setRelLote(""); }}>
              <option value="todos">Todos os animais</option>
              <option value="lote">Um lote</option>
              <option value="animal">Um animal</option>
            </select>
          </Campo>
          {relTipo === "animal" && (
            <Campo label="Animal"><AnimalPicker animais={animais} value={relAnimal} onChange={setRelAnimal} placeholder="Selecione…" /></Campo>
          )}
          {relTipo === "lote" && (
            <Campo label="Lote">
              <select style={inputStyle} value={relLote} onChange={(e) => setRelLote(e.target.value)}>
                <option value="">Selecione…</option>
                {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
              </select>
            </Campo>
          )}
          <Campo label="Período de"><input type="date" style={inputStyle} value={relIni} onChange={(e) => setRelIni(e.target.value)} /></Campo>
          <Campo label="Período até"><input type="date" style={inputStyle} value={relFim} onChange={(e) => setRelFim(e.target.value)} /></Campo>
        </div>

        {carregandoRel ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Carregando…</p>
        ) : (
          <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
            <table className="fazenda-table">
              <thead>
                <tr>
                  <th>Nº</th><th>Lote</th><th style={{ textAlign: "right" }}>Nº pesagens</th>
                  <th>1ª pesagem</th><th>Última pesagem</th>
                  <th style={{ textAlign: "right" }}>GMD (kg/dia)</th><th style={{ textAlign: "right" }}>GPD (kg/dia)</th>
                </tr>
              </thead>
              <tbody>
                {(linhas || []).map((l) => (
                  <tr key={l.numero_matriz}>
                    <td style={{ fontWeight: 700 }}>{l.numero_matriz}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{l.grupo_primario || "—"}</td>
                    <td style={{ textAlign: "right" }}>{l.num_pesagens}</td>
                    <td style={{ fontSize: "0.78rem" }}>{formatDate(l.primeira_data)} · {l.primeira_peso} kg</td>
                    <td style={{ fontSize: "0.78rem" }}>{formatDate(l.ultima_data)} · {l.ultima_peso} kg</td>
                    <td style={{ textAlign: "right", fontWeight: 700, color: "var(--green-light)" }}>{l.gmd_kg_dia ?? "—"}</td>
                    <td style={{ textAlign: "right", fontWeight: 700 }}>{l.gpd_kg_dia ?? "—"}</td>
                  </tr>
                ))}
                {!(linhas || []).length && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma pesagem no filtro.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        <p style={nota}>GMD: ganho médio diário entre a primeira e a última pesagem do período. GPD: média dos ganhos diários entre pesagens consecutivas.</p>
      </div>

      <UltimosLancados<PesagemLinha>
        titulo="Últimas pesagens lançadas"
        linhas={recentes}
        colunas={[
          { label: "Animal", render: (l) => <span style={{ fontWeight: 700 }}>{l.numero_matriz}</span> },
          { label: "Data", render: (l) => formatDate(l.data_pesagem) },
          { label: "kg", render: (l) => l.peso_kg, alinhar: "right" },
        ]}
        tipoExclusao="pesagem_corporal"
        onExcluido={() => { carregarRecentes(); atualizarRelatorio(); }}
      />
    </>
  );
}
