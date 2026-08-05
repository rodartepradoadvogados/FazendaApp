"use client";
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { Plus, Trash2 } from "lucide-react";
import {
  fetchAnimais,
  fetchProtocolosIatfCadastrados, criarProtocoloIatfCadastrado, atualizarProtocoloIatfCadastrado, excluirProtocoloIatfCadastrado,
  fetchCentralProtocolosAcompanhamento, fetchCentralProtocolosHistorico,
  fetchPrincipiosAtivos,
  formatDate,
  TIPOS_PROTOCOLO_CUSTOM,
  type ProtocoloIatfMolde, type EtapaProtocoloIatf, type LinhaCentralProtocolos,
} from "@/lib/api";
import type { AnimalRow } from "@/components/AnimalModal";
import { UNIDADES_PROTOCOLO } from "@/lib/constants";
import { TabBar } from "@/components/ui";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";

const FormProtocoloCustomizado = dynamic(() => import("@/components/lancamentos/FormProtocoloCustomizado").then((m) => m.FormProtocoloCustomizado), { ssr: false });
// Editores de cadastro reaproveitados de Configurações > Cadastro — MESMO
// componente, mesmo endpoint, mesmos protocolos. Ver comentário em TIPOS_CADASTRO.
const CadastroProtocolosSanitarios = dynamic(() => import("@/components/CadastroSanitario").then((m) => m.CadastroProtocolosSanitarios), { ssr: false });
const CadastroProtocolosInducao = dynamic(() => import("@/components/CadastroSanitario").then((m) => m.CadastroProtocolosInducao), { ssr: false });
const CadastroProtocolosCustomizados = dynamic(() => import("@/components/CadastroProtocolosCustomizados"), { ssr: false });

const inputStyle: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", width: "100%",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

const LABEL_TIPO: Record<string, string> = { produtivo: "Produtivo", reprodutivo: "Reprodutivo", sanitario: "Sanitário" };
const COR_TIPO: Record<string, string> = { produtivo: "var(--green-light)", reprodutivo: "var(--dourado-light)", sanitario: "var(--red)" };

function Pill({ children, cor }: { children: React.ReactNode; cor?: string }) {
  return (
    <span style={{
      fontSize: "0.7rem", fontWeight: 700, padding: "0.15rem 0.55rem", borderRadius: "999px",
      background: "var(--surface-2)", color: cor || "var(--text-muted)", border: `1px solid ${cor || "var(--border)"}`,
    }}>{children}</span>
  );
}

// ─────────────────────────── Aba Cadastro ───────────────────────────
const DIAS_IATF = [0, 7, 9] as const;

function novaEtapaIatf(dia: number): EtapaProtocoloIatf {
  return { dia, criterio_tipo: "medicamento", produto: "", dose: null, unidade: "", via: "" };
}

