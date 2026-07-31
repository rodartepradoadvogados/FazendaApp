"use client";
import { useEffect, useMemo, useState } from "react";
import { Filter, Baby, AlertTriangle } from "lucide-react";
import { fetchAnimais, fetchRelatorioBezerras, ehAdmin } from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { SelecaoAnimaisTabela } from "@/components/SelecaoAnimaisTabela";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

type LinhaBezerra = {
  numero: string; nome: string | null; sexo: string | null; categoria_abrev: string | null;
  grupo_primario: string | null; data_nasc: string | null; idade_meses: number | null; ativo: boolean;
  tomou_colostro: boolean | null; litros_colostro: number | null; brix_colostro: number | null;
  classe_colostro: "ouro" | "prata" | "bronze" | null; data_colostro: string | null;
  hora_parto: string | null; hora_colostro: string | null; peso_nascer_kg: number | null;
  brix_soro: number | null; proteina_serica: number | null;
  classe_soro: "sucesso" | "alerta" | "falha" | null;
  classe_colostragem: "excelente" | "boa" | "aceitavel" | "ruim" | null;
  apenas_colostro_po: boolean; sem_mensuracao: boolean; data_teste_sangue: string | null;
  usuario_nome?: string | null;
};

const LABEL_CLASSE_COLOSTRO: Record<string, { txt: string; cor: string }> = {
  ouro: { txt: "Ouro", cor: "var(--dourado-light)" }, prata: { txt: "Prata", cor: "var(--text-muted)" },
  bronze: { txt: "Bronze", cor: "var(--red)" },
};
const LABEL_CLASSE_SORO: Record<string, { txt: string; cor: string }> = {
  sucesso: { txt: "Sucesso", cor: "var(--green-light)" }, alerta: { txt: "Alerta", cor: "var(--amber)" },
  falha: { txt: "Falha", cor: "var(--red)" },
};
const LABEL_CLASSE_COLOSTRAGEM: Record<string, { txt: string; cor: string }> = {
  excelente: { txt: "Excelente", cor: "var(--green-light)" }, boa: { txt: "Boa", cor: "var(--dourado-light)" },
  aceitavel: { txt: "Aceitável", cor: "var(--amber)" }, ruim: { txt: "Ruim", cor: "var(--red)" },
};

const COLUNAS_BEZERRAS = [
  { header: "Data", key: "data_teste_sangue" }, { header: "Nº", key: "numero" }, { header: "Nome", key: "nome" },
  { header: "Categoria", key: "categoria_abrev" }, { header: "Lote", key: "grupo_primario" }, { header: "Idade (meses)", key: "idade_meses" },
  { header: "Tomou colostro", key: "tomou_colostroFmt" }, { header: "Litros", key: "litros_colostro" },
  { header: "Brix colostro (%)", key: "brix_colostro" }, { header: "Classe colostro", key: "classe_colostroFmt" },
  { header: "Brix soro (%)", key: "brix_soro" }, { header: "Proteína sérica (g/dL)", key: "proteina_serica" },
  { header: "Eficiência colostragem", key: "classe_colostragemFmt" }, { header: "Classe soro", key: "classe_soroFmt" },
];

