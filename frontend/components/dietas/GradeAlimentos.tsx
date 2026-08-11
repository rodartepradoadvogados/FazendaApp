"use client";
// Etapa 1 do wizard — grade de ingredientes da dieta. Cabeçalho e 1ª coluna
// (nome) ficam fixos ao rolar (ver .sticky-* abaixo) porque a grade tem ~15
// colunas visíveis e pode chegar a 60 ingredientes (limite do backend).
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, Info, Library, Plus, Save, Trash2, Upload } from "lucide-react";
import {
  CAMPOS_GRADE_PRINCIPAL, CATEGORIAS_NASEM, CategoriaNasem, EntradaBiblioteca, GRUPOS_CAMPOS_NUTRICIONAIS,
  ItemGrade, ROTULOS_CAMPOS_NUTRICIONAIS, TemplatesResponse, itemGradeDaBiblioteca, itemGradeVazio,
  listarAlimentos, listarTemplates, salvarAlimentoNaBiblioteca,
} from "@/lib/dietas";
import { ImportarAlimentoModal } from "@/components/dietas/ImportarAlimentoModal";

const inputCel: React.CSSProperties = {
  width: "4.6rem", padding: "0.3rem 0.35rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)",
  background: "var(--surface)", color: "var(--text)", fontSize: "0.78rem",
};
const th: React.CSSProperties = {
  padding: "0.5rem 0.6rem", textAlign: "left", color: "var(--thead-fg)", fontSize: "0.66rem", fontWeight: 700,
  textTransform: "uppercase", letterSpacing: "0.08em", whiteSpace: "nowrap", background: "var(--thead-bg)",
  position: "sticky", top: 0, zIndex: 2, borderBottom: "1px solid var(--border-strong, var(--border))",
};
const td: React.CSSProperties = { padding: "0.35rem 0.6rem", borderBottom: "1px solid var(--border)", whiteSpace: "nowrap" };

