"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Dna, Trash2, Search, RefreshCw, Plus, Pencil, ChevronDown, ChevronRight, X, Upload } from "lucide-react";
import {
  fetchTouros, fetchTourosCowData, criarTouroCowData, atualizarTouroCowData, excluirTouroCowData,
  recarregarCatalogoTourosCowData, importarPlanilhaTourosCowData, type Touro, type TouroIn,
} from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { casaBusca } from "@/lib/busca";

const fmt = (v?: number | null, dec = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: dec, maximumFractionDigits: dec });

export const CAMPO_VAZIO: TouroIn = {
  naab: "", nome: "", nome_completo: "", raca: "", central: "",
  leite_kg: null, gordura_kg: null, gordura_pct: null, proteina_kg: null, proteina_pct: null,
  tpi: null, nm_dolar: null, tipo_composto: null, ubere_composto: null, pernas_composto: null,
  ccs_score: null, fertilidade_filhas: null, facilidade_parto: null,
  fonte: "", rodada_prova: "", observacao: "", dados_extra: [],
};

export const CAMPOS_NUMERICOS: { chave: keyof TouroIn; label: string }[] = [
  { chave: "leite_kg", label: "Leite (kg)" },
  { chave: "gordura_kg", label: "Gordura (kg)" },
  { chave: "gordura_pct", label: "Gordura (%)" },
  { chave: "proteina_kg", label: "Proteína (kg)" },
  { chave: "proteina_pct", label: "Proteína (%)" },
  { chave: "tpi", label: "TPI" },
  { chave: "nm_dolar", label: "NM$" },
  { chave: "tipo_composto", label: "Tipo (composto)" },
  { chave: "ubere_composto", label: "Úbere (composto)" },
  { chave: "pernas_composto", label: "Pernas (composto)" },
  { chave: "ccs_score", label: "CCS/SCS" },
  { chave: "fertilidade_filhas", label: "Fertilidade das filhas" },
  { chave: "facilidade_parto", label: "Facilidade de parto" },
];