export default function RelatorioBezerras() {
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [modo, setModo] = useState<"todos" | "animal" | "lote" | "selecao">("todos");
  const [faixaEtaria, setFaixaEtaria] = useState("");
  const [numeroFiltro, setNumeroFiltro] = useState("");
  const [loteFiltro, setLoteFiltro] = useState("");
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [dados, setDados] = useState<LinhaBezerra[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const admin = ehAdmin();

  useEffect(() => { fetchAnimais().then(setAnimais).catch(() => {}); }, []);

  useEffect(() => {
    const filtros: { faixaEtaria?: string; numero?: string; lote?: string; numeros?: string[] } = {};
    if (faixaEtaria) filtros.faixaEtaria = faixaEtaria;
    if (modo === "animal" && numeroFiltro) filtros.numero = numeroFiltro;
    if (modo === "lote" && loteFiltro) filtros.lote = loteFiltro;
    if (modo === "selecao" && selecionados.size) filtros.numeros = Array.from(selecionados);
    fetchRelatorioBezerras(filtros).then(setDados).catch((e) => setErro(e.message));
  }, [faixaEtaria, modo, numeroFiltro, loteFiltro, selecionados]);

  const lotes = useMemo(
    () => Array.from(new Set(animais.map((a) => a.grupo_primario).filter(Boolean))).sort() as string[],
    [animais]
  );

  const toggleSelecionado = (numero: string) => setSelecionados((prev) => {
    const novo = new Set(prev);
    novo.has(numero) ? novo.delete(numero) : novo.add(numero);
    return novo;
  });
  const toggleTodos = () => setSelecionados((prev) => (prev.size === animais.length ? new Set() : new Set(animais.map((a) => a.numero))));

  const linhasExport = (dados || []).map((l) => ({
    ...l, tomou_colostroFmt: l.tomou_colostro == null ? "—" : l.tomou_colostro ? "Sim" : "Não",
    classe_colostroFmt: l.classe_colostro ? LABEL_CLASSE_COLOSTRO[l.classe_colostro].txt : "—",
    classe_soroFmt: l.classe_soro ? LABEL_CLASSE_SORO[l.classe_soro].txt : "—",
    classe_colostragemFmt: l.classe_colostragem ? LABEL_CLASSE_COLOSTRAGEM[l.classe_colostragem].txt : (l.apenas_colostro_po ? "Só colostro em pó" : l.sem_mensuracao ? "Sem mensuração" : "—"),
  }));

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const ord = useOrdenacao(dados || []);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Baby size={22} style={{ color: "var(--dourado-light)" }} /> Relatório de bezerras</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Colostragem e teste de sangue (IgG) por animal — inclusive já adultos.</p>
      </div>

      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Faixa etária</label>
            <select style={selStyle} value={faixaEtaria} onChange={(e) => setFaixaEtaria(e.target.value)}>
              <option value="">Todas</option>
              <option value="ate_12">Bezerras (até 12 meses)</option>
              <option value="acima_12">Acima de 12 meses (novilhas/vacas)</option>
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ver</label>
            <select style={selStyle} value={modo} onChange={(e) => setModo(e.target.value as typeof modo)}>
              <option value="todos">Todos os animais</option>
              <option value="animal">Um animal</option>
              <option value="lote">Por lote atual</option>
              <option value="selecao">Seleção de vários animais</option>
            </select></div>
          {modo === "animal" && (
            <div style={{ gridColumn: "span 2" }}><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
              <AnimalPicker animais={animais} value={numeroFiltro} onChange={setNumeroFiltro} /></div>
          )}
          {modo === "lote" && (
            <div style={{ gridColumn: "span 2" }}><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Lote</label>
              <select style={selStyle} value={loteFiltro} onChange={(e) => setLoteFiltro(e.target.value)}>
                <option value="">Selecione…</option>
                {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
              </select></div>
          )}
        </div>
        {modo === "selecao" && (
          <SelecaoAnimaisTabela
            animais={animais} selecionados={selecionados} toggle={toggleSelecionado} toggleTodos={toggleTodos}
            colunas={[
              { header: "Grupo", campo: "grupo_primario", render: (a) => a.grupo_primario || "—" },
              { header: "Categoria", campo: "categoria_abrev", render: (a) => a.categoria_abrev || a.categoria_completa || "—" },
            ]}
          />
        )}
      </div>

      {erro && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {erro}.</span></div>}
      {!dados && !erro && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {dados && (
        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between">
            <span className="flex items-center gap-2"><Baby size={14} /> Relatório sanitário de bezerras ({dados.length})</span>
            <ExportarBotoes titulo="Relatório sanitário de bezerras" nomeArquivoBase="relatorio_bezerras" colunas={COLUNAS_BEZERRAS} linhas={linhasExport} />
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: "560px" }}>
            <table className="fazenda-table">
              <thead>
                <tr>
                  <ThOrdenavel label="Nº" campo="numero" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="Nome" campo="nome" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="Categoria" campo="categoria_abrev" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="Lote" campo="grupo_primario" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="Idade (m)" campo="idade_meses" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                  <ThOrdenavel label="Colostro?" campo="tomou_colostro" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="Litros" campo="litros_colostro" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                  <ThOrdenavel label="Brix colostro" campo="brix_colostro" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                  <ThOrdenavel label="Classe colostro" campo="classe_colostro" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  <ThOrdenavel label="Brix soro" campo="brix_soro" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                  <ThOrdenavel label="Prot. sérica" campo="proteina_serica" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                  <ThOrdenavel label="Eficiência (IgG)" campo="classe_colostragem" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                  {admin && <ThOrdenavel label="Usuário" campo="usuario_nome" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="left" />}
                </tr>
              </thead>
              <tbody>
                {ord.linhasOrdenadas.map((l) => {
                  const grave = l.classe_soro === "falha" || l.classe_colostragem === "ruim" || l.classe_colostro === "bronze";
                  const trStyle: React.CSSProperties = grave
                    ? { background: "rgba(192,57,43,0.12)", borderLeft: "3px solid var(--red)" }
                    : {};
                  return (
                    <tr key={l.numero} style={trStyle}>
                      <td style={{ fontWeight: 700 }}>{l.numero}</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.nome || "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.categoria_abrev || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.grupo_primario || "—"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{l.idade_meses ?? "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.tomou_colostro == null ? "—" : l.tomou_colostro ? "Sim" : "Não"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{l.litros_colostro ?? "—"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{l.brix_colostro ?? "—"}</td>
                      <td style={{ fontSize: "0.78rem", fontWeight: 700, color: l.classe_colostro ? LABEL_CLASSE_COLOSTRO[l.classe_colostro].cor : "var(--text-muted)" }}>
                        {l.classe_colostro ? LABEL_CLASSE_COLOSTRO[l.classe_colostro].txt : "—"}
                      </td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{l.brix_soro ?? "—"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{l.proteina_serica ?? "—"}</td>
                      <td style={{ fontSize: "0.78rem", fontWeight: 700, color: l.classe_colostragem ? LABEL_CLASSE_COLOSTRAGEM[l.classe_colostragem].cor : "var(--text-muted)" }}>
                        {l.classe_colostragem
                          ? LABEL_CLASSE_COLOSTRAGEM[l.classe_colostragem].txt
                          : l.apenas_colostro_po
                            ? <span style={{ color: "var(--blue)" }}>Só colostro em pó</span>
                            : l.sem_mensuracao
                              ? <span style={{ color: "var(--text-muted)" }}>Sem mensuração</span>
                              : "—"}
                      </td>
                      {admin && <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{l.usuario_nome ?? "—"}</td>}
                    </tr>
                  );
                })}
                {!dados.length && <tr><td colSpan={admin ? 13 : 12} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum animal encontrado com esses filtros.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
