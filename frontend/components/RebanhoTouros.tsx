"use client";
import { useEffect, useMemo, useState } from "react";
import { Dna, Search, Warehouse, FlaskConical, Database, Pencil, Trash2, X } from "lucide-react";
import {
  fetchEstoqueSemen, fetchTouros, fetchAnimais, atualizarEstoqueSemen, atualizarTouro, excluirEstoqueSemen,
  fetchProvaMediaSemen, type Touro, type TouroIn, type ProvaMediaSemen, type ProvaMediaCampos,
} from "@/lib/api";
import type { AnimalRow } from "./AnimalModal";
import { CAMPOS_NUMERICOS, parseDadosExtra, FormTouro, CAMPO_VAZIO } from "./CadastroTouros";
import { TouroDetalheModal } from "./TouroDetalheModal";
import { useOrdenacao, ThOrdenavel } from "./Ordenavel";
import { usePaginacao, Paginacao } from "./Paginacao";
import { casaBusca } from "@/lib/busca";

type EstoqueSemenItem = {
  id: number; touro_nome: string; codigo?: string | null; naab?: string | null;
  central?: string | null; tipo: string; doses: number; valor_unitario?: number | null;
  local_armazenamento?: string | null; observacao?: string | null; ativo: boolean;
};

type Fonte = "fazenda" | "semen";
type OrigemSemen = "estoque" | "naab";
type MachoAnimal = AnimalRow & { sexo?: string | null; nome?: string | null };

const fmt = (v?: number | null, dec = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: dec, maximumFractionDigits: dec });

const cardBtn = (ativo: boolean): React.CSSProperties => ({
  display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.65rem 1rem", borderRadius: "var(--r-sm)",
  border: `1px solid ${ativo ? "var(--dourado)" : "var(--border)"}`,
  background: ativo ? "var(--dourado-transp, rgba(197,160,74,0.12))" : "var(--surface-2)",
  color: ativo ? "var(--dourado-light)" : "var(--text)", cursor: "pointer", fontSize: "0.85rem", fontWeight: ativo ? 700 : 400,
});

const inputStyle: React.CSSProperties = { width: "100%", padding: "0.45rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem", display: "block" };

/** Editar um touro do estoque de sêmen direto em Rebanho > Touros (mesmos
 * campos do cadastro em Configurações > Cadastro > Estoque de sêmen). */
