"use client";
import React, { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Check, AlertTriangle, X } from "lucide-react";
import { adicionarAnimaisIatf, criarProtocoloIatf, fetchLancamentosIatf, fetchProtocolosIatfAtivos, formatDate, removerAnimalIatf } from "@/lib/api";
import type { HormonioIatf } from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { SelecaoAnimaisTabela } from "@/components/SelecaoAnimaisTabela";
import { EditorHormoniosIatf } from "@/components/EditorHormoniosIatf";
import { TabBar } from "@/components/ui";
import { Campo, inputStyle, lbl, nota } from "@/components/lancamentos/comumForms";
import { SelectAnimal, addDias, IDADE_MIN_SERVICO } from "@/components/lancamentos/_shared";

function nomeAutoIatf(d0: string): string {
  if (!d0) return "";
  const fmt = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" });
  const d11 = new Date(d0 + "T00:00:00"); d11.setDate(d11.getDate() + 11);
  return `IATF ${fmt(d0)} A ${fmt(d11.toISOString().slice(0, 10))}`;
}
const HORMONIOS: Record<string, string[]> = {
  progesterona: ["Sincrogest", "Cidr"],
  benzoato: ["Sincrodiol"],
  buserelina: ["Sincroforte"],
  cloprostenol: ["Estron"],
  cipionato: ["SincroCP"],
};

type ProtocoloIatfAtivo = {
  lancamento_id: number; nome_protocolo: string; data_d0: string;
  animais: { numero_matriz: string; etapa_atual: string; data_etapa_atual: string | null; d0_confirmado?: boolean }[];
};

