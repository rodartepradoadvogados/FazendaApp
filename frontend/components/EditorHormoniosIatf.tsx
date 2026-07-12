"use client";
// Editor de medicamentos (hormônios) por dia do protocolo IATF.
// Cada dia (D0/D7/D9) pode ter vários medicamentos (ex.: D0 = 1ml SincroCP +
// 2ml Estron). O produto pode ser definido pelo próprio medicamento, por
// princípio ativo ou por classificação — nos dois últimos, abre a lista dos
// medicamentos em estoque que cumprem o critério. Ao confirmar o dia na Agenda,
// o backend dá baixa no estoque e registra a aplicação em Sanidade por vaca.
import { useEffect, useMemo, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { fetchEstoque, fetchMedicamentos, fetchPrincipiosAtivos, CLASSIFICACOES_MEDICAMENTO, type HormonioIatf } from "@/lib/api";
import { VIAS_APLICACAO } from "@/lib/constants";

const DIAS = [
  { dia: 0, rotulo: "D0", padrao: "Implante P4 + Benzoato de estradiol + GnRH" },
  { dia: 7, rotulo: "D7", padrao: "Cloprostenol (PGF2α)" },
  { dia: 9, rotulo: "D9", padrao: "Retirar implante + Cipionato de estradiol + Cloprostenol" },
];

const UNIDADES_PADRAO = ["ml", "L", "unidade", "dose", "kg"];
const GRUPOS_UNIDADE = [["ml", "unidade", "dose"], ["L", "kg"]];
const unidadesCompat = (u?: string | null): string[] =>
  !u ? UNIDADES_PADRAO : (GRUPOS_UNIDADE.find((g) => g.includes(u)) || [u]);

type EstItem = { nome: string; quantidade?: number | null; unidade?: string | null };
type Linha = {
  key: string; dia: number; definirPor: "medicamento" | "principio_ativo" | "classificacao";
  criterio: string; produto: string; dose: string; unidade: string; via: string;
};

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "0.4rem 0.55rem", borderRadius: 6, fontSize: "0.82rem",
  background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)",
};
const lblMin: React.CSSProperties = { fontSize: "0.68rem", color: "var(--text-muted)", display: "block", marginBottom: "0.15rem" };

let _seq = 0;
const novaChave = () => `h${++_seq}`;