function FormEstoqueSemenEdit({ inicial, onSalvar, onCancelar }: { inicial: EstoqueSemenItem; onSalvar: (d: EstoqueSemenItem) => Promise<void>; onCancelar: () => void }) {
  const [dados, setDados] = useState(inicial);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");
  const set = (chave: keyof EstoqueSemenItem, valor: any) => setDados((d) => ({ ...d, [chave]: valor }));

  async function salvar() {
    if (!dados.touro_nome.trim()) { setErro("Nome do touro é obrigatório."); return; }
    setErro(""); setSalvando(true);
    try { await onSalvar(dados); } catch (e: any) { setErro(e.message || "Falha ao salvar"); } finally { setSalvando(false); }
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "flex-start", justifyContent: "center", zIndex: 200, overflowY: "auto", padding: "2rem 1rem" }}>
      <div style={{ background: "var(--bg)", borderRadius: "var(--r-sm)", padding: "1.5rem", width: "100%", maxWidth: "32rem", border: "1px solid var(--border)" }}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold flex items-center gap-2"><FlaskConical size={18} style={{ color: "var(--dourado)" }} /> Editar touro em estoque</h3>
          <button onClick={onCancelar} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}><X size={18} /></button>
        </div>
        {erro && <p style={{ color: "var(--vermelho, #d33)", fontSize: "0.85rem", marginBottom: "0.6rem" }}>{erro}</p>}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div><label style={labelStyle}>Touro</label><input style={inputStyle} value={dados.touro_nome} onChange={(e) => set("touro_nome", e.target.value)} /></div>
          <div><label style={labelStyle}>Código</label><input style={inputStyle} value={dados.codigo || ""} onChange={(e) => set("codigo", e.target.value)} /></div>
          <div><label style={labelStyle}>NAAB</label><input style={inputStyle} value={dados.naab || ""} onChange={(e) => set("naab", e.target.value)} /></div>
          <div><label style={labelStyle}>Central</label><input style={inputStyle} value={dados.central || ""} onChange={(e) => set("central", e.target.value)} /></div>
          <div>
            <label style={labelStyle}>Tipo</label>
            <select style={inputStyle} value={dados.tipo} onChange={(e) => set("tipo", e.target.value)}>
              <option value="convencional">Convencional</option>
              <option value="sexado">Sexado</option>
              <option value="fazenda">Touro da fazenda (monta natural)</option>
            </select>
          </div>
          <div><label style={labelStyle}>Doses</label><input type="number" min={0} style={inputStyle} value={dados.doses} onChange={(e) => set("doses", Number(e.target.value) || 0)} /></div>
          <div><label style={labelStyle}>Valor/dose</label><input type="number" step="any" min={0} style={inputStyle} value={dados.valor_unitario ?? ""} onChange={(e) => set("valor_unitario", e.target.value === "" ? null : Number(e.target.value))} /></div>
          <div><label style={labelStyle}>Local de armazenamento</label><input style={inputStyle} value={dados.local_armazenamento || ""} onChange={(e) => set("local_armazenamento", e.target.value)} /></div>
        </div>
        <div style={{ marginBottom: "0.8rem" }}>
          <label style={labelStyle}>Observação</label>
          <textarea style={{ ...inputStyle, minHeight: "3rem" }} value={dados.observacao || ""} onChange={(e) => set("observacao", e.target.value)} />
        </div>
        <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", marginBottom: "1rem", cursor: "pointer" }}>
          <input type="checkbox" checked={dados.ativo} onChange={(e) => set("ativo", e.target.checked)} /> Ativo
        </label>
        <div className="flex items-center justify-end gap-2">
          <button onClick={onCancelar} className="btn-secondary">Cancelar</button>
          <button onClick={salvar} disabled={salvando} className="btn-primary">{salvando ? "Salvando..." : "Salvar"}</button>
        </div>
      </div>
    </div>
  );
}

/**
 * Rebanho > Touros — filtro em cascata para consultar os touros disponíveis:
 * 1) fonte (touros da fazenda × sêmen); 2) se fazenda, qual touro (Frederico/
 * Sevaverde); se sêmen, estoque cadastrado × banco de dados NAAB.
 *
 * Clique numa linha abre a ficha do animal quando ele existe no cadastro de
 * Animal (só touros da fazenda, casados por nome com sexo="M"); sêmen em
 * estoque e o catálogo NAAB não têm ficha de animal — abrem um modal com os
 * dados cadastrados sobre o touro.
 */