function EditorMoldeIatf({ molde, onSalvo, onCancelar }: { molde: ProtocoloIatfMolde | null; onSalvo: () => void; onCancelar: () => void }) {
  const [nome, setNome] = useState(molde?.nome || "");
  const [observacao, setObservacao] = useState(molde?.observacao || "");
  const [etapas, setEtapas] = useState<EtapaProtocoloIatf[]>(molde?.etapas.length ? molde.etapas : [novaEtapaIatf(0)]);
  const [principios, setPrincipios] = useState<string[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchPrincipiosAtivos().then((d: any[]) => setPrincipios(d.map((p) => p.nome))).catch(() => {}); }, []);

  function atualizar(i: number, patch: Partial<EtapaProtocoloIatf>) {
    setEtapas((es) => es.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));
  }
  function remover(i: number) { setEtapas((es) => es.filter((_, idx) => idx !== i)); }
  function adicionar() { setEtapas((es) => [...es, novaEtapaIatf(0)]); }

  async function salvar() {
    setErro(null);
    if (!nome.trim()) { setErro("Informe o nome do protocolo."); return; }
    if (!etapas.length) { setErro("Informe ao menos uma etapa (D0, D7 ou D9)."); return; }
    setSalvando(true);
    try {
      const payload = { nome: nome.trim(), observacao: observacao || null, ativo: true, etapas };
      if (molde) await atualizarProtocoloIatfCadastrado(molde.id, payload);
      else await criarProtocoloIatfCadastrado(payload);
      onSalvo();
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar o protocolo IATF");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="card mb-3" style={{ background: "var(--surface-2)" }}>
      <div className="card-header mb-2">{molde ? "Editar protocolo IATF" : "Novo protocolo IATF"}</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label>
          <input style={inputStyle} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: Protocolo IATF Lote A" /></div>
        <div><label style={labelStyle}>Observação</label>
          <input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} placeholder="Opcional" /></div>
      </div>
      <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
        Hormônios de D0/D7/D9 — D11 é sempre a inseminação, nunca entra no molde.
      </p>
      {etapas.map((e, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "auto 1fr 1fr 1fr auto auto auto", gap: "0.4rem", alignItems: "end", marginBottom: "0.5rem" }}>
          <div><label style={labelStyle}>Dia</label>
            <select style={inputStyle} value={e.dia} onChange={(ev) => atualizar(i, { dia: Number(ev.target.value) })}>
              {DIAS_IATF.map((d) => <option key={d} value={d}>D{d}</option>)}
            </select>
          </div>
          <div><label style={labelStyle}>Definir por</label>
            <select style={inputStyle} value={e.criterio_tipo} onChange={(ev) => atualizar(i, { criterio_tipo: ev.target.value as any, produto: "" })}>
              <option value="medicamento">Medicamento</option>
              <option value="principio_ativo">Princípio ativo</option>
              <option value="classificacao">Classificação</option>
            </select>
          </div>
          <div><label style={labelStyle}>{e.criterio_tipo === "principio_ativo" ? "Princípio ativo" : e.criterio_tipo === "classificacao" ? "Classificação" : "Medicamento"}</label>
            {e.criterio_tipo === "principio_ativo" ? (
              <select style={inputStyle} value={e.produto} onChange={(ev) => atualizar(i, { produto: ev.target.value })}>
                <option value="">Selecione…</option>
                {principios.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            ) : (
              <input style={inputStyle} value={e.produto} onChange={(ev) => atualizar(i, { produto: ev.target.value })} placeholder="Nome" />
            )}
          </div>
          <div><label style={labelStyle}>Dose / unid.</label>
            <div style={{ display: "flex", gap: "0.3rem" }}>
              <input type="number" style={inputStyle} value={e.dose ?? ""} onChange={(ev) => atualizar(i, { dose: ev.target.value ? Number(ev.target.value) : null })} placeholder="0" />
              <select style={inputStyle} value={e.unidade || ""} onChange={(ev) => atualizar(i, { unidade: ev.target.value })}>
                <option value="">—</option>
                {/* Unidade fora da lista (protocolo antigo) continua visível para não sumir ao editar. */}
                {e.unidade && !UNIDADES_PROTOCOLO.includes(e.unidade) && <option value={e.unidade}>{e.unidade}</option>}
                {UNIDADES_PROTOCOLO.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
          </div>
          <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => remover(i)} title="Remover etapa"><Trash2 size={15} /></button>
        </div>
      ))}
      <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem", display: "inline-flex", alignItems: "center", gap: 4, marginBottom: "0.8rem" }} onClick={adicionar}>
        <Plus size={13} /> Adicionar hormônio
      </button>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{erro}</p>}
      <div className="flex items-center gap-3">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
        <button className="btn-ghost" onClick={onCancelar}>Cancelar</button>
      </div>
    </div>
  );
}

