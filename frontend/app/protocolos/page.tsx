"use client";
import { useEffect, useId, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { Plus, Trash2, FileText, FileSpreadsheet } from "lucide-react";
import {
  fetchAnimais, fetchEstoque,
  fetchProtocolosIatfCadastrados, criarProtocoloIatfCadastrado, atualizarProtocoloIatfCadastrado, excluirProtocoloIatfCadastrado,
  fetchCentralProtocolosAcompanhamento, fetchCentralProtocolosHistorico,
  fetchDetalheProtocolo, darBaixaProtocolo, encerrarProtocolo, reabrirProtocolo, cancelarProtocolo,
  desfazerAplicacao, editarLancamentoProtocolo,
  fetchPrincipiosAtivos,
  formatDate,
  type ProtocoloIatfMolde, type EtapaProtocoloIatf, type LinhaCentralProtocolos,
  type DetalheCentralProtocolo, type MedicamentoIatf,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import { exportarFolhaCampoPDF, exportarFolhaCampoExcel } from "@/lib/folhaProtocolo";
import type { AnimalRow } from "@/components/AnimalModal";
import { type EstoqueItem } from "@/components/lancamentos/comumForms";
import { UNIDADES_PROTOCOLO } from "@/lib/constants";
import { TabBar } from "@/components/ui";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";

const FormProtocoloCustomizado = dynamic(() => import("@/components/lancamentos/FormProtocoloCustomizado").then((m) => m.FormProtocoloCustomizado), { ssr: false });
// Os mesmos formulários já usados em Lançamentos — reaproveitados aqui, na
// aba Lançamento, para IATF/Indução/Sanitário poderem ser lançados também
// pela Central (ver comentário em TIPOS_LANCAMENTO).
const FormProtocoloIatf = dynamic(() => import("@/components/lancamentos/FormProtocoloIatf").then((m) => m.FormProtocoloIatf), { ssr: false });
const FormInducaoLactacao = dynamic(() => import("@/components/FormInducaoLactacao").then((m) => m.FormInducaoLactacao), { ssr: false });
const FormProtocoloSanitario = dynamic(() => import("@/components/lancamentos/FormProtocoloSanitario").then((m) => m.FormProtocoloSanitario), { ssr: false });
// Editores de cadastro reaproveitados de Configurações > Cadastro — MESMO
// componente, mesmo endpoint, mesmos protocolos. Ver comentário em TIPOS_CADASTRO.
const CadastroProtocolosSanitarios = dynamic(() => import("@/components/CadastroSanitario").then((m) => m.CadastroProtocolosSanitarios), { ssr: false });
// Cadastro do Calendário Sanitário (Preventivo) — migrado de Lançamentos para
// cá: em Lançamentos só se aplica uma regra já cadastrada (ver
// FormAplicarCalendarioSanitario), o cadastro da regra em si mora aqui.
const FormCalendarioSanitario = dynamic(() => import("@/components/lancamentos/FormCalendarioSanitario").then((m) => m.FormCalendarioSanitario), { ssr: false });
const CadastroProtocolosInducao = dynamic(() => import("@/components/CadastroSanitario").then((m) => m.CadastroProtocolosInducao), { ssr: false });
const CadastroProtocolosCustomizados = dynamic(() => import("@/components/CadastroProtocolosCustomizados"), { ssr: false });
const CadastroLida = dynamic(() => import("@/components/CadastroLida"), { ssr: false });
const FormLida = dynamic(() => import("@/components/lancamentos/FormLida").then((m) => m.FormLida), { ssr: false });

const inputStyle: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", width: "100%",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

const LABEL_TIPO: Record<string, string> = { produtivo: "Produtivo", reprodutivo: "Reprodutivo", sanitario: "Sanitário", lida: "Lida" };
const COR_TIPO: Record<string, string> = { produtivo: "var(--green-light)", reprodutivo: "var(--dourado-light)", sanitario: "var(--red)", lida: "var(--blue)" };

function Pill({ children, cor }: { children: React.ReactNode; cor?: string }) {
  return (
    <span style={{
      fontSize: "0.7rem", fontWeight: 700, padding: "0.15rem 0.55rem", borderRadius: "999px",
      background: "var(--surface-2)", color: cor || "var(--text-muted)", border: `1px solid ${cor || "var(--border)"}`,
    }}>{children}</span>
  );
}

// ─────────────────────────── Aba Cadastro ───────────────────────────
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
        O dia de cada hormônio é livre — o clássico é D0/D7/D9, mas há protocolo com outro espaçamento (ex.: D0/D8/D10/D12).
        A inseminação nunca entra no molde: ela é sempre 2 dias depois da última etapa cadastrada.
      </p>
      {etapas.map((e, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "auto 1fr 1fr 1fr auto auto auto", gap: "0.4rem", alignItems: "end", marginBottom: "0.5rem" }}>
          <div><label style={labelStyle}>Dia</label>
            <div className="flex items-center gap-1">
              <span style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>D</span>
              <input type="number" min={0} step={1} style={inputStyle} value={e.dia}
                     onChange={(ev) => atualizar(i, { dia: Math.max(0, Number(ev.target.value) || 0) })} />
            </div>
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
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
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
            Define os hormônios em dias livres (o clássico é D0/D7/D9, mas aceita outro espaçamento, ex.: D0/D8/D10/D12).
            A inseminação nunca faz parte do molde — é sempre 2 dias depois da última etapa cadastrada.
            Lançar sem escolher um molde continua funcionando (hormônios digitados na hora, cronograma clássico D0/D7/D9/D11), como sempre foi.
          </p>
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
      </div>
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
        {editando !== null ? (
          <EditorMoldeIatf
            molde={editando === "novo" ? null : editando}
            onSalvo={() => { setEditando(null); carregar(); }}
            onCancelar={() => setEditando(null)}
          />
        ) : (
          <div className="card" style={{ textAlign: "center", padding: "2.2rem 1rem" }}>
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Selecione um protocolo para editar, ou clique em Novo.</p>
          </div>
        )}
      </div>
    </div>
  );
}

// Seletor visual "de que tipo é o protocolo?" — mesmo desenho nas abas
// Cadastro e Lançamento (o usuário achou bonito o de Cadastro e pediu para
// repetir). Genérico o bastante para os dois conjuntos de tipos, que não são
// os mesmos: Cadastro tem 4 tipos (não inclui nada que não se cadastra por
// aqui); Lançamento também tem 4, na mesma ordem, por familiaridade.
function SeletorTipoProtocolo<T extends string>({ titulo, tipos, tipo, onChange }: {
  titulo: string;
  tipos: readonly { id: T; label: string; desc: string }[];
  tipo: T;
  onChange: (t: T) => void;
}) {
  return (
    <div className="card mb-3">
      <div className="card-header mb-2">{titulo}</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {tipos.map((t) => {
          const ativo = t.id === tipo;
          return (
            <button
              key={t.id} type="button" onClick={() => onChange(t.id)} title={t.desc}
              style={{
                textAlign: "left", padding: "0.6rem 0.75rem", borderRadius: "var(--r-sm)", cursor: "pointer",
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
  );
}

// Cadastro único: escolhe-se DE QUE protocolo se trata e abre-se o editor
// daquele tipo. Os três já existentes (sanitário, indução, customizado) são
// os MESMOS componentes usados em Configurações > Cadastro — mesmo formulário,
// mesmo endpoint, mesmos protocolos já cadastrados. Não há cópia nem tabela
// paralela: cadastrar aqui ou lá é indiferente.
const TIPOS_CADASTRO = [
  { id: "sanitario", label: "Sanitário", desc: "Curativo (cronograma de dias) ou Preventivo (calendário sanitário — regra recorrente)" },
  { id: "iatf", label: "IATF", desc: "Hormônios em dias livres (D0/D7/D9 ou outro espaçamento)" },
  { id: "inducao", label: "Indução de lactação", desc: "Medicamento, implante e manejo por dia" },
  { id: "customizado", label: "Customizado", desc: "Roteiro livre de etapas, para qualquer rotina" },
  { id: "lida", label: "Lida", desc: "Trabalho da fazenda que não é protocolo de animal — por período ou frequência" },
] as const;
type TipoCadastro = typeof TIPOS_CADASTRO[number]["id"];

// Sanitário se divide em dois sub-cards: Curativo (cronograma de etapas de
// dias fixos, D0/D1/D2…) e Preventivo (o Calendário Sanitário — regra
// recorrente por frequência ou por evento de vida, ver FormCalendarioSanitario).
// São modelos de dados bem diferentes — por isso viram sub-abas, não um
// campo a mais no mesmo formulário.
const SUBS_SANITARIO = [
  { id: "curativo", label: "Curativo", desc: "Cronograma de etapas em dias fixos (D0/D1/D2…)" },
  { id: "preventivo", label: "Preventivo", desc: "Calendário sanitário — regra recorrente (frequência ou evento de vida)" },
] as const;
type SubSanitario = typeof SUBS_SANITARIO[number]["id"];

function CadastroTab({ estoque }: { estoque: EstoqueItem[] }) {
  const [tipo, setTipo] = useState<TipoCadastro>("sanitario");
  const [subSanitario, setSubSanitario] = useState<SubSanitario>("curativo");
  // Atalho vindo de fora (ex.: "Editar" no calendário sanitário, em Sanidade)
  // — abre direto em Sanitário > Preventivo.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    const tipoQs = qs.get("tipo");
    if (tipoQs && TIPOS_CADASTRO.some((t) => t.id === tipoQs)) setTipo(tipoQs as TipoCadastro);
    const subQs = qs.get("sub");
    if (subQs && SUBS_SANITARIO.some((s) => s.id === subQs)) setSubSanitario(subQs as SubSanitario);
  }, []);

  return (
    <div>
      <SeletorTipoProtocolo titulo="Do que se trata o protocolo?" tipos={TIPOS_CADASTRO} tipo={tipo} onChange={setTipo} />

      {tipo === "sanitario" && (
        <>
          <SeletorTipoProtocolo titulo="Curativo ou preventivo?" tipos={SUBS_SANITARIO} tipo={subSanitario} onChange={setSubSanitario} />
          {subSanitario === "curativo" && <CadastroProtocolosSanitarios />}
          {subSanitario === "preventivo" && <FormCalendarioSanitario estoque={estoque} />}
        </>
      )}
      {tipo === "iatf" && <CadastroIatf />}
      {tipo === "inducao" && <CadastroProtocolosInducao />}
      {tipo === "customizado" && <CadastroProtocolosCustomizados />}
      {tipo === "lida" && <CadastroLida />}
    </div>
  );
}

// ─────────────────────────── Aba Lançamento ───────────────────────────
// Os 4 tipos lançam AQUI também — não só em Lançamentos. É redundância
// proposital (o mesmo pedido que já valeu para os cards do app: IATF em
// Reprodutivo E em Protocolos, Sanitário em Sanidade E em Protocolos): a
// Central de Protocolos deve resolver o dia a dia sozinha, sem o usuário
// precisar saber que IATF "mora" em outra tela. Os TRÊS que já existiam em
// Lançamentos são os MESMOS COMPONENTES usados lá — mesmo formulário, mesmo
// endpoint; lançar aqui ou lá é o idêntico lançamento, só muda o caminho até
// a tela. Só o Customizado nasce exclusivamente aqui (nunca existiu em
// Lançamentos, e não faz sentido duplicar essa é a única exceção).
const TIPOS_LANCAMENTO = [
  { id: "sanitario", label: "Sanitário", desc: "Aplicar um protocolo cadastrado a um animal" },
  { id: "iatf", label: "IATF", desc: "Hormônios num lote — molde de dias livres ou digitado na hora" },
  { id: "inducao", label: "Indução de lactação", desc: "Cronograma completo, com baixa de estoque" },
  { id: "customizado", label: "Customizado", desc: "Roteiro livre, por matriz(es) ou tarefa da fazenda" },
  { id: "lida", label: "Lida", desc: "Tarefa geral da fazenda, por período ou por frequência" },
] as const;
type TipoLancamento = typeof TIPOS_LANCAMENTO[number]["id"];

function LancamentoTab({ animais, estoque }: { animais: AnimalRow[]; estoque: EstoqueItem[] }) {
  const [tipo, setTipo] = useState<TipoLancamento>("sanitario");

  return (
    <div>
      <SeletorTipoProtocolo titulo="Qual protocolo você quer lançar?" tipos={TIPOS_LANCAMENTO} tipo={tipo} onChange={setTipo} />

      <div className="card mb-3">
        <div className="card-header mb-2">Lançar {TIPOS_LANCAMENTO.find((t) => t.id === tipo)?.label.toLowerCase()}</div>
        {tipo === "iatf" && <FormProtocoloIatf animais={animais} />}
        {tipo === "inducao" && <FormInducaoLactacao animais={animais} />}
        {tipo === "sanitario" && <FormProtocoloSanitario animais={animais} estoque={estoque} />}
        {tipo === "customizado" && <FormProtocoloCustomizado animais={animais as any} />}
        {tipo === "lida" && <FormLida animais={animais as any} />}
      </div>

      <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
        {tipo === "customizado" || tipo === "lida"
          ? `${TIPOS_LANCAMENTO.find((t) => t.id === tipo)?.label} só é lançado aqui — não existe em Lançamentos.`
          : "Mesmo lançamento de Lançamentos — lance aqui ou lá, dá no mesmo registro."}
      </p>
    </div>
  );
}

// ───────────────── Detalhe de um lançamento: a grade animal × dia ─────────────────
//
// É esta tela que fecha o ciclo do protocolo. Até 08/2026 a Agenda era o
// ÚNICO lugar do sistema capaz de gravar "etapa realizada", e ela escondia a
// etapa cujo dia já tinha passado — protocolo que perdia o dia travava em "em
// andamento" para sempre. Aqui a baixa é possível a qualquer momento, com a
// data REAL da aplicação, e o que acabou antes do fim pode ser encerrado.
const COR_ESTADO: Record<string, string> = {
  realizada: "var(--green-light)", atrasada: "var(--red)", pendente: "var(--text-muted)",
};
const LABEL_STATUS: Record<string, string> = {
  concluido: "Concluído", encerrado: "Encerrado", cancelado: "Cancelado", ativo: "Ativo",
};

function DetalheProtocolo({ origem, origemId, onFechar, onMudou }: {
  origem: string; origemId: number; onFechar: () => void; onMudou: () => void;
}) {
  const [det, setDet] = useState<DetalheCentralProtocolo | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  // Dia escolhido para dar baixa + a data real da aplicação. A data começa na
  // data PREVISTA do dia, não em hoje: quem aplicou no dia certo e só está
  // registrando agora só precisa confirmar.
  const [diaBaixa, setDiaBaixa] = useState<number | null>(null);
  const [dataBaixa, setDataBaixa] = useState("");
  const [animaisBaixa, setAnimaisBaixa] = useState<string[]>([]);
  const [encerrando, setEncerrando] = useState(false);
  const [cancelando, setCancelando] = useState(false);
  const [motivo, setMotivo] = useState("");
  // IATF e Indução: qual medicamento/frasco foi escolhido em cada hormônio do
  // dia em baixa — dia → índice do hormônio → índice da opção escolhida em
  // `h.opcoes` (não o estoque_id: com "incluir mesmo sem estoque" ligado,
  // várias opções podem ter estoque_id null). Mesma lógica da Agenda (ver
  // medIatf em app/agenda/page.tsx).
  const [medSelecionado, setMedSelecionado] = useState<Record<number, Record<number, number | "">>>({});
  // Toggle "incluir todos os medicamentos/hormônios, inclusive sem estoque":
  // expande as opções do picker além dos frascos já em Estoque, listando
  // toda marca comercial cadastrada do mesmo princípio ativo — dá liberdade
  // de flagar o que realmente foi usado mesmo sem frasco cadastrado.
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  // G16 — bloco "Editar" (data de início/responsável/observação/nome), no
  // lugar do antigo botão "Renomear" (só o nome). `observacao` não vem
  // tipada em DetalheCentralProtocolo (frontend/lib/api.ts é terreno do
  // Agente 0, fora da fronteira deste agente) — o backend passou a devolvê-la
  // mesmo assim (ver central_protocolos.detalhe), acessada aqui via `any`.
  const [editando, setEditando] = useState(false);
  const [editForm, setEditForm] = useState({ data_inicio: "", responsavel: "", observacao: "", nome: "" });
  const [desfazerAlvo, setDesfazerAlvo] = useState<{ dia: number; numero_matriz: string; rotulo: string } | null>(null);
  const [desfazendo, setDesfazendo] = useState(false);

  const carregar = () => fetchDetalheProtocolo(origem, origemId, incluirSemEstoque).then(setDet).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [origem, origemId, incluirSemEstoque]);

  function abrirBaixa(dia: number) {
    const d = det?.dias.find((x) => x.dia === dia);
    const hoje = new Date().toISOString().slice(0, 10);
    setDiaBaixa(dia);
    // Nunca propõe data futura: protocolo em dia sugere hoje, atrasado sugere
    // o dia previsto.
    setDataBaixa(d && d.data_prevista < hoje ? d.data_prevista : hoje);
    setAnimaisBaixa(
      (det?.animais || [])
        .filter((a) => a.celulas.some((c) => c.dia === dia && !c.realizada))
        .map((a) => a.numero_matriz),
    );
    setMedSelecionado((p) => ({ ...p, [dia]: {} }));
    setAviso(null);
  }

  const hormoniosDoDiaBaixa = (origem === "iatf" || origem === "inducao") && diaBaixa != null
    ? det?.dias.find((d) => d.dia === diaBaixa)?.hormonios || []
    : [];

  async function confirmarBaixa() {
    if (diaBaixa == null) return;
    setSalvando(true); setErro(null);
    try {
      const pendentes = (det?.animais || []).filter((a) => a.celulas.some((c) => c.dia === diaBaixa && !c.realizada));
      const todos = animaisBaixa.length === pendentes.length;
      // IATF e Indução: monta `medicamentos` a partir dos hormônios do dia +
      // o frasco escolhido em medSelecionado (índice em h.opcoes) — mesmo
      // mapeamento que a Agenda já faz (marcarRealizado em app/agenda/page.tsx).
      // Sem hormônios cadastrados (protocolo ad-hoc, ou D11/inseminação), não
      // manda nada — mesmo comportamento de antes (backend cai nos
      // medicamentos cadastrados no lançamento).
      let medicamentos: MedicamentoIatf[] | undefined;
      if ((origem === "iatf" || origem === "inducao") && hormoniosDoDiaBaixa.length) {
        const sel = medSelecionado[diaBaixa] || {};
        medicamentos = hormoniosDoDiaBaixa.map((h, idx) => {
          const optIdx = sel[idx] ?? (h.opcoes?.length === 1 ? 0 : "");
          const opcao = optIdx === "" ? undefined : h.opcoes?.[optIdx];
          return {
            produto: opcao?.nome ?? h.produto, estoque_id: opcao?.estoque_id ?? undefined,
            dose: h.dose, unidade: h.unidade, via: h.via,
          };
        }).filter((m) => m.produto);
      }
      const r = await darBaixaProtocolo(origem, origemId, {
        dia: diaBaixa,
        animais: todos ? null : animaisBaixa,
        data_realizacao: dataBaixa || null,
        medicamentos,
      });
      setDiaBaixa(null);
      setAviso(r.avisos?.length ? r.avisos.join(" ") : "Baixa registrada.");
      await carregar(); onMudou();
    } catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  }

  async function confirmarEditar() {
    if (!det) return;
    setSalvando(true); setErro(null);
    try {
      // "nome" só entra no payload se o usuário de fato mexeu nele — o
      // backend só regrava o nome auto-gerado (data nova no lugar da antiga)
      // quando "nome" NÃO vem na requisição; mandar sempre, mesmo sem
      // mudança, desligaria essa regravação automática ao mudar a data.
      const dados: Parameters<typeof editarLancamentoProtocolo>[2] = {
        data_inicio: editForm.data_inicio || undefined,
        responsavel: editForm.responsavel,
        observacao: editForm.observacao,
      };
      const nomeAtual = editForm.nome.trim();
      if (nomeAtual && nomeAtual !== det.nome) dados.nome = nomeAtual;
      const r = await editarLancamentoProtocolo(origem, origemId, dados);
      setEditando(false);
      setAviso(r.avisos?.length ? r.avisos.join(" ") : "Protocolo atualizado.");
      await carregar(); onMudou();
    } catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  }

  async function confirmarDesfazer() {
    if (!desfazerAlvo) return;
    setDesfazendo(true); setErro(null);
    try {
      const r = await desfazerAplicacao(origem, origemId, desfazerAlvo.dia, desfazerAlvo.numero_matriz);
      setAviso(r.avisos?.length ? r.avisos.join(" ") : "Aplicação desfeita.");
      setDesfazerAlvo(null);
      await carregar(); onMudou();
    } catch (e: any) { setErro(e.message); }
    finally { setDesfazendo(false); }
  }

  async function confirmarEncerrar() {
    setSalvando(true); setErro(null);
    try {
      await encerrarProtocolo(origem, origemId, motivo);
      setEncerrando(false); setMotivo("");
      await carregar(); onMudou();
    } catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  }

  async function confirmarCancelar() {
    setSalvando(true); setErro(null);
    try {
      const r = await cancelarProtocolo(origem, origemId, motivo);
      setCancelando(false); setMotivo("");
      setAviso(r.avisos?.length ? r.avisos.join(" ") : "Protocolo cancelado e estoque estornado.");
      await carregar(); onMudou();
    } catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  }

  async function confirmarReabrir() {
    setSalvando(true); setErro(null);
    try { await reabrirProtocolo(origem, origemId); await carregar(); onMudou(); }
    catch (e: any) { setErro(e.message); }
    finally { setSalvando(false); }
  }

  if (erro && !det) return <Modal title="Protocolo" onClose={onFechar}><p style={{ color: "var(--red)" }}>{erro}</p></Modal>;
  if (!det) return <Modal title="Protocolo" onClose={onFechar}><p style={{ color: "var(--text-muted)" }}>Carregando…</p></Modal>;

  const pendentesDoDia = diaBaixa == null ? [] :
    det.animais.filter((a) => a.celulas.some((c) => c.dia === diaBaixa && !c.realizada));

  return (
    <Modal title={det.nome} onClose={onFechar} width="960px">
      <div className="flex items-center gap-4 mb-3" style={{ flexWrap: "wrap", fontSize: "0.82rem" }}>
        <span><strong>{det.etapas_realizadas}</strong> de {det.etapas_total} etapas</span>
        {det.etapas_atrasadas > 0 && <span style={{ color: "var(--red)", fontWeight: 600 }}>{det.etapas_atrasadas} atrasada(s)</span>}
        <span style={{ color: "var(--text-muted)" }}>{det.animais.length} animal(is)</span>
        {det.responsavel && <span style={{ color: "var(--text-muted)" }}>Responsável: {det.responsavel}</span>}
        {det.encerrado_em && (
          <span style={{ color: "var(--amber)", fontWeight: 600 }}>
            Encerrado em {formatDate(det.encerrado_em)}{det.encerrado_motivo ? ` — ${det.encerrado_motivo}` : ""}
          </span>
        )}
      </div>

      {erro && <div className="alert-critico mb-3"><span>{erro}</span></div>}
      {aviso && (
        <p className="mb-3" style={{ color: "var(--green-light)", fontSize: "0.82rem", fontWeight: 600 }}>{aviso}</p>
      )}

      {editando ? (
        <div className="mb-3" style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.8rem" }}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
            <div><label style={labelStyle}>Data de início</label>
              <input type="date" style={inputStyle} value={editForm.data_inicio}
                     onChange={(e) => setEditForm((f) => ({ ...f, data_inicio: e.target.value }))} /></div>
            <div><label style={labelStyle}>Responsável</label>
              <input style={inputStyle} value={editForm.responsavel}
                     onChange={(e) => setEditForm((f) => ({ ...f, responsavel: e.target.value }))} /></div>
            <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Observação</label>
              <input style={inputStyle} value={editForm.observacao}
                     onChange={(e) => setEditForm((f) => ({ ...f, observacao: e.target.value }))} /></div>
            <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Nome</label>
              <input style={inputStyle} value={editForm.nome}
                     onChange={(e) => setEditForm((f) => ({ ...f, nome: e.target.value }))} placeholder="Nome do protocolo" /></div>
          </div>
          <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
            Mudar a data de início desloca todas as datas previstas das aplicações pelo mesmo intervalo —
            bloqueado se alguma etapa já tiver sido aplicada.
          </p>
          <div className="flex items-center gap-2">
            <button className="btn-primary" style={{ fontSize: "0.78rem" }} onClick={confirmarEditar} disabled={salvando}>
              Salvar
            </button>
            <button className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={() => setEditando(false)}>Cancelar</button>
          </div>
        </div>
      ) : (
        <button className="btn-ghost mb-2" style={{ fontSize: "0.74rem" }}
                onClick={() => {
                  setEditForm({
                    data_inicio: det.data_inicio || "", responsavel: det.responsavel || "",
                    observacao: (det as any).observacao || "", nome: det.nome,
                  });
                  setEditando(true);
                }}>
          Editar
        </button>
      )}

      <div className="overflow-x-auto">
        <table className="fazenda-table">
          <thead><tr>
            <th>Animal</th>
            {det.dias.map((d) => (
              <th key={d.dia} style={{ textAlign: "center", whiteSpace: "nowrap" }}>
                {d.rotulo}<br />
                <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>{formatDate(d.data_prevista)}</span>
              </th>
            ))}
          </tr></thead>
          <tbody>
            {det.animais.map((a) => (
              <tr key={a.numero_matriz}>
                <td style={{ fontWeight: 600, fontSize: "0.82rem" }}>{a.numero_matriz}</td>
                {a.celulas.map((c) => (
                  <td key={c.dia} style={{ textAlign: "center", cursor: c.realizada ? "pointer" : "default" }}
                      onClick={c.realizada ? () => setDesfazerAlvo({ dia: c.dia, numero_matriz: a.numero_matriz, rotulo: c.rotulo }) : undefined}
                      title={c.realizada
                        ? `Aplicada em ${c.data_realizacao ? formatDate(c.data_realizacao) : "?"} — clique para desfazer só esta aplicação`
                        : `Prevista para ${formatDate(c.data_prevista)}`}>
                    <span style={{ color: COR_ESTADO[c.estado], fontWeight: 700 }}>
                      {c.realizada ? "✓" : c.estado === "atrasada" ? "!" : "·"}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
        <span style={{ color: "var(--green-light)", fontWeight: 700 }}>✓</span> aplicada (clique para desfazer) ·{" "}
        <span style={{ color: "var(--red)", fontWeight: 700 }}>!</span> atrasada ·{" "}
        <span style={{ fontWeight: 700 }}>·</span> a vencer
      </p>

      {desfazerAlvo && (
        <div className="card mt-2" style={{ background: "var(--surface-2)", border: "1px solid var(--red)" }}>
          <p style={{ fontSize: "0.82rem", marginBottom: "0.5rem" }}>
            Desfazer a aplicação de <strong>{desfazerAlvo.numero_matriz}</strong> em <strong>{desfazerAlvo.rotulo}</strong>?
            {origem === "iatf" && " O estoque consumido por esta vaca é estornado; a Sanidade já registrada na ficha permanece."}
          </p>
          <div className="flex gap-2">
            <button className="btn-primary" style={{ background: "var(--red)" }} onClick={confirmarDesfazer} disabled={desfazendo}>
              {desfazendo ? "Desfazendo…" : "Sim, desfazer"}
            </button>
            <button className="btn-ghost" onClick={() => setDesfazerAlvo(null)} disabled={desfazendo}>Não</button>
          </div>
        </div>
      )}

      {!det.encerrado_em && det.etapas_realizadas < det.etapas_total && (
        <div className="mt-3">
          <label style={labelStyle}>Dar baixa de um dia</label>
          <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
            {det.dias.filter((d) => d.realizadas < d.total).map((d) => (
              <button key={d.dia} type="button" className="btn-ghost" style={{ fontSize: "0.78rem" }}
                      onClick={() => abrirBaixa(d.dia)}>
                {d.rotulo} — faltam {d.total - d.realizadas}
              </button>
            ))}
          </div>
        </div>
      )}

      {diaBaixa != null && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label style={labelStyle}>Em que dia foi aplicado?</label>
              <input type="date" style={inputStyle} value={dataBaixa} max={new Date().toISOString().slice(0, 10)}
                     onChange={(e) => setDataBaixa(e.target.value)} />
              <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                A data real da aplicação — é ela que vai para a ficha do animal, não a data de hoje.
              </p>
            </div>
            <div>
              <label style={labelStyle}>Animais ({animaisBaixa.length} de {pendentesDoDia.length})</label>
              <div style={{ maxHeight: 140, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 6, padding: "0.4rem" }}>
                {pendentesDoDia.map((a) => (
                  <label key={a.numero_matriz} className="flex items-center gap-2" style={{ fontSize: "0.8rem", padding: "0.1rem 0" }}>
                    <input type="checkbox" checked={animaisBaixa.includes(a.numero_matriz)}
                           onChange={(e) => setAnimaisBaixa((p) => e.target.checked
                             ? [...p, a.numero_matriz] : p.filter((n) => n !== a.numero_matriz))} />
                    {a.numero_matriz}
                  </label>
                ))}
              </div>
            </div>
          </div>
          {hormoniosDoDiaBaixa.length > 0 && (
            <div style={{ marginTop: "0.6rem", background: "var(--surface)", border: "1px solid var(--dourado)", borderRadius: 8, padding: "0.55rem 0.7rem" }}>
              <div className="flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.4rem", marginBottom: "0.35rem" }}>
                <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "var(--dourado-light)" }}>
                  Qual medicamento/frasco você está usando?
                </div>
                <label className="flex items-center gap-2" style={{ fontSize: "0.7rem", color: "var(--text-muted)", cursor: "pointer" }}>
                  <input type="checkbox" checked={incluirSemEstoque}
                         onChange={(ev) => setIncluirSemEstoque(ev.target.checked)} />
                  Incluir todos os medicamentos/hormônios (inclusive sem estoque)
                </label>
              </div>
              {hormoniosDoDiaBaixa.map((h, idx) => {
                const sel = medSelecionado[diaBaixa!]?.[idx] ?? (h.opcoes?.length === 1 ? 0 : "");
                return (
                  <div key={idx} className="flex items-center gap-2" style={{ marginBottom: "0.3rem", flexWrap: "wrap" }}>
                    <span style={{ fontSize: "0.76rem", minWidth: 130 }}>
                      {h.produto}{h.dose ? ` · ${h.dose}${h.unidade || ""}` : ""}
                    </span>
                    {(h.opcoes?.length ?? 0) === 0 ? (
                      <span style={{ fontSize: "0.72rem", color: "var(--amber)" }}>
                        Sem medicamento em estoque para este princípio.
                        {!incluirSemEstoque && " Marque \"incluir mesmo sem estoque\" para flagar o que foi usado."}
                      </span>
                    ) : (
                      <select style={{ width: "auto", minWidth: 220, fontSize: "0.76rem", padding: "0.3rem 0.5rem", borderRadius: 6, background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
                              value={sel}
                              onChange={(ev) => setMedSelecionado((p) => ({
                                ...p, [diaBaixa!]: { ...(p[diaBaixa!] || {}), [idx]: ev.target.value === "" ? "" : Number(ev.target.value) },
                              }))}>
                        <option value="">Selecione o frasco…</option>
                        {h.opcoes.map((o, oi) => (
                          <option key={oi} value={oi}>
                            {o.nome}{o.marca ? ` · ${o.marca}` : ""}
                            {o.sem_estoque ? " — sem frasco em estoque" : ` — saldo ${o.saldo} ${o.unidade || ""}${!o.estoque_inicializado ? " (sem estoque inicial)" : ""}`}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <div className="flex gap-2 mt-3">
            <button className="btn-primary" onClick={confirmarBaixa} disabled={salvando || !animaisBaixa.length}>
              {salvando ? "Salvando…" : "Confirmar baixa"}
            </button>
            <button className="btn-ghost" onClick={() => setDiaBaixa(null)}>Cancelar</button>
          </div>
        </div>
      )}

      <div className="flex gap-2 mt-4" style={{ flexWrap: "wrap" }}>
        <button className="btn-ghost" onClick={() => exportarFolhaCampoPDF(det)} title="Folha para imprimir e levar ao curral">
          <FileText size={13} /> Folha de campo (PDF)
        </button>
        <button className="btn-ghost" onClick={() => exportarFolhaCampoExcel(det)}>
          <FileSpreadsheet size={13} /> Excel
        </button>
        {det.encerrado_em ? (
          <button className="btn-ghost" onClick={confirmarReabrir} disabled={salvando}>Reabrir protocolo</button>
        ) : (
          <button className="btn-ghost" style={{ color: "var(--amber)" }} onClick={() => setEncerrando(true)} disabled={salvando}>
            Encerrar protocolo
          </button>
        )}
        {det.ativo && (
          <button className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => setCancelando(true)} disabled={salvando}>
            Cancelar protocolo
          </button>
        )}
      </div>

      {cancelando && (
        <div className="card mt-2" style={{ background: "var(--surface-2)", border: "1px solid var(--red)" }}>
          <p style={{ fontSize: "0.82rem", marginBottom: "0.5rem" }}>
            Cancelar é para o lançamento que <strong>não deveria ter existido</strong> — diferente de encerrar.
            As {det.etapas_realizadas} aplicação(ões) já registrada(s) voltam a “não realizadas” e{" "}
            <strong>o estoque consumido é devolvido</strong>. O registro na ficha do animal permanece:
            o produto entrou nele, e isso não se reescreve.
          </p>
          <label style={labelStyle}>Motivo (opcional)</label>
          <input style={inputStyle} value={motivo} onChange={(e) => setMotivo(e.target.value)}
                 placeholder="ex.: lançado no lote errado, duplicado" />
          <div className="flex gap-2 mt-2">
            <button className="btn-primary" style={{ background: "var(--red)" }} onClick={confirmarCancelar} disabled={salvando}>
              Cancelar protocolo e estornar
            </button>
            <button className="btn-ghost" onClick={() => setCancelando(false)}>Voltar</button>
          </div>
        </div>
      )}

      {encerrando && (
        <div className="card mt-2" style={{ background: "var(--surface-2)" }}>
          <p style={{ fontSize: "0.82rem", marginBottom: "0.5rem" }}>
            Encerrar tira o protocolo da Agenda e do Acompanhamento. As{" "}
            <strong>{det.etapas_total - det.etapas_realizadas} etapa(s) que faltam continuam registradas como não aplicadas</strong> —
            encerrar não é dar por feito o que não foi feito.
          </p>
          <label style={labelStyle}>Motivo (opcional)</label>
          <input style={inputStyle} value={motivo} onChange={(e) => setMotivo(e.target.value)}
                 placeholder="ex.: lote vendido, vaca morreu, protocolo interrompido" />
          <div className="flex gap-2 mt-2">
            <button className="btn-primary" onClick={confirmarEncerrar} disabled={salvando}>Encerrar</button>
            <button className="btn-ghost" onClick={() => setEncerrando(false)}>Cancelar</button>
          </div>
        </div>
      )}
    </Modal>
  );
}

// ─────────────────────────── Abas Acompanhamento / Histórico ───────────────────────────
const COLUNAS_EXPORT: ColunaExport[] = [
  { header: "Protocolo", key: "nome" }, { header: "Tipo", key: "tipoLabel" },
  { header: "Início", key: "inicioFmt" }, { header: "Fim", key: "fimFmt" },
  { header: "Etapas", key: "etapasLabel" }, { header: "Animais", key: "animais" }, { header: "Status", key: "status" },
];

// Cards de origem — mesmo desenho do seletor de Lançamento, para achar
// visualmente parecido. Filtra por ORIGEM (sanitário/IATF/indução/
// customizado/lida), não pela categoria produtivo/reprodutivo/sanitário
// que o backend usa em `tipo` — essa distinção fica só no client, a lista
// completa já vem do endpoint (o campo de busca por nome ainda vai ao
// backend, já que esse sim é decidido lá).
const TIPOS_ACOMPANHAMENTO = [
  { id: "", label: "Todos", desc: "Todos os protocolos" },
  { id: "sanitario", label: "Sanitário", desc: "Curativo ou preventivo" },
  { id: "iatf", label: "IATF", desc: "Hormônios em lote" },
  { id: "inducao", label: "Indução de lactação", desc: "Cronograma com baixa de estoque" },
  { id: "customizado", label: "Customizado", desc: "Roteiro livre" },
  { id: "lida", label: "Lida", desc: "Tarefa geral da fazenda" },
] as const;
export type OrigemAcompanhamento = typeof TIPOS_ACOMPANHAMENTO[number]["id"];

// `origemFixa` — reaproveitada por Histórico > Produção para a aba "Indução
// de lactação" (ver app/producao/page.tsx::HistoricoInducaoLactacao):
// mesma lista/exportação/detalhe de sempre, só travando o filtro de origem
// e escondendo o seletor (redundante quando a própria aba já diz qual é).
export function ListaProtocolos({ historico, origemFixa }: { historico: boolean; origemFixa?: OrigemAcompanhamento }) {
  const [linhas, setLinhas] = useState<LinhaCentralProtocolos[] | null>(null);
  const [nome, setNome] = useState("");
  const [origem, setOrigem] = useState<OrigemAcompanhamento>(origemFixa ?? "");
  const [erro, setErro] = useState<string | null>(null);
  const [aberto, setAberto] = useState<{ origem: string; id: number } | null>(null);
  const [recarga, setRecarga] = useState(0);
  // Nomes já usados (sem o filtro de nome, senão a lista de sugestões encolhe
  // conforme a pessoa digita) — vira o <datalist> da busca, pra sugerir os
  // protocolos existentes em vez de depender só de texto livre.
  const [nomesConhecidos, setNomesConhecidos] = useState<string[]>([]);
  const datalistId = useId();

  useEffect(() => {
    const fetcher = historico ? fetchCentralProtocolosHistorico : fetchCentralProtocolosAcompanhamento;
    fetcher({ nome: nome || undefined })
      .then(setLinhas).catch((e) => setErro(e.message));
  }, [nome, historico, recarga]);

  useEffect(() => {
    const fetcher = historico ? fetchCentralProtocolosHistorico : fetchCentralProtocolosAcompanhamento;
    fetcher()
      .then((ls) => {
        const doTipo = origemFixa ? ls.filter((l) => l.origem === origemFixa) : ls;
        setNomesConhecidos(Array.from(new Set(doTipo.map((l) => l.nome))).sort((a, b) => a.localeCompare(b)));
      })
      .catch(() => {});
  }, [historico, origemFixa, recarga]);

  const linhasFiltradas = useMemo(
    () => (linhas || []).filter((l) => !origem || l.origem === origem),
    [linhas, origem],
  );

  const linhasExport = useMemo(() => linhasFiltradas.map((l) => ({
    nome: l.nome, tipoLabel: LABEL_TIPO[l.tipo] || l.tipo,
    inicioFmt: formatDate(l.data_inicio), fimFmt: formatDate(l.data_fim),
    etapasLabel: `${l.etapas_realizadas}/${l.etapas_total}`, animais: l.animais,
    status: LABEL_STATUS[l.status] || l.status,
  })), [linhasFiltradas]);

  return (
    <div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      <div className="mb-3">
        <label style={labelStyle}>Buscar por nome do protocolo</label>
        <input style={inputStyle} list={datalistId} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="ex.: mastite, IATF…" />
        <datalist id={datalistId}>
          {nomesConhecidos.map((n) => <option key={n} value={n} />)}
        </datalist>
      </div>

      {!origemFixa && <SeletorTipoProtocolo titulo="Filtrar por protocolo" tipos={TIPOS_ACOMPANHAMENTO} tipo={origem} onChange={setOrigem} />}

      {erro && <div className="alert-critico mb-3"><span>Sem dados: {erro}.</span></div>}
      {linhas && (
        <div className="flex items-center justify-between mb-2">
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{linhasFiltradas.length} protocolo(s)</span>
          {historico && <ExportarBotoes titulo="Central de Protocolos — Histórico" nomeArquivoBase="central_protocolos_historico" colunas={COLUNAS_EXPORT} linhas={linhasExport} />}
        </div>
      )}
      </div>

      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      {!linhas ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : (
        <>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr>
                <th>Protocolo</th><th>Tipo</th><th>Início</th><th>Fim</th><th>Etapas</th><th>Animais</th><th>Status</th>
              </tr></thead>
              <tbody>
                {linhasFiltradas.map((l) => {
                  // Sanitário é lançado por animal e na Central aparece só
                  // agrupado para exibição — abrir a grade dele exigiria
                  // decidir o que fazer com o grupo inteiro. Segue pela Agenda.
                  const abrivel = l.origem !== "sanitario";
                  return (
                  <tr key={`${l.origem}-${l.origem_id}`}
                      onClick={abrivel ? () => setAberto({ origem: l.origem, id: l.origem_id }) : undefined}
                      style={abrivel ? { cursor: "pointer" } : undefined}
                      title={abrivel ? "Abrir a grade animal × dia, dar baixa e encerrar" : "Protocolo sanitário: baixa pela Agenda"}>
                    <td style={{ fontWeight: 600, fontSize: "0.82rem" }}>{l.nome}</td>
                    <td><Pill cor={COR_TIPO[l.tipo]}>{LABEL_TIPO[l.tipo] || l.tipo}</Pill></td>
                    <td style={{ fontSize: "0.78rem" }}>{formatDate(l.data_inicio)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{formatDate(l.data_fim)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{l.etapas_realizadas}/{l.etapas_total}{!historico ? ` (faltam ${l.etapas_faltam})` : ""}</td>
                    <td style={{ fontSize: "0.78rem" }}>{l.animais || "—"}</td>
                    <td>
                      {l.status === "concluido" ? <span style={{ color: "var(--green-light)" }}>Concluído</span>
                        : l.status === "cancelado" ? <span style={{ color: "var(--red)" }}>Cancelado</span>
                        : l.status === "encerrado" ? <span style={{ color: "var(--amber)" }} title={l.encerrado_motivo || undefined}>Encerrado</span>
                        : <span style={{ color: "var(--dourado-light)" }}>Ativo</span>}
                    </td>
                  </tr>
                  );
                })}
                {!linhasFiltradas.length && (
                  <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo {historico ? "concluído" : "ativo"} para os filtros escolhidos.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
      </div>
      </div>

      {aberto && (
        <DetalheProtocolo origem={aberto.origem} origemId={aberto.id}
                          onFechar={() => setAberto(null)} onMudou={() => setRecarga((n) => n + 1)} />
      )}
    </div>
  );
}

// ─────────────────────────── Página ───────────────────────────
export default function ProtocolosPage() {
  const [aba, setAba] = useState<"cadastro" | "lancamento" | "acompanhamento" | "historico">("acompanhamento");
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [estoque, setEstoque] = useState<EstoqueItem[]>([]);
  useEffect(() => {
    fetchAnimais().then(setAnimais).catch(() => {});
    fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {});
  }, []);
  // Atalho vindo de fora (ex.: "Editar" no calendário sanitário, em Sanidade,
  // ou no relatório de Exclusão) — só escolhe a aba certa; a Central de
  // Protocolos não permite pular direto para uma regra específica, mesmo
  // padrão do "ir=" de Lançamentos.
  useEffect(() => {
    const abaQs = new URLSearchParams(window.location.search).get("aba");
    if (abaQs && ["cadastro", "lancamento", "acompanhamento", "historico"].includes(abaQs)) setAba(abaQs as typeof aba);
  }, []);

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold mb-1" style={{ color: "var(--dourado-light)" }}>Central de Protocolos</h1>
      <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginBottom: "1.2rem" }}>
        IATF, Sanitário, Indução de Lactação e Customizado — cadastro, lançamento, acompanhamento e histórico num só lugar.
        Os 4 tipos podem ser lançados por aqui; IATF, Indução e Sanitário continuam também disponíveis em Lançamentos — é o mesmo lançamento, dois caminhos.
      </p>

      <TabBar<"cadastro" | "lancamento" | "acompanhamento" | "historico">
        abas={[
          { id: "cadastro", label: "Cadastro", title: "Moldes de cada protocolo" },
          { id: "lancamento", label: "Lançamento", title: "Lançar IATF, indução, sanitário ou customizado" },
          { id: "acompanhamento", label: "Acompanhamento", title: "Protocolos em andamento, dos 4 tipos" },
          { id: "historico", label: "Histórico", title: "Concluídos e cancelados, com exportação" },
        ]}
        ativa={aba}
        onChange={setAba}
      />

      {aba === "cadastro" && <CadastroTab estoque={estoque} />}
      {aba === "lancamento" && <LancamentoTab animais={animais} estoque={estoque} />}
      {aba === "acompanhamento" && <ListaProtocolos historico={false} />}
      {aba === "historico" && <ListaProtocolos historico />}
    </div>
  );
}