export function EditorHormoniosIatf({ onChange }: { onChange: (h: HormonioIatf[]) => void }) {
  const [estoque, setEstoque] = useState<EstItem[]>([]);
  const [principios, setPrincipios] = useState<string[]>([]);
  const [linhas, setLinhas] = useState<Linha[]>([]);
  // Medicamentos que cumprem o critério, por linha (para princípio/classificação).
  const [opcoes, setOpcoes] = useState<Record<string, EstItem[]>>({});

  useEffect(() => {
    fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {});
    fetchPrincipiosAtivos().then((d: any[]) => setPrincipios(d.map((p) => p.nome))).catch(() => {});
  }, []);

  // Emite a lista pronta para a API sempre que muda.
  useEffect(() => {
    onChange(
      linhas
        .filter((l) => l.produto.trim())
        .map((l) => ({ dia: l.dia, produto: l.produto.trim(), dose: l.dose ? Number(l.dose) : null, unidade: l.unidade || undefined, via: l.via || undefined }))
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linhas]);

  const estoqueOrdenado = useMemo(() => [...estoque].sort((a, b) => a.nome.localeCompare(b.nome)), [estoque]);
  const unidadeDoProduto = (nome: string) => estoque.find((e) => e.nome === nome)?.unidade;

  function adicionar(dia: number) {
    setLinhas((ls) => [...ls, { key: novaChave(), dia, definirPor: "medicamento", criterio: "", produto: "", dose: "", unidade: "", via: "" }]);
  }
  function remover(key: string) {
    setLinhas((ls) => ls.filter((l) => l.key !== key));
    setOpcoes((o) => { const n = { ...o }; delete n[key]; return n; });
  }
  function atualizar(key: string, patch: Partial<Linha>) {
    setLinhas((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  }

  function escolherDefinirPor(l: Linha, valor: Linha["definirPor"]) {
    atualizar(l.key, { definirPor: valor, criterio: "", produto: "", unidade: "" });
    setOpcoes((o) => ({ ...o, [l.key]: [] }));
  }
  function escolherCriterio(l: Linha, criterio: string) {
    atualizar(l.key, { criterio, produto: "", unidade: "" });
    if (!criterio) { setOpcoes((o) => ({ ...o, [l.key]: [] })); return; }
    const filtro = l.definirPor === "principio_ativo" ? { principio_ativo: criterio } : { classificacao: criterio };
    fetchMedicamentos(filtro)
      .then((m: EstItem[]) => setOpcoes((o) => ({ ...o, [l.key]: m })))
      .catch(() => setOpcoes((o) => ({ ...o, [l.key]: [] })));
  }
  function escolherProduto(l: Linha, nome: string) {
    const comp = unidadesCompat(unidadeDoProduto(nome));
    atualizar(l.key, { produto: nome, unidade: comp[0] || "" });
  }

  return (
    <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
      <div className="card-header mb-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
        Medicamentos por dia (opcional) — dão baixa no estoque quando você confirmar o dia na Agenda
      </div>
      <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
        Informe os medicamentos de cada dia (ex.: D0 = 1&nbsp;ml SincroCP + 2&nbsp;ml Estron). Cada dose é multiplicada pelo nº de vacas confirmadas. Sem medicamentos, o protocolo só agenda os dias (sem baixa de estoque).
      </p>

      {DIAS.map(({ dia, rotulo, padrao }) => {
        const doDia = linhas.filter((l) => l.dia === dia);
        return (
          <div key={dia} style={{ marginBottom: "0.9rem", paddingBottom: "0.6rem", borderBottom: "1px solid var(--border)" }}>
            <div className="flex items-center justify-between" style={{ marginBottom: "0.35rem" }}>
              <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{rotulo} <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: "0.72rem" }}>— {padrao}</span></span>
              <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem", display: "inline-flex", alignItems: "center", gap: 4 }} onClick={() => adicionar(dia)}>
                <Plus size={13} /> medicamento
              </button>
            </div>

            {doDia.map((l) => {
              const listaProdutos = l.definirPor === "medicamento" ? estoqueOrdenado : (opcoes[l.key] || []);
              return (
                <div key={l.key} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.55rem", marginBottom: "0.45rem" }}>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <div>
                      <label style={lblMin}>Definir por</label>
                      <select style={inputStyle} value={l.definirPor} onChange={(e) => escolherDefinirPor(l, e.target.value as Linha["definirPor"])}>
                        <option value="medicamento">Medicamento</option>
                        <option value="principio_ativo">Princípio ativo</option>
                        <option value="classificacao">Classificação</option>
                      </select>
                    </div>

                    {l.definirPor !== "medicamento" && (
                      <div>
                        <label style={lblMin}>{l.definirPor === "principio_ativo" ? "Princípio ativo" : "Classificação"}</label>
                        <select style={inputStyle} value={l.criterio} onChange={(e) => escolherCriterio(l, e.target.value)}>
                          <option value="">Selecione…</option>
                          {(l.definirPor === "principio_ativo" ? principios : CLASSIFICACOES_MEDICAMENTO).map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      </div>
                    )}

                    <div>
                      <label style={lblMin}>Medicamento</label>
                      <select style={inputStyle} value={l.produto} onChange={(e) => escolherProduto(l, e.target.value)} disabled={l.definirPor !== "medicamento" && !l.criterio}>
                        <option value="">Selecione…</option>
                        {listaProdutos.map((m) => <option key={m.nome} value={m.nome}>{m.nome}{m.quantidade != null ? ` (${m.quantidade} ${m.unidade || ""})` : ""}</option>)}
                      </select>
                      {l.definirPor !== "medicamento" && l.criterio && !listaProdutos.length && (
                        <p style={{ fontSize: "0.68rem", color: "var(--amber)", marginTop: 2 }}>Nenhum medicamento com esse critério.</p>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-1">
                      <div>
                        <label style={lblMin}>Dose</label>
                        <input type="number" inputMode="decimal" style={inputStyle} value={l.dose} onChange={(e) => atualizar(l.key, { dose: e.target.value })} placeholder="0" />
                      </div>
                      <div>
                        <label style={lblMin}>Unid.</label>
                        <select style={inputStyle} value={l.unidade} onChange={(e) => atualizar(l.key, { unidade: e.target.value })}>
                          {!l.unidade && <option value="">—</option>}
                          {unidadesCompat(unidadeDoProduto(l.produto)).map((u) => <option key={u} value={u}>{u}</option>)}
                        </select>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-2 mt-2">
                    <div style={{ flex: 1, maxWidth: 220 }}>
                      <label style={lblMin}>Via de aplicação</label>
                      <select style={inputStyle} value={l.via} onChange={(e) => atualizar(l.key, { via: e.target.value })}>
                        <option value="">Selecione…</option>
                        {VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
                      </select>
                    </div>
                    <button type="button" className="btn-ghost" style={{ color: "var(--red)", alignSelf: "flex-end" }} onClick={() => remover(l.key)} title="Remover">
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