// Cadastro de molde de IATF — o único dos 4 que não tinha editor próprio
// antes da Central (os outros 3 já eram cadastrados em Configurações, e são
// reaproveitados aqui pelos MESMOS componentes, ver CadastroTab).
function CadastroIatf() {
  const [moldesIatf, setMoldesIatf] = useState<ProtocoloIatfMolde[] | null>(null);
  const [editando, setEditando] = useState<ProtocoloIatfMolde | null | "novo">(null);

  const carregar = () => { fetchProtocolosIatfCadastrados().then(setMoldesIatf).catch(() => setMoldesIatf([])); };
  useEffect(carregar, []);

  async function excluir(id: number) {
    if (!window.confirm("Excluir este protocolo IATF cadastrado?")) return;
    try { await excluirProtocoloIatfCadastrado(id); carregar(); }
    catch (e: any) { window.alert(e.message || "Não foi possível excluir."); }
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <div className="card-header" style={{ padding: 0 }}>Protocolos IATF cadastrados</div>
        {editando === null && (
          <button className="btn-primary" style={{ fontSize: "0.78rem", display: "inline-flex", alignItems: "center", gap: 4 }} onClick={() => setEditando("novo")}>
            <Plus size={13} /> Novo
          </button>
        )}
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Define os hormônios de D0/D7/D9 — D11 é sempre a inseminação e nunca faz parte do molde.
        Lançar sem escolher um molde continua funcionando (hormônios digitados na hora), como sempre foi.
      </p>
      {editando !== null && (
        <EditorMoldeIatf
          molde={editando === "novo" ? null : editando}
          onSalvo={() => { setEditando(null); carregar(); }}
          onCancelar={() => setEditando(null)}
        />
      )}
      <table className="fazenda-table">
        <thead><tr><th>Nome</th><th>Etapas</th><th></th></tr></thead>
        <tbody>
          {(moldesIatf || []).map((m) => (
            <tr key={m.id}>
              <td style={{ fontWeight: 600 }}>{m.nome}{!m.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
              <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{m.etapas.map((e) => `D${e.dia}`).join(", ") || "—"}</td>
              <td style={{ textAlign: "right" }}>
                <button className="btn-ghost" style={{ fontSize: "0.74rem", marginRight: "0.5rem" }} onClick={() => setEditando(m)}>Editar</button>
                <button className="btn-ghost" style={{ fontSize: "0.74rem", color: "var(--red)" }} onClick={() => excluir(m.id)}>Excluir</button>
              </td>
            </tr>
          ))}
          {moldesIatf && !moldesIatf.length && (
            <tr><td colSpan={3} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo IATF cadastrado — lançar continua funcionando sem molde (hormônios digitados na hora).</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// Cadastro único: escolhe-se DE QUE protocolo se trata e abre-se o editor
// daquele tipo. Os três já existentes (sanitário, indução, customizado) são
// os MESMOS componentes usados em Configurações > Cadastro — mesmo formulário,
// mesmo endpoint, mesmos protocolos já cadastrados. Não há cópia nem tabela
// paralela: cadastrar aqui ou lá é indiferente.
const TIPOS_CADASTRO = [
  { id: "sanitario", label: "Sanitário", desc: "Curativo ou preventivo — cronograma de dias (D0/D1/D2…)" },
  { id: "iatf", label: "IATF", desc: "Hormônios de D0/D7/D9" },
  { id: "inducao", label: "Indução de lactação", desc: "Medicamento, implante e manejo por dia" },
  { id: "customizado", label: "Customizado", desc: "Roteiro livre de etapas, para qualquer rotina" },
] as const;
type TipoCadastro = typeof TIPOS_CADASTRO[number]["id"];

function CadastroTab() {
  const [tipo, setTipo] = useState<TipoCadastro>("sanitario");

  return (
    <div>
      <div className="card mb-3">
        <div className="card-header mb-2">Do que se trata o protocolo?</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {TIPOS_CADASTRO.map((t) => {
            const ativo = t.id === tipo;
            return (
              <button
                key={t.id} type="button" onClick={() => setTipo(t.id)} title={t.desc}
                style={{
                  textAlign: "left", padding: "0.6rem 0.75rem", borderRadius: "8px", cursor: "pointer",
                  border: `1px solid ${ativo ? "var(--dourado)" : "var(--border)"}`,
                  background: ativo ? "var(--pill-active-bg)" : "transparent",
                  color: ativo ? "var(--dourado-light)" : "var(--text)",
                }}
              >
                <span style={{ display: "block", fontWeight: 700, fontSize: "0.85rem" }}>{t.label}</span>
                <span style={{ display: "block", fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>{t.desc}</span>
              </button>
            );
          })}
        </div>
      </div>

      {tipo === "iatf" && <CadastroIatf />}
      {tipo === "sanitario" && <CadastroProtocolosSanitarios />}
      {tipo === "inducao" && <CadastroProtocolosInducao />}
      {tipo === "customizado" && <CadastroProtocolosCustomizados />}

      <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "1rem" }}>
        Regra que <strong>se repete</strong> no tempo (vermífugo a cada 4 meses, Brucelose no nascimento) não é protocolo
        de etapas — continua no <strong>Calendário Sanitário</strong>, em Sanidade. Aqui ficam só os cronogramas de dias fixos.
      </p>
    </div>
  );
}

// ─────────────────────────── Aba Lançamento (só Customizado) ───────────────────────────
function LancamentoTab({ animais }: { animais: AnimalRow[] }) {
  return (
    <div>
      <div className="card mb-3">
        <div className="card-header mb-2">Lançar protocolo customizado</div>
        <FormProtocoloCustomizado animais={animais as any} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <a href="/lancamentos" className="card" style={{ textDecoration: "none" }}>
          <div style={{ fontWeight: 700, color: "var(--dourado-light)", fontSize: "0.85rem" }}>IATF</div>
          <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>lançar em Lançamentos →</div>
        </a>
        <a href="/lancamentos" className="card" style={{ textDecoration: "none" }}>
          <div style={{ fontWeight: 700, color: "var(--dourado-light)", fontSize: "0.85rem" }}>Indução de lactação</div>
          <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>lançar em Lançamentos →</div>
        </a>
        <a href="/lancamentos" className="card" style={{ textDecoration: "none" }}>
          <div style={{ fontWeight: 700, color: "var(--dourado-light)", fontSize: "0.85rem" }}>Protocolo Sanitário</div>
          <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>lançar em Lançamentos →</div>
        </a>
      </div>
    </div>
  );
}

// ─────────────────────────── Abas Acompanhamento / Histórico ───────────────────────────
const COLUNAS_EXPORT: ColunaExport[] = [
  { header: "Protocolo", key: "nome" }, { header: "Tipo", key: "tipoLabel" },
  { header: "Início", key: "inicioFmt" }, { header: "Fim", key: "fimFmt" },
  { header: "Etapas", key: "etapasLabel" }, { header: "Animais", key: "animais" }, { header: "Status", key: "status" },
];

function ListaProtocolos({ historico }: { historico: boolean }) {
  const [linhas, setLinhas] = useState<LinhaCentralProtocolos[] | null>(null);
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const fetcher = historico ? fetchCentralProtocolosHistorico : fetchCentralProtocolosAcompanhamento;
    fetcher({ nome: nome || undefined, tipo: tipo || undefined })
      .then(setLinhas).catch((e) => setErro(e.message));
  }, [nome, tipo, historico]);

  const linhasExport = useMemo(() => (linhas || []).map((l) => ({
    nome: l.nome, tipoLabel: LABEL_TIPO[l.tipo] || l.tipo,
    inicioFmt: formatDate(l.data_inicio), fimFmt: formatDate(l.data_fim),
    etapasLabel: `${l.etapas_realizadas}/${l.etapas_total}`, animais: l.animais,
    status: l.status === "concluido" ? "Concluído" : l.status === "cancelado" ? "Cancelado" : "Ativo",
  })), [linhas]);

  return (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Buscar por nome do protocolo</label>
          <input style={inputStyle} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: mastite, IATF…" /></div>
        <div><label style={labelStyle}>Tipo</label>
          <select style={inputStyle} value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="">Todos os tipos</option>
            {TIPOS_PROTOCOLO_CUSTOM.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></div>
      </div>

      {erro && <div className="alert-critico mb-3"><span>Sem dados: {erro}.</span></div>}
      {!linhas ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : (
        <>
          <div className="flex items-center justify-between mb-2">
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{linhas.length} protocolo(s)</span>
            {historico && <ExportarBotoes titulo="Central de Protocolos — Histórico" nomeArquivoBase="central_protocolos_historico" colunas={COLUNAS_EXPORT} linhas={linhasExport} />}
          </div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr>
                <th>Protocolo</th><th>Tipo</th><th>Início</th><th>Fim</th><th>Etapas</th><th>Animais</th><th>Status</th>
              </tr></thead>
              <tbody>
                {linhas.map((l) => (
                  <tr key={`${l.origem}-${l.origem_id}`}>
                    <td style={{ fontWeight: 600, fontSize: "0.82rem" }}>{l.nome}</td>
                    <td><Pill cor={COR_TIPO[l.tipo]}>{LABEL_TIPO[l.tipo] || l.tipo}</Pill></td>
                    <td style={{ fontSize: "0.78rem" }}>{formatDate(l.data_inicio)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{formatDate(l.data_fim)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{l.etapas_realizadas}/{l.etapas_total}{!historico ? ` (faltam ${l.etapas_faltam})` : ""}</td>
                    <td style={{ fontSize: "0.78rem" }}>{l.animais || "—"}</td>
                    <td>
                      {l.status === "concluido" ? <span style={{ color: "var(--green-light)" }}>Concluído</span>
                        : l.status === "cancelado" ? <span style={{ color: "var(--red)" }}>Cancelado</span>
                        : <span style={{ color: "var(--dourado-light)" }}>Ativo</span>}
                    </td>
                  </tr>
                ))}
                {!linhas.length && (
                  <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo {historico ? "concluído" : "ativo"} para os filtros escolhidos.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

// ─────────────────────────── Página ───────────────────────────
export default function ProtocolosPage() {
  const [aba, setAba] = useState<"cadastro" | "lancamento" | "acompanhamento" | "historico">("acompanhamento");
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  useEffect(() => { fetchAnimais().then(setAnimais).catch(() => {}); }, []);

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold mb-1" style={{ color: "var(--dourado-light)" }}>Central de Protocolos</h1>
      <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginBottom: "1.2rem" }}>
        IATF, Sanitário, Indução de Lactação e Customizado — cadastro, lançamento, acompanhamento e histórico num só lugar.
        IATF, Indução e Sanitário continuam lançados normalmente em Lançamentos; o Customizado lança só aqui.
      </p>

      <TabBar<"cadastro" | "lancamento" | "acompanhamento" | "historico">
        abas={[
          { id: "cadastro", label: "Cadastro", title: "Moldes de cada protocolo" },
          { id: "lancamento", label: "Lançamento", title: "Lançar protocolo customizado" },
          { id: "acompanhamento", label: "Acompanhamento", title: "Protocolos em andamento, dos 4 tipos" },
          { id: "historico", label: "Histórico", title: "Concluídos e cancelados, com exportação" },
        ]}
        ativa={aba}
        onChange={setAba}
      />

      {aba === "cadastro" && <CadastroTab />}
      {aba === "lancamento" && <LancamentoTab animais={animais} />}
      {aba === "acompanhamento" && <ListaProtocolos historico={false} />}
      {aba === "historico" && <ListaProtocolos historico />}
    </div>
  );
}
