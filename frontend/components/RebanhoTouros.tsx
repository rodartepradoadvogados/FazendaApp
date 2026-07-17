"use client";
import { useEffect, useMemo, useState } from "react";
import { Dna, Search, Warehouse, FlaskConical, Database } from "lucide-react";
import { fetchEstoqueSemen, fetchTouros, fetchAnimais, type Touro } from "@/lib/api";
import type { AnimalRow } from "./AnimalModal";
import { CAMPOS_NUMERICOS, parseDadosExtra } from "./CadastroTouros";
import { TouroDetalheModal } from "./TouroDetalheModal";

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
  display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.65rem 1rem", borderRadius: "8px",
  border: `1px solid ${ativo ? "var(--dourado)" : "var(--border)"}`,
  background: ativo ? "var(--dourado-transp, rgba(197,160,74,0.12))" : "var(--surface-2)",
  color: ativo ? "var(--dourado-light)" : "var(--text)", cursor: "pointer", fontSize: "0.85rem", fontWeight: ativo ? 700 : 400,
});

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

  useEffect(() => {
    fetchEstoqueSemen().then(setEstoque).catch(() => setEstoque([]));
    fetchAnimais({ incluirMachos: true }).then((d) => setMachos(d.filter((a: MachoAnimal) => a.sexo === "M"))).catch(() => {});
  }, []);

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

  const estoqueFiltrado = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return emEstoque;
    return emEstoque.filter((e) => `${e.touro_nome} ${e.codigo || ""} ${e.naab || ""} ${e.central || ""}`.toLowerCase().includes(q));
  }, [emEstoque, busca]);

  const naabFiltrado = useMemo(() => {
    const q = busca.trim().toLowerCase();
    const base = naab ?? [];
    if (!q) return base;
    return base.filter((t) => `${t.nome || ""} ${t.naab} ${t.central || ""} ${t.raca || ""}`.toLowerCase().includes(q));
  }, [naab, busca]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };

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
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr><th>Touro</th><th>Código</th><th>NAAB</th><th>Central</th><th>Tipo</th><th style={{ textAlign: "right" }}>Doses</th><th style={{ textAlign: "right" }}>Valor/dose</th></tr></thead>
                <tbody>
                  {estoqueFiltrado.map((e) => (
                    <tr key={e.id} style={{ cursor: "pointer" }} onClick={() => abrirDetalheEstoque(e)} title="Ver detalhes do touro">
                      <td style={{ fontWeight: 700 }}>{e.touro_nome}</td>
                      <td style={{ fontSize: "0.8rem" }}>{e.codigo || "—"}</td>
                      <td style={{ fontSize: "0.8rem" }}>{e.naab || "—"}</td>
                      <td style={{ fontSize: "0.8rem" }}>{e.central || "—"}</td>
                      <td style={{ fontSize: "0.8rem", textTransform: "capitalize" }}>{e.tipo}</td>
                      <td style={{ textAlign: "right", fontWeight: 600 }}>{e.doses}</td>
                      <td style={{ textAlign: "right" }}>{e.valor_unitario ? `R$ ${fmt(e.valor_unitario, 2)}` : "—"}</td>
                    </tr>
                  ))}
                  {!estoqueFiltrado.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)", textAlign: "center" }}>Nenhum touro em estoque encontrado.</td></tr>}
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
                  <thead><tr><th>NAAB</th><th>Touro</th><th>Central</th><th>Raça</th><th style={{ textAlign: "right" }}>TPI</th><th style={{ textAlign: "right" }}>Leite (kg)</th></tr></thead>
                  <tbody>
                    {naabFiltrado.slice(0, 200).map((t) => (
                      <tr key={t.id ?? t.naab} style={{ cursor: "pointer" }} onClick={() => abrirDetalheNaab(t)} title="Ver detalhes do touro">
                        <td style={{ fontWeight: 700 }}>{t.naab}</td>
                        <td style={{ fontSize: "0.8rem" }}>{t.nome || "—"}</td>
                        <td style={{ fontSize: "0.8rem" }}>{t.central || "—"}</td>
                        <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{t.raca || "—"}</td>
                        <td style={{ textAlign: "right", fontWeight: 600, color: "var(--dourado-light)" }}>{fmt(t.tpi)}</td>
                        <td style={{ textAlign: "right" }}>{fmt(t.leite_kg)}</td>
                      </tr>
                    ))}
                    {!naabFiltrado.length && <tr><td colSpan={6} style={{ color: "var(--text-muted)", textAlign: "center" }}>Nenhum touro do catálogo NAAB encontrado.</td></tr>}
                  </tbody>
                </table>
              )}
              {naab && naabFiltrado.length > 200 && (
                <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Mostrando 200 de {naabFiltrado.length} — refine a busca para ver mais.</p>
              )}
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
    </div>
  );
}