export function parseDadosExtra(json?: string | null): [string, string][] {
  if (!json) return [];
  try {
    const v = JSON.parse(json);
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

export function FormTouro({ inicial, onSalvar, onCancelar }: { inicial: TouroIn; onSalvar: (d: TouroIn) => Promise<void>; onCancelar: () => void }) {
  const [dados, setDados] = useState<TouroIn>(inicial);
  const [extra, setExtra] = useState<[string, string][]>(inicial.dados_extra || []);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  const set = (chave: keyof TouroIn, valor: any) => setDados((d) => ({ ...d, [chave]: valor }));

  async function salvar() {
    if (!dados.naab.trim() || !dados.nome?.trim()) {
      setErro("Código NAAB e nome do touro são obrigatórios.");
      return;
    }
    setErro("");
    setSalvando(true);
    try {
      await onSalvar({ ...dados, dados_extra: extra.filter(([l, v]) => l.trim() && v.trim()) });
    } catch (e: any) {
      setErro(e.message || "Falha ao salvar");
    } finally {
      setSalvando(false);
    }
  }

  const inputStyle: React.CSSProperties = { width: "100%", padding: "0.45rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" };
  const labelStyle: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem", display: "block" };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "flex-start", justifyContent: "center", zIndex: 200, overflowY: "auto", padding: "2rem 1rem" }}>
      <div style={{ background: "var(--bg)", borderRadius: "var(--r-sm)", padding: "1.5rem", width: "100%", maxWidth: "42rem", border: "1px solid var(--border)" }}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold flex items-center gap-2"><Dna size={18} style={{ color: "var(--dourado)" }} /> {inicial.naab ? "Editar touro" : "Novo touro"}</h3>
          <button onClick={onCancelar} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}><X size={18} /></button>
        </div>

        {erro && <p style={{ color: "var(--vermelho, #d33)", fontSize: "0.85rem", marginBottom: "0.6rem" }}>{erro}</p>}

        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label style={labelStyle}>Código NAAB *</label>
            <input style={inputStyle} value={dados.naab} onChange={(e) => set("naab", e.target.value.toUpperCase())} placeholder="ex.: 007HO12345" />
          </div>
          <div>
            <label style={labelStyle}>Nome do touro *</label>
            <input style={inputStyle} value={dados.nome || ""} onChange={(e) => set("nome", e.target.value)} placeholder="ex.: AltaBRONTIDE" />
          </div>
          <div>
            <label style={labelStyle}>Nome completo</label>
            <input style={inputStyle} value={dados.nome_completo || ""} onChange={(e) => set("nome_completo", e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Raça</label>
            <input style={inputStyle} value={dados.raca || ""} onChange={(e) => set("raca", e.target.value)} placeholder="ex.: HO, Girolando..." />
          </div>
          <div>
            <label style={labelStyle}>Central</label>
            <input style={inputStyle} value={dados.central || ""} onChange={(e) => set("central", e.target.value)} placeholder="ex.: Alta, ABS, Select Sires..." />
          </div>
          <div>
            <label style={labelStyle}>Fonte</label>
            <input style={inputStyle} value={dados.fonte || ""} onChange={(e) => set("fonte", e.target.value)} placeholder="ex.: Alta Genetics" />
          </div>
          <div>
            <label style={labelStyle}>Rodada da prova</label>
            <input style={inputStyle} value={dados.rodada_prova || ""} onChange={(e) => set("rodada_prova", e.target.value)} placeholder="ex.: Jul/2026" />
          </div>
        </div>

        <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", margin: "0.8rem 0 0.4rem" }}>Provas genéticas (opcional)</p>
        <div className="grid grid-cols-3 gap-3 mb-3">
          {CAMPOS_NUMERICOS.map(({ chave, label }) => (
            <div key={chave}>
              <label style={labelStyle}>{label}</label>
              <input type="number" step="any" style={inputStyle} value={(dados[chave] as number | null) ?? ""}
                onChange={(e) => set(chave, e.target.value === "" ? null : Number(e.target.value))} />
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between" style={{ margin: "0.8rem 0 0.4rem" }}>
          <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>Outros dados da planilha (opcional)</p>
          <button onClick={() => setExtra((prev) => [...prev, ["", ""]])} className="btn-secondary" style={{ fontSize: "0.78rem", padding: "0.3rem 0.6rem" }}>
            <Plus size={13} style={{ marginRight: "0.2rem" }} /> Adicionar campo
          </button>
        </div>
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
          Use para registrar qualquer coluna da planilha do fornecedor sem equivalente acima (ex.: "Feed Saved", "EFI", "Pedigree"...).
        </p>
        {extra.map(([rotulo, valor], i) => (
          <div key={i} className="flex items-center gap-2 mb-2">
            <input style={{ ...inputStyle, flex: "1 1 40%" }} placeholder="Nome do campo (ex.: Feed Saved)" value={rotulo}
              onChange={(e) => setExtra((prev) => prev.map((p, j) => (j === i ? [e.target.value, p[1]] : p)))} />
            <input style={{ ...inputStyle, flex: "1 1 40%" }} placeholder="Valor" value={valor}
              onChange={(e) => setExtra((prev) => prev.map((p, j) => (j === i ? [p[0], e.target.value] : p)))} />
            <button onClick={() => setExtra((prev) => prev.filter((_, j) => j !== i))} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
              <Trash2 size={15} />
            </button>
          </div>
        ))}

        <div style={{ marginTop: "0.8rem" }}>
          <label style={labelStyle}>Observação</label>
          <textarea style={{ ...inputStyle, minHeight: "3rem" }} value={dados.observacao || ""} onChange={(e) => set("observacao", e.target.value)} />
        </div>

        <div className="flex items-center justify-end gap-2" style={{ marginTop: "1.2rem" }}>
          <button onClick={onCancelar} className="btn-secondary">Cancelar</button>
          <button onClick={salvar} disabled={salvando} className="btn-primary">{salvando ? "Salvando..." : "Salvar"}</button>
        </div>
      </div>
    </div>
  );
}

// O catálogo NAAB é GLOBAL: um `Touro` só (sem fazenda_id) lido por todas as
// fazendas-cliente. Por isso esta mesma tela tem dois modos:
//
//   "fazenda" (padrão) — SOMENTE LEITURA. A fazenda consulta, busca, ordena e
//     abre os dados da planilha; quem edita o catálogo de todo mundo não pode
//     ser o administrador de uma fazenda-cliente. Os botões de cadastrar,
//     editar, excluir e recarregar simplesmente não existem aqui — e o
//     backend também não tem mais as rotas (ver cadastro/genetica.py).
//
//   "painel" — Painel CowData. Lê e escreve pelas rotas /painel-cowdata/
//     touros, sob a permissão "editar touros NAAB" do cadastro de equipe.
//     Precisa ler por lá também: um membro da Equipe CowData não tem fazenda
//     selecionada no token e nem conseguiria chamar a rota da fazenda.
//
// Esconder o botão é só metade: quem protege é a rota. Os dois lados, sempre.
export type ContextoCadastroTouros = "fazenda" | "painel";

export default function CadastroTouros({ contexto = "fazenda" }: { contexto?: ContextoCadastroTouros } = {}) {
  const podeEditar = contexto === "painel";
  const [touros, setTouros] = useState<Touro[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");
  const [info, setInfo] = useState("");
  const [busca, setBusca] = useState("");
  const [expandido, setExpandido] = useState<number | null>(null);
  const [editando, setEditando] = useState<Touro | "novo" | null>(null);
  const [recarregando, setRecarregando] = useState(false);
  // Importar a planilha do fornecedor — saiu de Configurações › Importar
  // dados da fazenda junto com o resto da manutenção do catálogo (ver o
  // comentário do componente). Sem esta caixa aqui, atualizar a rodada de
  // provas deixaria de ter caminho em qualquer lugar do sistema.
  const [fonteImport, setFonteImport] = useState("");
  const [rodadaImport, setRodadaImport] = useState("");
  const [importando, setImportando] = useState(false);

  async function importarPlanilha(file: File) {
    setImportando(true);
    setErro(""); setInfo("");
    try {
      const r = await importarPlanilhaTourosCowData(file, fonteImport.trim(), rodadaImport.trim());
      await carregar();
      const partes = [
        r.criados != null ? `${r.criados} touro(s) novo(s)` : null,
        r.atualizados != null ? `${r.atualizados} atualizado(s)` : null,
      ].filter(Boolean);
      setInfo(`Planilha importada${partes.length ? `: ${partes.join(", ")}` : ""}.`);
      if (r.erros?.length) setErro(r.erros.slice(0, 5).join(" · "));
    } catch (e: any) {
      setErro(e.message || "Falha ao importar a planilha");
    } finally {
      setImportando(false);
    }
  }

  async function recarregarCatalogo() {
    setRecarregando(true);
    setErro(""); setInfo("");
    try {
      const r = await recarregarCatalogoTourosCowData();
      await carregar();
      setInfo(`Catálogo padrão recarregado: ${r.touros_depois} touro(s) no banco (eram ${r.touros_antes}).`);
    } catch (e: any) {
      setErro(e.message || "Falha ao recarregar o catálogo");
    } finally {
      setRecarregando(false);
    }
  }

  async function carregar() {
    setCarregando(true);
    setErro("");
    try {
      setTouros(await (podeEditar ? fetchTourosCowData() : fetchTouros()));
    } catch (e: any) {
      setErro(e.message || "Falha ao carregar touros");
    } finally {
      setCarregando(false);
    }
  }
  useEffect(() => { carregar(); }, [contexto]);  // eslint-disable-line react-hooks/exhaustive-deps

  const filtrados = useMemo(
    () => touros.filter((t) => casaBusca(`${t.naab || ""} ${t.nome || ""} ${t.central || ""} ${t.raca || ""}`, busca)),
    [touros, busca]
  );
  const ord = useOrdenacao(filtrados);

  async function remover(t: Touro) {
    if (!t.id) return;
    if (!confirm(`Excluir o touro ${t.naab}${t.nome ? " — " + t.nome : ""}?`)) return;
    try {
      await excluirTouroCowData(t.id);
      setTouros((prev) => prev.filter((x) => x.id !== t.id));
    } catch (e: any) {
      setErro(e.message || "Falha ao excluir");
    }
  }

  async function salvar(d: TouroIn) {
    if (editando && editando !== "novo" && editando.id) {
      const atualizado = await atualizarTouroCowData(editando.id, d);
      setTouros((prev) => prev.map((t) => (t.id === atualizado.id ? atualizado : t)));
    } else {
      const criado = await criarTouroCowData(d);
      setTouros((prev) => [...prev, criado]);
    }
    setEditando(null);
  }

  const th: React.CSSProperties = { textAlign: "left", padding: "0.5rem 0.6rem", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.03em", color: "var(--text-muted)", whiteSpace: "nowrap", borderBottom: "1px solid var(--border)" };
  const td: React.CSSProperties = { padding: "0.45rem 0.6rem", fontSize: "0.82rem", borderBottom: "1px solid var(--border)", whiteSpace: "nowrap" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-3 flex items-start justify-between" style={{ flexWrap: "wrap", gap: "0.6rem" }}>
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2"><Dna size={18} style={{ color: "var(--dourado)" }} /> Touros (NAAB)</h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
            {podeEditar
              ? "Banco de touros da CowData — o MESMO catálogo para todas as fazendas-cliente. Cadastre manualmente aqui ou importe a planilha do fornecedor. Só o código NAAB e o nome são obrigatórios; todo o resto é opcional."
              : "Banco de touros — consulta do catálogo NAAB usado na prova média, no estudo de touros, na inseminação e na sugestão de acasalamento. O catálogo é o mesmo para todas as fazendas e é mantido pela CowData; para incluir ou corrigir um touro, fale com o suporte."}
          </p>
        </div>
        {podeEditar && (
          <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
            <button onClick={recarregarCatalogo} disabled={recarregando} className="btn-secondary" title="Reimporta o catálogo padrão empacotado no servidor (upsert por NAAB — não apaga touros existentes). Use se o catálogo não aparecer."
              style={{ display: "flex", alignItems: "center", gap: "0.35rem", whiteSpace: "nowrap" }}>
              <RefreshCw size={15} /> {recarregando ? "Recarregando..." : "Recarregar catálogo padrão"}
            </button>
            <button onClick={() => setEditando("novo")} className="btn-primary" style={{ display: "flex", alignItems: "center", gap: "0.35rem", whiteSpace: "nowrap" }}>
              <Plus size={15} /> Novo touro
            </button>
          </div>
        )}
      </div>

      {podeEditar && (
        <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.7rem 0.9rem", marginBottom: "0.9rem", background: "var(--surface)" }}>
          <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--dourado)", marginBottom: "0.2rem" }}>
            Importar a planilha do fornecedor
          </p>
          <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
            Excel (.xlsx) ou CSV exportado do ABS BullSearch, Alta, Select Sires, CRV... Upsert por código NAAB —
            nunca apaga touro existente. Vale para TODAS as fazendas-cliente de uma vez.
          </p>
          <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
            <input value={fonteImport} onChange={(e) => setFonteImport(e.target.value)} placeholder="Central / fonte (ex.: Alta Genetics)"
              style={{ flex: "1 1 12rem", padding: "0.4rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)", fontSize: "0.82rem" }} />
            <input value={rodadaImport} onChange={(e) => setRodadaImport(e.target.value)} placeholder="Rodada da prova (ex.: Ago/2026)"
              style={{ flex: "1 1 12rem", padding: "0.4rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)", fontSize: "0.82rem" }} />
            <label className="btn-secondary" style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", cursor: importando ? "wait" : "pointer", whiteSpace: "nowrap" }}>
              <Upload size={15} /> {importando ? "Importando..." : "Escolher arquivo"}
              <input type="file" accept=".csv,.xlsx,.xlsm" disabled={importando} style={{ display: "none" }}
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) importarPlanilha(f); }} />
            </label>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: "1 1 16rem", maxWidth: "22rem" }}>
          <Search size={15} style={{ position: "absolute", left: "0.6rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por NAAB, nome, central ou raça..."
            style={{ width: "100%", padding: "0.5rem 0.6rem 0.5rem 2rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }} />
        </div>
        <button onClick={carregar} className="btn-secondary" style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
          <RefreshCw size={14} /> Atualizar
        </button>
        <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{filtrados.length} touro(s)</span>
      </div>

      {erro && <p style={{ color: "var(--vermelho, #d33)", fontSize: "0.85rem" }}>{erro}</p>}
      {info && <p style={{ color: "var(--verde, #2a8)", fontSize: "0.85rem" }}>{info}</p>}
      {carregando ? (
        <p style={{ color: "var(--text-muted)" }}>Carregando...</p>
      ) : filtrados.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.88rem" }}>
          {podeEditar
            ? "Nenhum touro cadastrado ainda. Importe a planilha do fornecedor ou clique em \"Novo touro\"."
            : "Nenhum touro no catálogo NAAB ainda. O catálogo é mantido pela CowData — fale com o suporte."}
        </p>
      ) : (
        <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: "60rem" }}>
            <thead>
              <tr>
                <th style={th}></th>
                <ThOrdenavel label="NAAB" campo="naab" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Nome" campo="nome" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Central" campo="central" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Raça" campo="raca" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Leite (kg)" campo="leite_kg" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                <ThOrdenavel label="Gord." campo="gordura_kg" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                <ThOrdenavel label="Prot." campo="proteina_kg" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                <ThOrdenavel label="TPI" campo="tpi" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                <ThOrdenavel label="NM$" campo="nm_dolar" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                <ThOrdenavel label="Fert. filhas" campo="fertilidade_filhas" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                <ThOrdenavel label="Fac. parto" campo="facilidade_parto" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                <th style={th}>Fonte / rodada</th>
                {podeEditar && <th style={th}></th>}
              </tr>
            </thead>
            <tbody>
              {ord.linhasOrdenadas.map((t) => {
                const extra = parseDadosExtra(t.dados_extra);
                const aberto = expandido === t.id;
                return (
                  <Fragment key={t.id}>
                    <tr>
                      <td style={{ ...td, textAlign: "center" }}>
                        {extra.length > 0 && (
                          <button onClick={() => setExpandido(aberto ? null : (t.id ?? null))} title="Ver todos os dados da planilha"
                            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", display: "flex" }}>
                            {aberto ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                          </button>
                        )}
                      </td>
                      <td style={{ ...td, fontWeight: 700, color: "var(--dourado-light)" }}>{t.naab}</td>
                      <td style={td}>{t.nome || "—"}</td>
                      <td style={td}>{t.central || "—"}</td>
                      <td style={td}>{t.raca || "—"}</td>
                      <td style={{ ...td, textAlign: "right" }}>{fmt(t.leite_kg)}</td>
                      <td style={{ ...td, textAlign: "right" }}>{fmt(t.gordura_kg)}</td>
                      <td style={{ ...td, textAlign: "right" }}>{fmt(t.proteina_kg)}</td>
                      <td style={{ ...td, textAlign: "right", fontWeight: 600 }}>{fmt(t.tpi)}</td>
                      <td style={{ ...td, textAlign: "right" }}>{t.nm_dolar == null ? "—" : `$${fmt(t.nm_dolar)}`}</td>
                      <td style={{ ...td, textAlign: "right" }}>{fmt(t.fertilidade_filhas, 1)}</td>
                      <td style={{ ...td, textAlign: "right" }}>{fmt(t.facilidade_parto, 1)}</td>
                      <td style={{ ...td, fontSize: "0.74rem", color: "var(--text-muted)" }}>{[t.fonte, t.rodada_prova].filter(Boolean).join(" · ") || "—"}</td>
                      {podeEditar && (
                        <td style={{ ...td, textAlign: "right", whiteSpace: "nowrap" }}>
                          <button onClick={() => setEditando(t)} title="Editar touro"
                            style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)", marginRight: "0.5rem" }}>
                            <Pencil size={15} />
                          </button>
                          <button onClick={() => remover(t)} title="Excluir touro"
                            style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
                            <Trash2 size={15} />
                          </button>
                        </td>
                      )}
                    </tr>
                    {aberto && (
                      <tr>
                        <td colSpan={podeEditar ? 14 : 13} style={{ padding: "0.6rem 1rem 0.9rem 2.2rem", borderBottom: "1px solid var(--border)", background: "var(--surface)" }}>
                          <p style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "0.4rem" }}>
                            Todos os dados da planilha do fornecedor
                          </p>
                          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(14rem, 1fr))", gap: "0.3rem 1rem" }}>
                            {extra.map(([rotulo, valor], i) => (
                              <div key={i} style={{ fontSize: "0.78rem", display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                                <span style={{ color: "var(--text-muted)" }}>{rotulo}</span>
                                <span style={{ fontWeight: 600 }}>{String(valor)}</span>
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {podeEditar && editando && (
        <FormTouro
          inicial={editando === "novo" ? CAMPO_VAZIO : { ...editando, nome: editando.nome || "", dados_extra: parseDadosExtra(editando.dados_extra) }}
          onSalvar={salvar}
          onCancelar={() => setEditando(null)}
        />
      )}
    </div>
  );
}