function ProtocolosIatfAtivos({ recarregarRef }: { recarregarRef: React.MutableRefObject<() => void> }) {
  const [ativos, setAtivos] = useState<ProtocoloIatfAtivo[] | null>(null);
  const [abertos, setAbertos] = useState<Set<number>>(new Set());
  const [removendo, setRemovendo] = useState<string | null>(null);
  const toggle = (id: number) => setAbertos((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const carregar = () => fetchProtocolosIatfAtivos().then(setAtivos).catch(() => setAtivos([]));
  useEffect(() => { carregar(); recarregarRef.current = carregar; }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function remover(lancamentoId: number, numero: string) {
    if (!window.confirm(`Remover ${numero} deste protocolo? Só é possível se nenhuma etapa dela já foi confirmada.`)) return;
    const chave = `${lancamentoId}-${numero}`;
    setRemovendo(chave);
    try {
      await removerAnimalIatf(lancamentoId, numero);
      await carregar();
    } catch (e: any) {
      window.alert(e.message || "Não foi possível remover este animal.");
    } finally {
      setRemovendo(null);
    }
  }

  if (!ativos || !ativos.length) return null;
  return (
    <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
      <div className="card-header mb-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
        Protocolos IATF em andamento ({ativos.length})
      </div>
      <div className="space-y-2">
        {ativos.map((p) => {
          const aberto = abertos.has(p.lancamento_id);
          return (
            <div key={p.lancamento_id} style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
              <button onClick={() => toggle(p.lancamento_id)} title={aberto ? "Clique para recolher os animais" : "Clique para ver os animais e etapas"} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.8rem", background: "var(--surface)", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
                {aberto ? <ChevronDown size={15} style={{ color: "var(--dourado-light)", flexShrink: 0 }} /> : <ChevronRight size={15} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />}
                <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{p.nome_protocolo}</span>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>D0 {formatDate(p.data_d0)} — {p.animais.length} animal(is)</span>
              </button>
              {aberto && (
                <table className="fazenda-table" style={{ margin: 0 }}>
                  <thead><tr><th>Nº</th><th>Etapa atual</th><th>Data</th><th>D0</th><th></th></tr></thead>
                  <tbody>
                    {p.animais.map((a) => (
                      <tr key={a.numero_matriz}>
                        <td style={{ fontWeight: 700 }}>{a.numero_matriz}</td>
                        <td>{a.etapa_atual}</td>
                        <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{a.data_etapa_atual ? formatDate(a.data_etapa_atual) : "—"}</td>
                        <td>
                          {a.d0_confirmado ? (
                            <span title="D0 confirmado na Agenda" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.74rem", color: "var(--green-light)" }}>
                              <Check size={13} /> confirmado
                            </span>
                          ) : (
                            <span title="D0 ainda não confirmado na Agenda — pode ter entrado no protocolo sem ter sido implantada" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.74rem", color: "var(--amber)" }}>
                              <AlertTriangle size={13} /> não confirmado
                            </span>
                          )}
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <button
                            type="button" className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                            disabled={removendo === `${p.lancamento_id}-${a.numero_matriz}`}
                            onClick={() => remover(p.lancamento_id, a.numero_matriz)}
                            title="Remover este animal do protocolo (corrige inclusão por engano)"
                          >
                            <X size={12} /> Remover
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function FormProtocoloIatf({ animais }: { animais: AnimalRow[] }) {
  // Novo protocolo (cria um lançamento) ou adicionar animais a um já existente.
  const [modo, setModo] = useState<"novo" | "existente">("novo");
  const [emLote, setEmLote] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [um, setUm] = useState("");
  const [d0, setD0] = useState("");
  const [hormonios, setHormonios] = useState<HormonioIatf[]>([]);
  // Protocolos já lançados (para "existente").
  const [existentes, setExistentes] = useState<{ lancamento_id: number; nome_protocolo: string; data_d0: string; qtd_animais: number }[]>([]);
  const [existenteId, setExistenteId] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const recarregarAtivosRef = useRef(() => {});
  const toggle = (n: string) => setSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const toggleTodos = () => setSel((p) => (p.size === animais.length && animais.length ? new Set() : new Set(animais.map((a) => a.numero))));

  const nomeProtocolo = nomeAutoIatf(d0);

  useEffect(() => {
    if (modo === "existente") fetchLancamentosIatf().then(setExistentes).catch(() => setExistentes([]));
  }, [modo]);

  async function salvar() {
    setErro(null); setSucesso(null);
    const animaisAlvo = emLote ? Array.from(sel) : (um ? [um] : []);
    if (!animaisAlvo.length) { setErro(emLote ? "Selecione ao menos um animal." : "Selecione a matriz."); return; }
    setSalvando(true);
    try {
      if (modo === "existente") {
        if (!existenteId) { setErro("Selecione o protocolo existente."); setSalvando(false); return; }
        const r = await adicionarAnimaisIatf(Number(existenteId), animaisAlvo);
        setSucesso(`${r.adicionados} animal(is) adicionado(s) ao protocolo "${r.nome_protocolo}".`);
      } else {
        if (!d0) { setErro("Informe a data do D0."); setSalvando(false); return; }
        const r = await criarProtocoloIatf({ animais: animaisAlvo, data_d0: d0, protocolo: nomeProtocolo, hormonios });
        setSucesso(`Protocolo "${nomeProtocolo}" agendado para ${r.animais} animal(is) — ${r.eventos_criados} eventos na Agenda (D0/D7/D9/D11).`);
      }
      setSel(new Set()); setUm("");
      recarregarAtivosRef.current();
      if (modo === "existente") fetchLancamentosIatf().then(setExistentes).catch(() => {});
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar protocolo IATF");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <TabBar<"novo" | "existente">
        abas={[
          { id: "novo", label: "Novo protocolo", title: "Criar um novo protocolo IATF (define D0 e hormônios)" },
          { id: "existente", label: "Adicionar a protocolo existente", title: "Incluir animais num protocolo já lançado (mesmo D0 e nome)" },
        ]}
        ativa={modo}
        onChange={setModo}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <Campo label="Seleção">
          <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}>
            <input type="checkbox" checked={emLote} onChange={(e) => setEmLote(e.target.checked)} /> Em lote (vários animais)
          </label>
        </Campo>
        {modo === "novo" ? (
          <>
            <Campo label="Data do D0"><input type="date" style={inputStyle} value={d0} onChange={(e) => setD0(e.target.value)} /></Campo>
            <Campo label="Nome do protocolo (automático)" full>
              <input style={{ ...inputStyle, opacity: 0.85 }} readOnly value={nomeProtocolo || "Informe a data do D0…"} />
            </Campo>
          </>
        ) : (
          <Campo label="Protocolo existente" full>
            <select style={inputStyle} value={existenteId} onChange={(e) => setExistenteId(e.target.value)}>
              <option value="">Selecione o protocolo…</option>
              {existentes.map((l) => <option key={l.lancamento_id} value={l.lancamento_id}>{l.nome_protocolo} — {l.qtd_animais} animal(is)</option>)}
            </select>
          </Campo>
        )}
      </div>

      <div className="mt-3">
        <label style={lbl}>Matriz (nº)</label>
        {emLote
          ? <SelecaoAnimaisTabela
              animais={animais} selecionados={sel} toggle={toggle} toggleTodos={toggleTodos}
              colunas={[
                { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                { header: "Lote", render: (a) => a.grupo_primario || "—" },
              ]}
            />
          : <SelectAnimal animais={animais} value={um} onChange={setUm} placeholder="Selecione a matriz…" />}
      </div>
      <p style={nota}>Matriz lista apenas fêmeas aptas (≥ {IDADE_MIN_SERVICO} meses). Isso só agenda o protocolo hormonal — a inseminação em si (D11) é lançada à parte, na sub-aba Inseminação.</p>

      {modo === "novo" && (
        <>
          <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
            <div className="card-header mb-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
              Cronograma IATF — vai para a Agenda
            </div>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr><th>Dia</th><th>Data</th><th>Ação / hormônio</th></tr></thead>
                <tbody>
                  <tr><td style={{ fontWeight: 700 }}>D0</td><td>{addDias(d0, 0)}</td><td>Implante de progesterona + Benzoato de estradiol + Acetato de buserelina</td></tr>
                  <tr><td style={{ fontWeight: 700 }}>D7</td><td>{addDias(d0, 7)}</td><td>Cloprostenol</td></tr>
                  <tr><td style={{ fontWeight: 700 }}>D9</td><td>{addDias(d0, 9)}</td><td>Retirar implante + Cipionato de estradiol + Cloprostenol</td></tr>
                  <tr><td style={{ fontWeight: 700, color: "var(--green-light)" }}>D11</td><td>{addDias(d0, 11)}</td><td style={{ color: "var(--green-light)" }}>Inseminação (IATF)</td></tr>
                </tbody>
              </table>
            </div>
            <p style={nota}>Ao salvar, cria os eventos D0/D7/D9/D11 na Agenda para cada animal selecionado.</p>
          </div>
          <EditorHormoniosIatf onChange={setHormonios} />
        </>
      )}
      <ProtocolosIatfAtivos recarregarRef={recarregarAtivosRef} />
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}