export default function RebanhoTouros({ onAbrirFicha }: { onAbrirFicha?: (numero: string) => void } = {}) {
  const [fonte, setFonte] = useState<Fonte | null>(null);
  const [origemSemen, setOrigemSemen] = useState<OrigemSemen | null>(null);
  const [estoque, setEstoque] = useState<EstoqueSemenItem[] | null>(null);
  const [naab, setNaab] = useState<Touro[] | null>(null);
  const [erroNaab, setErroNaab] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [tourosFazenda, setTourosFazenda] = useState<string[]>([]);
  const [machos, setMachos] = useState<MachoAnimal[]>([]);
  const [detalhe, setDetalhe] = useState<{ titulo: string; campos: [string, string][] } | null>(null);
  const [editEstoque, setEditEstoque] = useState<EstoqueSemenItem | null>(null);
  const [editNaab, setEditNaab] = useState<Touro | null>(null);
  const [provaMedia, setProvaMedia] = useState<ProvaMediaSemen | null>(null);
  const [provaErro, setProvaErro] = useState<string | null>(null);
  const [provaDe, setProvaDe] = useState("");
  const [provaAte, setProvaAte] = useState("");

  useEffect(() => {
    fetchEstoqueSemen().then(setEstoque).catch(() => setEstoque([]));
    fetchAnimais({ incluirMachos: true }).then((d) => setMachos(d.filter((a: MachoAnimal) => a.sexo === "M"))).catch(() => {});
  }, []);

  // Prova média (Quadro 3): só faz sentido olhando o estoque de sêmen (é ele
  // que dá o peso/doses) — recalcula ao entrar na sub-aba ou trocar o
  // período dos serviços considerados.
  useEffect(() => {
    if (origemSemen !== "estoque") return;
    setProvaErro(null);
    fetchProvaMediaSemen(provaDe || undefined, provaAte || undefined)
      .then(setProvaMedia)
      .catch((e: any) => setProvaErro(e.message || "Erro ao calcular a prova média"));
  }, [origemSemen, provaDe, provaAte]);

  const abrirTouroFazenda = (touroNome: string, f: EstoqueSemenItem) => {
    const animal = machos.find((a) => (a.nome || "").trim().toLowerCase() === touroNome.trim().toLowerCase());
    if (animal && onAbrirFicha) { onAbrirFicha(animal.numero); return; }
    setDetalhe({
      titulo: touroNome,
      campos: [
        ["Local de armazenamento", f.local_armazenamento || "—"],
        ["Observação", f.observacao || "—"],
        ["Ativo", f.ativo ? "Sim" : "Não"],
      ],
    });
  };

  const abrirDetalheEstoque = (e: EstoqueSemenItem) => {
    setDetalhe({
      titulo: e.touro_nome,
      campos: [
        ["Código", e.codigo || "—"],
        ["NAAB", e.naab || "—"],
        ["Central", e.central || "—"],
        ["Tipo", e.tipo],
        ["Doses", String(e.doses)],
        ["Valor/dose", e.valor_unitario ? `R$ ${fmt(e.valor_unitario, 2)}` : "—"],
        ["Local de armazenamento", e.local_armazenamento || "—"],
        ["Observação", e.observacao || "—"],
        ["Ativo", e.ativo ? "Sim" : "Não"],
      ],
    });
  };

  const abrirDetalheNaab = (t: Touro) => {
    const fixos: [string, string][] = [
      ["NAAB", t.naab],
      ["Nome completo", t.nome_completo || "—"],
      ["Central", t.central || "—"],
      ["Raça", t.raca || "—"],
      ...CAMPOS_NUMERICOS.map(({ chave, label }): [string, string] => [label, fmt(t[chave] as number | null)]),
      ["Fonte", t.fonte || "—"],
      ["Rodada da prova", t.rodada_prova || "—"],
      ["Observação", t.observacao || "—"],
    ];
    // A planilha do fornecedor (dados_extra) às vezes repete rótulos já
    // modelados acima (ex.: "TPI", "Raça") — evita duplicar a mesma
    // informação (e as chaves React repetidas que isso causaria).
    const rotulosFixos = new Set(fixos.map(([rotulo]) => rotulo.trim().toLowerCase()));
    const extras = parseDadosExtra(t.dados_extra).filter(([rotulo]) => !rotulosFixos.has(rotulo.trim().toLowerCase()));
    setDetalhe({ titulo: t.nome || t.naab, campos: [...fixos, ...extras] });
  };

  useEffect(() => {
    if (origemSemen === "naab" && naab === null) {
      setErroNaab(null);
      fetchTouros().then(setNaab).catch((e: any) => { setNaab([]); setErroNaab(e.message || "Erro ao carregar o catálogo NAAB"); });
    }
  }, [origemSemen, naab]);

  const fazenda = useMemo(() => (estoque ?? []).filter((e) => e.tipo === "fazenda"), [estoque]);
  const emEstoque = useMemo(() => (estoque ?? []).filter((e) => e.tipo !== "fazenda"), [estoque]);

  const nomesFazenda = useMemo(() => Array.from(new Set(fazenda.map((f) => f.touro_nome))).sort(), [fazenda]);

  const escolherFonte = (f: Fonte) => {
    setFonte(f);
    setOrigemSemen(null);
    setTourosFazenda([]);
    setBusca("");
  };

  const toggleTouroFazenda = (nome: string) =>
    setTourosFazenda((p) => (p.includes(nome) ? p.filter((x) => x !== nome) : [...p, nome]));

  const fazendaFiltrada = tourosFazenda.length ? fazenda.filter((f) => tourosFazenda.includes(f.touro_nome)) : fazenda;

  const estoqueFiltrado = useMemo(
    () => emEstoque.filter((e) => casaBusca(`${e.touro_nome} ${e.codigo || ""} ${e.naab || ""} ${e.central || ""}`, busca)),
    [emEstoque, busca]
  );

  const naabFiltrado = useMemo(
    () => (naab ?? []).filter((t) => casaBusca(`${t.nome || ""} ${t.naab} ${t.central || ""} ${t.raca || ""}`, busca)),
    [naab, busca]
  );

  const ordEstoque = useOrdenacao(estoqueFiltrado);
  const ordNaab = useOrdenacao(naabFiltrado);
  const pagNaab = usePaginacao(ordNaab.linhasOrdenadas);

  const [erroExclusao, setErroExclusao] = useState("");
  const excluirDoEstoque = async (e: EstoqueSemenItem) => {
    if (!window.confirm(`Excluir "${e.touro_nome}" do estoque de sêmen? Esta ação não pode ser desfeita.`)) return;
    setErroExclusao("");
    try {
      await excluirEstoqueSemen(e.id);
      setEstoque((prev) => (prev ?? []).filter((x) => x.id !== e.id));
    } catch (err: any) {
      setErroExclusao(err.message || "Erro ao excluir sêmen do estoque");
    }
  };

  const salvarEdicaoEstoque = async (d: EstoqueSemenItem) => {
    const atualizado = await atualizarEstoqueSemen(d.id, {
      touro_nome: d.touro_nome.trim(), codigo: d.codigo || undefined, naab: d.naab || undefined,
      central: d.central || undefined, tipo: d.tipo, doses: d.doses, valor_unitario: d.valor_unitario ?? undefined,
      local_armazenamento: d.local_armazenamento || undefined, observacao: d.observacao || undefined, ativo: d.ativo,
    });
    setEstoque((prev) => (prev ?? []).map((e) => (e.id === atualizado.id ? atualizado : e)));
    setEditEstoque(null);
  };

  const salvarEdicaoNaab = async (d: TouroIn) => {
    if (!editNaab?.id) return;
    const atualizado = await atualizarTouro(editNaab.id, d);
    setNaab((prev) => (prev ?? []).map((t) => (t.id === atualizado.id ? atualizado : t)));
    setEditNaab(null);
  };

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Dna size={22} style={{ color: "var(--dourado)" }} /> Touros</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Filtre os touros disponíveis para monta natural ou inseminação: da fazenda, em estoque de sêmen, ou no banco de dados NAAB.</p>
      </div>

      <div className="card mb-4">
        <div className="card-header mb-3">1. Fonte do touro</div>
        <div className="flex flex-wrap gap-3">
          <button style={cardBtn(fonte === "fazenda")} onClick={() => escolherFonte("fazenda")}>
            <Warehouse size={16} /> Touros da fazenda (monta natural)
          </button>
          <button style={cardBtn(fonte === "semen")} onClick={() => escolherFonte("semen")}>
            <FlaskConical size={16} /> Sêmen
          </button>
        </div>
      </div>

      {fonte === "fazenda" && (
        <div className="card mb-4">
          <div className="card-header mb-3">2. Touro(s) da fazenda</div>
          {!estoque && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
          {estoque && !nomesFazenda.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum touro da fazenda cadastrado ainda — cadastre em Configurações &gt; Cadastro &gt; Estoque de sêmen (tipo "fazenda").</p>}
          <div className="flex flex-wrap gap-2 mb-3">
            {nomesFazenda.map((nome) => (
              <button key={nome} style={cardBtn(tourosFazenda.includes(nome))} onClick={() => toggleTouroFazenda(nome)}>
                {nome}
              </button>
            ))}
          </div>
          {!!fazendaFiltrada.length && (
            <div className="overflow-x-auto">
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr><th>Touro</th><th>Local</th><th>Observação</th><th>Ativo</th></tr></thead>
                <tbody>
                  {fazendaFiltrada.map((f) => (
                    <tr key={f.id} style={{ cursor: "pointer" }} onClick={() => abrirTouroFazenda(f.touro_nome, f)} title="Ver ficha/detalhes do touro">
                      <td style={{ fontWeight: 700 }}>{f.touro_nome}</td>
                      <td style={{ fontSize: "0.8rem" }}>{f.local_armazenamento || "—"}</td>
                      <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{f.observacao || "—"}</td>
                      <td>{f.ativo ? "Sim" : "Não"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {fonte === "semen" && (
        <div className="card mb-4">
          <div className="card-header mb-3">2. Origem do sêmen</div>
          <div className="flex flex-wrap gap-3 mb-3">
            <button style={cardBtn(origemSemen === "estoque")} onClick={() => { setOrigemSemen("estoque"); setBusca(""); }}>
              <Warehouse size={16} /> Touros em estoque
            </button>
            <button style={cardBtn(origemSemen === "naab")} onClick={() => { setOrigemSemen("naab"); setBusca(""); }}>
              <Database size={16} /> Banco de dados NAAB
            </button>
          </div>

          {origemSemen && (
            <div className="mb-3" style={{ position: "relative", maxWidth: 320 }}>
              <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
              <input style={{ ...selStyle, paddingLeft: "1.6rem", width: "100%" }} value={busca} onChange={(e) => setBusca(e.target.value)}
                placeholder={origemSemen === "estoque" ? "Buscar touro, código, NAAB…" : "Buscar touro, NAAB, central, raça…"} />
            </div>
          )}

          {origemSemen === "estoque" && (
            <div className="overflow-x-auto">
              {erroExclusao && <p style={{ color: "var(--vermelho, #d33)", fontSize: "0.85rem", marginBottom: "0.6rem" }}>{erroExclusao}</p>}
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead>
                  <tr>
                    <ThOrdenavel label="Touro" campo="touro_nome" coluna={ordEstoque.coluna} dir={ordEstoque.dir} ordenar={ordEstoque.ordenar} />
                    <ThOrdenavel label="Código" campo="codigo" coluna={ordEstoque.coluna} dir={ordEstoque.dir} ordenar={ordEstoque.ordenar} />
                    <ThOrdenavel label="NAAB" campo="naab" coluna={ordEstoque.coluna} dir={ordEstoque.dir} ordenar={ordEstoque.ordenar} />
                    <ThOrdenavel label="Central" campo="central" coluna={ordEstoque.coluna} dir={ordEstoque.dir} ordenar={ordEstoque.ordenar} />
                    <ThOrdenavel label="Tipo" campo="tipo" coluna={ordEstoque.coluna} dir={ordEstoque.dir} ordenar={ordEstoque.ordenar} />
                    <ThOrdenavel label="Doses" campo="doses" coluna={ordEstoque.coluna} dir={ordEstoque.dir} ordenar={ordEstoque.ordenar} alinhar="right" />
                    <ThOrdenavel label="Valor/dose" campo="valor_unitario" coluna={ordEstoque.coluna} dir={ordEstoque.dir} ordenar={ordEstoque.ordenar} alinhar="right" />
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {ordEstoque.linhasOrdenadas.map((e) => (
                    <tr key={e.id} style={{ cursor: "pointer" }} onClick={() => abrirDetalheEstoque(e)} title="Ver detalhes do touro">
                      <td style={{ fontWeight: 700 }}>{e.touro_nome}</td>
                      <td style={{ fontSize: "0.8rem" }}>{e.codigo || "—"}</td>
                      <td style={{ fontSize: "0.8rem" }}>{e.naab || "—"}</td>
                      <td style={{ fontSize: "0.8rem" }}>{e.central || "—"}</td>
                      <td style={{ fontSize: "0.8rem", textTransform: "capitalize" }}>{e.tipo}</td>
                      <td style={{ textAlign: "right", fontWeight: 600 }}>{e.doses}</td>
                      <td style={{ textAlign: "right" }}>{e.valor_unitario ? `R$ ${fmt(e.valor_unitario, 2)}` : "—"}</td>
                      <td style={{ textAlign: "right" }}>
                        <button onClick={(ev) => { ev.stopPropagation(); setEditEstoque(e); }} title="Editar touro"
                          style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
                          <Pencil size={14} />
                        </button>
                        <button onClick={(ev) => { ev.stopPropagation(); excluirDoEstoque(e); }} title="Excluir do estoque"
                          style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--red, #d33)", marginLeft: "0.4rem" }}>
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!estoqueFiltrado.length && <tr><td colSpan={8} style={{ color: "var(--text-muted)", textAlign: "center" }}>Nenhum touro em estoque encontrado.</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          {origemSemen === "naab" && (
            <div className="overflow-x-auto">
              {erroNaab && <p style={{ color: "var(--red)" }}>Não foi possível carregar o catálogo NAAB: {erroNaab}. Se você não tem acesso ao módulo "Configurações", peça a um administrador para verificar suas permissões.</p>}
              {!naab && !erroNaab && <p style={{ color: "var(--text-muted)" }}>Carregando catálogo NAAB…</p>}
              {naab && (
                <table className="fazenda-table" style={{ margin: 0 }}>
                  <thead>
                    <tr>
                      <ThOrdenavel label="NAAB" campo="naab" coluna={ordNaab.coluna} dir={ordNaab.dir} ordenar={ordNaab.ordenar} />
                      <ThOrdenavel label="Touro" campo="nome" coluna={ordNaab.coluna} dir={ordNaab.dir} ordenar={ordNaab.ordenar} />
                      <ThOrdenavel label="Central" campo="central" coluna={ordNaab.coluna} dir={ordNaab.dir} ordenar={ordNaab.ordenar} />
                      <ThOrdenavel label="Raça" campo="raca" coluna={ordNaab.coluna} dir={ordNaab.dir} ordenar={ordNaab.ordenar} />
                      <ThOrdenavel label="TPI" campo="tpi" coluna={ordNaab.coluna} dir={ordNaab.dir} ordenar={ordNaab.ordenar} alinhar="right" />
                      <ThOrdenavel label="Leite (kg)" campo="leite_kg" coluna={ordNaab.coluna} dir={ordNaab.dir} ordenar={ordNaab.ordenar} alinhar="right" />
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagNaab.linhasPagina.map((t) => (
                      <tr key={t.id ?? t.naab} style={{ cursor: "pointer" }} onClick={() => abrirDetalheNaab(t)} title="Ver detalhes do touro">
                        <td style={{ fontWeight: 700 }}>{t.naab}</td>
                        <td style={{ fontSize: "0.8rem" }}>{t.nome || "—"}</td>
                        <td style={{ fontSize: "0.8rem" }}>{t.central || "—"}</td>
                        <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{t.raca || "—"}</td>
                        <td style={{ textAlign: "right", fontWeight: 600, color: "var(--dourado-light)" }}>{fmt(t.tpi)}</td>
                        <td style={{ textAlign: "right" }}>{fmt(t.leite_kg)}</td>
                        <td style={{ textAlign: "right" }}>
                          <button onClick={(ev) => { ev.stopPropagation(); setEditNaab(t); }} title="Editar touro"
                            style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)" }}>
                            <Pencil size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                    {!naabFiltrado.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)", textAlign: "center" }}>Nenhum touro do catálogo NAAB encontrado.</td></tr>}
                  </tbody>
                </table>
              )}
              {naab && (
                <Paginacao pagina={pagNaab.pagina} totalPaginas={pagNaab.totalPaginas} totalLinhas={pagNaab.totalLinhas}
                  tamanhoPagina={pagNaab.tamanhoPagina} onMudarPagina={pagNaab.setPagina} onMudarTamanho={pagNaab.setTamanhoPagina} />
              )}
            </div>
          )}
        </div>
      )}

      {fonte === "semen" && origemSemen === "estoque" && (
        <div className="card mb-4">
          <div className="card-header mb-3">3. Prova média — automático</div>
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.9rem" }}>
            Média ponderada dos indicadores de prova de cada touro pela quantidade de doses de sêmen — soma(indicador × doses) ÷ soma(doses).
            É a mesma lógica de índice ponderado que provas genéticas oficiais já usam (ex.: o PTI combina produção e tipo numa razão fixa entre eles);
            aqui quem pondera é a quantidade de sêmen, não uma razão fixa. Um touro sem determinado indicador não entra no cálculo
            daquele indicador específico — não puxa a média do grupo para baixo.
          </p>
          <div className="grid grid-cols-2 gap-3 mb-4" style={{ maxWidth: 420 }}>
            <div><label style={labelStyle}>Serviços de (data)</label><input type="date" style={inputStyle} value={provaDe} onChange={(e) => setProvaDe(e.target.value)} /></div>
            <div><label style={labelStyle}>Serviços até (data)</label><input type="date" style={inputStyle} value={provaAte} onChange={(e) => setProvaAte(e.target.value)} /></div>
          </div>
          {provaErro && <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{provaErro}</p>}
          {!provaMedia && !provaErro && <p style={{ color: "var(--text-muted)" }}>Calculando…</p>}
          {provaMedia && (
            <div className="overflow-x-auto">
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead>
                  <tr>
                    <th>Indicador</th>
                    <th style={{ textAlign: "right" }}>Prova média do botijão (fazenda toda)</th>
                    <th style={{ textAlign: "right" }}>Prova média das doses usadas nos serviços</th>
                  </tr>
                </thead>
                <tbody>
                  {CAMPOS_NUMERICOS.map(({ chave, label }) => (
                    <tr key={chave}>
                      <td style={{ fontSize: "0.82rem" }}>{label}</td>
                      <td style={{ textAlign: "right", fontWeight: 600 }}>{fmt(provaMedia.botijao.prova[chave as keyof ProvaMediaCampos], 2)}</td>
                      <td style={{ textAlign: "right", fontWeight: 600, color: "var(--dourado-light)" }}>{fmt(provaMedia.servicos_periodo.prova[chave as keyof ProvaMediaCampos], 2)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>Doses / touros considerados</td>
                    <td style={{ textAlign: "right", fontSize: "0.76rem", color: "var(--text-muted)" }}>
                      {provaMedia.botijao.total_doses} dose(s) · {provaMedia.botijao.touros_considerados} touro(s)
                    </td>
                    <td style={{ textAlign: "right", fontSize: "0.76rem", color: "var(--text-muted)" }}>
                      {provaMedia.servicos_periodo.total_doses} dose(s) · {provaMedia.servicos_periodo.touros_considerados} touro(s)
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>
      )}

      {detalhe && (
        <TouroDetalheModal
          titulo={detalhe.titulo}
          campos={detalhe.campos}
          onFechar={() => setDetalhe(null)}
          nota="Este touro não tem ficha de animal cadastrada no rebanho — os dados acima são os únicos registrados sobre ele."
        />
      )}

      {editEstoque && (
        <FormEstoqueSemenEdit inicial={editEstoque} onSalvar={salvarEdicaoEstoque} onCancelar={() => setEditEstoque(null)} />
      )}

      {editNaab && (
        <FormTouro
          inicial={{ ...CAMPO_VAZIO, ...editNaab, nome: editNaab.nome || "", dados_extra: parseDadosExtra(editNaab.dados_extra) }}
          onSalvar={salvarEdicaoNaab}
          onCancelar={() => setEditNaab(null)}
        />
      )}
    </div>
  );
}