export function GradeAlimentos({ itens, onChange }: { itens: ItemGrade[]; onChange: (itens: ItemGrade[]) => void }) {
  const [templates, setTemplates] = useState<TemplatesResponse | null>(null);
  const [biblioteca, setBiblioteca] = useState<EntradaBiblioteca[] | null>(null);
  const [importarAberto, setImportarAberto] = useState(false);
  const [bibliotecaAberta, setBibliotecaAberta] = useState(false);
  const [drawerIdx, setDrawerIdx] = useState<number | null>(null);

  useEffect(() => { listarTemplates().then(setTemplates).catch(() => {}); }, []);
  useEffect(() => { if (bibliotecaAberta && !biblioteca) listarAlimentos().then((r) => setBiblioteca(r.biblioteca)).catch(() => {}); }, [bibliotecaAberta, biblioteca]);

  function atualizarItem(idx: number, patch: Partial<ItemGrade>) {
    onChange(itens.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  function atualizarCampoNumerico(idx: number, campo: keyof ItemGrade, valorTexto: string) {
    const valor = valorTexto === "" ? null : Number(valorTexto);
    const it = itens[idx];
    const editados = new Set(it.campos_editados || []);
    editados.add(campo as string);
    atualizarItem(idx, { [campo]: valor, campos_editados: Array.from(editados) } as Partial<ItemGrade>);
  }

  function trocarCategoria(idx: number, categoria: CategoriaNasem) {
    const it = itens[idx];
    const editados = new Set(it.campos_editados || []);
    const template = templates?.categorias[categoria] || {};
    const patch: Partial<ItemGrade> = { categoria_nasem: categoria };
    for (const [campo, valor] of Object.entries(template)) {
      if (!editados.has(campo)) (patch as any)[campo] = valor;
    }
    atualizarItem(idx, patch);
  }

  function adicionarLinhaManual() {
    const categoria: CategoriaNasem = "Outros";
    const item = itemGradeVazio(categoria);
    const template = templates?.categorias[categoria];
    if (template) Object.assign(item, template);
    onChange([...itens, item]);
  }

  function adicionarDaBiblioteca(e: EntradaBiblioteca) {
    onChange([...itens, itemGradeDaBiblioteca(e)]);
  }

  function removerLinha(idx: number) {
    onChange(itens.filter((_, i) => i !== idx));
    if (drawerIdx === idx) setDrawerIdx(null);
  }

  function importarResolvidos(novos: ItemGrade[]) {
    onChange([...itens, ...novos]);
  }

  async function salvarNaBiblioteca(idx: number) {
    const it = itens[idx];
    if (!confirm(`Salvar "${it.nome}" na biblioteca de referência da fazenda?`)) return;
    try {
      const valores: Record<string, number | null> = {};
      for (const grupo of GRUPOS_CAMPOS_NUTRICIONAIS) for (const campo of grupo.campos) valores[campo] = (it as any)[campo] ?? null;
      await salvarAlimentoNaBiblioteca({
        alimento_id: it.alimento_id ?? null, nome: it.nome, categoria_nasem: it.categoria_nasem, conc_pct: it.conc_pct, valores,
      });
      alert("Salvo na biblioteca.");
    } catch (e: any) {
      alert(e.message);
    }
  }

  const somaProporcao = useMemo(() => itens.reduce((s, i) => s + (i.proporcao_ms_pct || 0), 0), [itens]);

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.6rem", marginBottom: "0.8rem", alignItems: "center" }}>
        <button type="button" className="btn-secondary" onClick={() => setImportarAberto(true)}>
          <Upload size={14} /> Importar do cadastro
        </button>
        <button type="button" className="btn-secondary" onClick={adicionarLinhaManual}>
          <Plus size={14} /> Adicionar linha manual
        </button>
        <button type="button" className="btn-secondary" onClick={() => setBibliotecaAberta((v) => !v)}>
          <Library size={14} /> Biblioteca de referência {bibliotecaAberta ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
        <span style={{ marginLeft: "auto", fontSize: "0.8rem", color: somaProporcao > 100.5 || somaProporcao < 99.5 ? "var(--amber)" : "var(--text-muted)" }}>
          Soma da proporção na MS: <strong>{somaProporcao.toFixed(1)}%</strong>{Math.abs(somaProporcao - 100) > 0.5 && itens.length > 0 ? " (ajuste para 100%)" : ""}
        </span>
      </div>

      {bibliotecaAberta && (
        <div className="card" style={{ marginBottom: "0.8rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem", marginBottom: "0.6rem" }}>
            <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-muted)" }}>
              Biblioteca padrão CowData + os alimentos próprios da fazenda — clique em "+" para adicionar direto na grade, sem cadastro nenhum.
            </p>
            <Link href="/dietas/biblioteca" style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.76rem", color: "var(--gold-deep)", whiteSpace: "nowrap" }}>
              Gerenciar biblioteca <ExternalLink size={12} />
            </Link>
          </div>
          {biblioteca === null && <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Carregando…</p>}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(13rem, 1fr))", gap: "0.5rem" }}>
            {(biblioteca || []).map((e) => (
              <button
                key={e.id} type="button" onClick={() => adicionarDaBiblioteca(e)}
                title={e.inclusao_min_pct != null || e.inclusao_max_pct != null
                  ? `Inclusão sugerida na dieta: ${e.inclusao_min_pct ?? "?"}–${e.inclusao_max_pct ?? "?"}% da MS`
                  : undefined}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
                  padding: "0.5rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)",
                  background: "var(--surface-2)", color: "var(--text)", fontSize: "0.78rem", cursor: "pointer", textAlign: "left",
                }}
              >
                <span>
                  {e.nome} {e.eh_mestre && <span style={{ color: "var(--gold-deep)", fontSize: "0.65rem", fontWeight: 700 }}>CowData</span>}
                  <br /><span style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>
                    {e.categoria_nasem}
                    {(e.inclusao_min_pct != null || e.inclusao_max_pct != null) && ` · inclusão ${e.inclusao_min_pct ?? "?"}–${e.inclusao_max_pct ?? "?"}%`}
                  </span>
                </span>
                <Plus size={14} />
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 0, maxHeight: "60vh", overflow: "auto", position: "relative" }}>
        <table style={{ borderCollapse: "separate", borderSpacing: 0, fontSize: "0.8rem", minWidth: "62rem" }}>
          <thead>
            <tr>
              <th style={{ ...th, position: "sticky", left: 0, top: 0, zIndex: 3, minWidth: "12rem" }}>Ingrediente</th>
              <th style={{ ...th, minWidth: "9rem" }}>Categoria</th>
              <th style={th}>Conc. %</th>
              <th style={th}>Prop. MS %</th>
              {CAMPOS_GRADE_PRINCIPAL.map((c) => <th key={c} style={th}>{ROTULOS_CAMPOS_NUTRICIONAIS[c]}</th>)}
              <th style={{ ...th, minWidth: "7rem" }}>Origem</th>
              <th style={th}></th>
            </tr>
          </thead>
          <tbody>
            {itens.length === 0 && (
              <tr><td colSpan={7 + CAMPOS_GRADE_PRINCIPAL.length} style={{ padding: "1.5rem" }}>
                <div className="empty-state">Nenhum ingrediente ainda. Importe do cadastro, adicione uma linha manual ou use a biblioteca de referência acima.</div>
              </td></tr>
            )}
            {itens.map((it, idx) => (
              <tr key={idx}>
                <td style={{ ...td, position: "sticky", left: 0, zIndex: 1, background: "var(--surface)", minWidth: "12rem" }}>
                  <button type="button" onClick={() => setDrawerIdx(idx)} title="Ver/editar todos os campos nutricionais"
                    style={{ background: "none", border: "none", padding: 0, color: "var(--text)", fontWeight: 600, cursor: "pointer", textAlign: "left" }}>
                    {it.nome || <span style={{ color: "var(--text-muted)" }}>(sem nome)</span>}
                  </button>
                </td>
                <td style={td}>
                  <select value={it.categoria_nasem} onChange={(e) => trocarCategoria(idx, e.target.value as CategoriaNasem)}
                    style={{ ...inputCel, width: "8.6rem" }}>
                    {CATEGORIAS_NASEM.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </td>
                <td style={td}>
                  <input type="number" step="1" min={0} max={100} value={it.conc_pct} onChange={(e) => atualizarItem(idx, { conc_pct: Number(e.target.value) })} style={inputCel} />
                </td>
                <td style={td}>
                  <input
                    type="number" step="0.1" min={0} max={100} value={it.proporcao_ms_pct}
                    onChange={(e) => atualizarItem(idx, { proporcao_ms_pct: Number(e.target.value) })}
                    title={it.inclusao_min_pct != null || it.inclusao_max_pct != null
                      ? `Inclusão sugerida da biblioteca: ${it.inclusao_min_pct ?? "?"}–${it.inclusao_max_pct ?? "?"}% da MS da dieta`
                      : undefined}
                    style={inputCel}
                  />
                  {(it.inclusao_min_pct != null || it.inclusao_max_pct != null) && (
                    <div style={{ fontSize: "0.62rem", color: "var(--text-muted)", marginTop: "0.1rem", whiteSpace: "nowrap" }}>
                      sugerido {it.inclusao_min_pct ?? "?"}–{it.inclusao_max_pct ?? "?"}%
                    </div>
                  )}
                </td>
                {CAMPOS_GRADE_PRINCIPAL.map((campo) => (
                  <td key={campo} style={td}>
                    <input
                      type="number" step="0.01" value={(it as any)[campo] ?? ""}
                      onChange={(e) => atualizarCampoNumerico(idx, campo, e.target.value)}
                      placeholder="—"
                      style={{ ...inputCel, borderStyle: (it.campos_editados || []).includes(campo) ? "solid" : "dashed", opacity: (it as any)[campo] == null ? 0.6 : 1 }}
                    />
                  </td>
                ))}
                <td style={{ ...td, fontSize: "0.72rem", color: "var(--text-muted)" }}>{it.origem}</td>
                <td style={td}>
                  <div style={{ display: "flex", gap: "0.25rem" }}>
                    <button type="button" title="Salvar na biblioteca" onClick={() => salvarNaBiblioteca(idx)} className="btn-ghost" style={{ padding: "0.25rem 0.4rem" }}>
                      <Save size={13} />
                    </button>
                    <button type="button" title="Remover" onClick={() => removerLinha(idx)} className="btn-ghost" style={{ padding: "0.25rem 0.4rem", color: "var(--red)" }}>
                      <Trash2 size={13} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="alert-critico" style={{ marginTop: "0.8rem", background: "color-mix(in srgb, var(--amber) 14%, transparent)", borderColor: "var(--amber)", color: "var(--text)" }}>
        <Info size={15} style={{ flexShrink: 0 }} />
        Cromo, biotina, colina, niacina e betacaroteno não têm valor de exigência na referência usada; ficam disponíveis só como fornecido pela dieta, sem balanço.
      </div>

      {importarAberto && (
        <ImportarAlimentoModal onFechar={() => setImportarAberto(false)} onImportar={(novos) => { importarResolvidos(novos); setImportarAberto(false); }} />
      )}

      {drawerIdx !== null && itens[drawerIdx] && (
        <DrawerDetalheIngrediente
          item={itens[drawerIdx]}
          onFechar={() => setDrawerIdx(null)}
          onAtualizarCampo={(campo, valor) => atualizarCampoNumerico(drawerIdx, campo, valor)}
        />
      )}
    </div>
  );
}

function DrawerDetalheIngrediente({
  item, onFechar, onAtualizarCampo,
}: {
  item: ItemGrade; onFechar: () => void; onAtualizarCampo: (campo: keyof ItemGrade, valorTexto: string) => void;
}) {
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", justifyContent: "flex-end", background: "var(--overlay)" }} onClick={onFechar}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: "min(30rem, 100%)", height: "100%", background: "var(--surface)", overflowY: "auto",
        borderLeft: "1px solid var(--border)", padding: "1.2rem",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h3 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700, color: "var(--text)" }}>{item.nome || "Ingrediente"}</h3>
          <button type="button" className="btn-ghost" onClick={onFechar}>Fechar</button>
        </div>
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: 0 }}>
          {item.categoria_nasem} · origem {item.origem}. Campos em branco são completados automaticamente pelo template da categoria no cálculo.
        </p>
        {GRUPOS_CAMPOS_NUTRICIONAIS.map((grupo) => (
          <div key={grupo.titulo} style={{ marginTop: "1rem" }}>
            <h4 style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--gold-deep)", margin: "0 0 0.5rem" }}>{grupo.titulo}</h4>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
              {grupo.campos.map((campo) => (
                <label key={campo} style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
                  {ROTULOS_CAMPOS_NUTRICIONAIS[campo]}
                  <input
                    type="number" step="0.01" value={(item as any)[campo] ?? ""}
                    onChange={(e) => onAtualizarCampo(campo, e.target.value)}
                    placeholder="—"
                    style={{ width: "100%", marginTop: "0.15rem", padding: "0.35rem 0.5rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)", fontSize: "0.8rem" }}
                  />
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
