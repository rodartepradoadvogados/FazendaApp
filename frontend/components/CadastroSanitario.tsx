"use client";
import { Fragment, useEffect, useRef, useState } from "react";
import { Syringe, Bug, CalendarClock, ClipboardList, FlaskConical, Plus, Pencil, AlertTriangle, Check, X, Trash2, Search, ChevronDown, ChevronRight, Upload, Download, Milk } from "lucide-react";
import {
  fetchPrincipiosAtivos, restaurarCatalogoPrincipios,
  fetchFarmaciaPrincipios, fetchFarmaciaDetalhe, criarPrincipioFarmacia, atualizarPrincipioFarmacia,
  criarMarcaFarmacia, excluirMarcaFarmacia,
  fetchDoencas, criarDoenca, atualizarDoenca,
  fetchEventosSanitarios, criarEventoSanitario, atualizarEventoSanitario,
  fetchExames, criarExame, atualizarExame, excluirExame,
  fetchProtocolosSanitarios, criarProtocoloSanitario, atualizarProtocoloSanitario, excluirProtocoloSanitario, importarProtocoloSanitarioExcel,
  fetchProtocolosInducaoLactacaoCadastro, criarProtocoloInducaoLactacao, atualizarProtocoloInducaoLactacao,
  fetchEstoque, fetchLotes,
  fetchIndicacoes, criarIndicacao, excluirIndicacao,
  fetchServicosCadastro,
  type ProtocoloEtapa, type EventoSanitarioPayload, type ExameDefinicaoPayload, type PrincipioFarmacia, type MarcaComercial, type IndicacaoTerapeutica,
  type EtapaInducaoLactacao, type ProtocoloInducaoLactacaoCadastro, type ProtocoloInducaoLactacaoPayload,
} from "@/lib/api";
import { exportarExcel } from "@/lib/export";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { EstoquePicker, type EstoqueItemPicker } from "./EstoquePicker";
import { VIAS_APLICACAO } from "@/lib/constants";
import { CLASSIFICACOES_MEDICAMENTO } from "@/lib/api";

const CRITERIOS: [string, string][] = [
  ["medicamento", "Medicamento"],
  ["principio_ativo", "Princípio ativo"],
  ["doenca", "Doença"],
  ["classificacao", "Classificação"],
];

// Unidades para a etapa do protocolo — restringidas às compatíveis com a
// unidade de estoque do produto (para a baixa automática funcionar). Sem
// produto/estoque, oferece a lista padrão.
const UNIDADES_PADRAO = ["ml", "L", "unidade", "dose", "kg", "metro", "saca 30kg", "saca 60kg"];
const GRUPOS_UNIDADE = [["ml", "unidade", "dose"], ["L", "kg"]];
// Sinônimos/abreviações legadas (import de planilha, cadastro antigo) que
// precisam cair no mesmo grupo do valor canônico — senão o item some das
// opções de unidade compatível (ex.: "un" não batia com "unidade" e escondia "ml").
const SINONIMOS_UNIDADE: Record<string, string> = { un: "unidade", und: "unidade", unid: "unidade", unidades: "unidade" };
const unidadesCompat = (u?: string | null): string[] => {
  if (!u) return UNIDADES_PADRAO;
  const norm = SINONIMOS_UNIDADE[u.trim().toLowerCase()] || u;
  return GRUPOS_UNIDADE.find((g) => g.includes(norm)) || [u];
};

const ABAS = [
  ["principios", "Princípio ativo", Syringe],
  ["doencas", "Doença", Bug],
  ["eventos", "Evento sanitário", CalendarClock],
  ["protocolos", "Protocolo sanitário", ClipboardList],
  ["inducao", "Indução de lactação", Milk],
  ["exames", "Exames", FlaskConical],
] as const;
// Reexportado para o Cadastro compor a árvore de sub-navegação (Configurações
// › Cadastro › Sanitário › estas 4 abas) sem duplicar rótulos/ícones.
export type AbaCadastroSanitario = (typeof ABAS)[number][0];
export const ABAS_CADASTRO_SANITARIO = ABAS;

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const buscaInputStyle: React.CSSProperties = { width: "100%", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.5rem 0.75rem 0.5rem 2rem", fontSize: "0.85rem" };

// Normaliza texto para busca insensível a maiúsculas e acentos.
const normalizar = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

// Aceita controle externo (Cadastro precisa da aba ativa para compor a
// árvore de sub-navegação Configurações › Cadastro › Sanitário) — sem props,
// funciona como antes, com estado próprio.
export default function CadastroSanitario({ abaControlada, onAbaChange }: {
  abaControlada?: AbaCadastroSanitario; onAbaChange?: (id: AbaCadastroSanitario) => void;
} = {}) {
  const [abaInterna, setAbaInterna] = useState<AbaCadastroSanitario>("principios");
  const aba = abaControlada ?? abaInterna;
  const setAba = onAbaChange ?? setAbaInterna;

  return (
    <div>
      {aba === "principios" && <ListaPrincipiosAtivos />}
      {aba === "doencas" && (
        <ListaNomeAtivo
          titulo="Doenças" icone={Bug}
          descricao="O que cada evento do calendário sanitário visa combater."
          fetchFn={fetchDoencas} criarFn={criarDoenca} atualizarFn={atualizarDoenca}
          semRegistros="Nenhuma doença cadastrada ainda."
        />
      )}
      {aba === "eventos" && <CadastroEventosSanitarios />}
      {aba === "protocolos" && <CadastroProtocolosSanitarios />}
      {aba === "inducao" && <CadastroProtocolosInducao />}
      {aba === "exames" && <CadastroExames />}
    </div>
  );
}

type Protocolo = {
  id: number; nome: string; doenca_id: number | null; doenca_nome: string | null; eh_mastite: boolean; ativo: boolean;
  dia_inicial?: number;
  etapas: ProtocoloEtapa[];
};
type ProtocoloForm = { nome: string; doenca_id: string; eh_mastite: boolean; dia_inicial: number; ativo: boolean; etapas: ProtocoloEtapa[] };
const etapaVazia = (dia: number): ProtocoloEtapa => ({ dia, criterio_tipo: "medicamento", produto: "", dosagem: 0, unidade: "ml", via: "", observacao: "" });
// Protocolos novos nascem em D0 (mesmo padrão da indução de lactação); um
// protocolo já existente que veio com dia_inicial=1 (pré-padronização D0)
// mantém o próprio dia_inicial ao ser editado — ver abrirEdicao.
const protocoloFormVazio = (): ProtocoloForm => ({ nome: "", doenca_id: "", eh_mastite: false, dia_inicial: 0, ativo: true, etapas: [etapaVazia(0)] });

export function CadastroProtocolosSanitarios() {
  const [itens, setItens] = useState<Protocolo[] | null>(null);
  const [doencas, setDoencas] = useState<{ id: number; nome: string }[]>([]);
  const [estoque, setEstoque] = useState<EstoqueItemPicker[]>([]);
  const [principios, setPrincipios] = useState<{ id: number; nome: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<ProtocoloForm>(protocoloFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [importando, setImportando] = useState(false);
  const [msgImport, setMsgImport] = useState<{ erro: boolean; texto: string } | null>(null);
  const inputImportRef = useRef<HTMLInputElement>(null);
  const [excluindo, setExcluindo] = useState<number | null>(null);
  const [erroExclusao, setErroExclusao] = useState<string | null>(null);

  const carregar = () => fetchProtocolosSanitarios().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchDoencas().then(setDoencas).catch(() => {});
    fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {});
    fetchPrincipiosAtivos().then(setPrincipios).catch(() => {});
  }, []);

  const abrirNovo = () => { setForm(protocoloFormVazio()); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (p: Protocolo) => {
    setForm({
      nome: p.nome, doenca_id: p.doenca_id ? String(p.doenca_id) : "", eh_mastite: p.eh_mastite,
      dia_inicial: p.dia_inicial ?? 0, ativo: p.ativo,
      etapas: p.etapas.length ? p.etapas.map((e) => ({ ...e })) : [etapaVazia(p.dia_inicial ?? 0)],
    });
    setEditando(p.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  // Bloqueado no backend se o protocolo já foi lançado alguma vez (mantém o
  // histórico íntegro) — nesse caso o usuário desativa em vez de excluir
  // (checkbox "Ativo" no form de edição).
  const excluir = async (p: Protocolo) => {
    if (!window.confirm(`Excluir o protocolo "${p.nome}"? Isso não pode ser desfeito.`)) return;
    setExcluindo(p.id); setErroExclusao(null);
    try {
      await excluirProtocoloSanitario(p.id);
      await carregar();
    } catch (e: any) {
      setErroExclusao(e.message || "Erro ao excluir protocolo");
    } finally {
      setExcluindo(null);
    }
  };

  const acrescentarEtapa = () => setForm((f) => ({ ...f, etapas: [...f.etapas, etapaVazia(f.etapas.length)] }));
  const removerEtapa = (idx: number) => setForm((f) => (f.etapas.length > 1 ? { ...f, etapas: f.etapas.filter((_, i) => i !== idx) } : f));
  const atualizarEtapa = (idx: number, patch: Partial<ProtocoloEtapa>) =>
    setForm((f) => ({ ...f, etapas: f.etapas.map((e, i) => (i === idx ? { ...e, ...patch } : e)) }));

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    if (form.etapas.some((e) => e.dia < 0)) { setMsg("O dia da etapa não pode ser negativo (o protocolo pode começar em D0)."); return; }
    if (form.etapas.some((e) => !e.produto.trim() || !e.dosagem || Number(e.dosagem) <= 0)) { setMsg("Preencha produto e dosagem em todas as etapas."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = {
        nome: form.nome.trim(), doenca_id: form.doenca_id ? Number(form.doenca_id) : undefined,
        eh_mastite: form.eh_mastite, dia_inicial: form.dia_inicial, ativo: form.ativo,
        etapas: form.etapas.map((e) => ({ ...e, dia: Number(e.dia), dosagem: Number(e.dosagem), via: e.via || undefined, observacao: e.observacao || undefined })),
      };
      if (editando === "novo") await criarProtocoloSanitario(dados);
      else if (typeof editando === "number") await atualizarProtocoloSanitario(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const baixarModelo = () => {
    exportarExcel(
      "Modelo de importação — Protocolo sanitário",
      [
        { header: "Nome do protocolo", key: "nome", width: 26 },
        { header: "Dia da aplicação", key: "dia", width: 14 },
        { header: "Definido por", key: "definido_por", width: 16 },
        { header: "Medicamento", key: "medicamento", width: 20 },
        { header: "Dosagem", key: "dosagem", width: 12 },
        { header: "Unidade", key: "unidade", width: 12 },
        { header: "Via", key: "via", width: 16 },
      ],
      [
        { nome: "Exemplo - Protocolo 1", dia: 1, definido_por: "Medicamento", medicamento: "Borgal", dosagem: 40, unidade: "ml", via: "Intramuscular" },
        { nome: "Exemplo - Protocolo 1", dia: 1, definido_por: "Medicamento", medicamento: "Spectramast", dosagem: 2, unidade: "unidade", via: "Intramamária" },
        { nome: "Exemplo - Protocolo 1", dia: 2, definido_por: "Medicamento", medicamento: "Spectramast", dosagem: 2, unidade: "unidade", via: "Intramamária" },
      ],
      "modelo_protocolo_sanitario",
    );
  };

  const importarArquivo = async (file: File) => {
    setImportando(true); setMsgImport(null);
    try {
      const r = await importarProtocoloSanitarioExcel(file);
      const partes: string[] = [];
      if (r.criados?.length) partes.push(`${r.criados.length} protocolo(s) criado(s): ${r.criados.join(", ")}`);
      if (r.atualizados?.length) partes.push(`${r.atualizados.length} atualizado(s): ${r.atualizados.join(", ")}`);
      if (r.erros?.length) partes.push(`Erros: ${r.erros.join(" | ")}`);
      setMsgImport({ erro: !!r.erros?.length && !r.criados?.length && !r.atualizados?.length, texto: partes.join(" — ") || "Nenhum protocolo reconhecido na planilha." });
      await carregar();
    } catch (e: any) {
      setMsgImport({ erro: true, texto: e.message || "Erro ao importar planilha" });
    } finally {
      setImportando(false);
      if (inputImportRef.current) inputImportRef.current.value = "";
    }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((p) =>
    !termoBusca || normalizar(`${p.nome} ${p.doenca_nome ?? ""}`).includes(termoBusca)
  );
  const ordProtocolos = useOrdenacao(filtrados);

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><ClipboardList size={16} /> Protocolos sanitários</span>
        <div className="flex items-center gap-2">
          <button className="btn-ghost" style={{ fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={baixarModelo} title="Baixar planilha-modelo para preencher e importar">
            <Download size={13} /> Baixar modelo
          </button>
          <button
            className="btn-ghost" style={{ fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
            onClick={() => inputImportRef.current?.click()} disabled={importando}
            title="Importar protocolo(s) de uma planilha Excel/CSV"
          >
            <Upload size={13} /> {importando ? "Importando…" : "Importar Excel"}
          </button>
          <input ref={inputImportRef} type="file" accept=".xlsx,.xlsm,.csv" style={{ display: "none" }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) importarArquivo(f); }} />
          <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
            <Plus size={14} /> Novo
          </button>
        </div>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Tratamento com múltiplas etapas (produto, dosagem, via e dia de aplicação), a exemplo do tratamento de
        mastite. Os dias começam em D0, como todos os protocolos do sistema (inclusive o protocolo hormonal IATF).
        Marque "É protocolo de mastite" para habilitar, no lançamento, os campos de CMT, teto afetado e
        classificação (clínica/subclínica/ambiental). Para cadastrar vários protocolos de uma vez, baixe o modelo,
        preencha uma linha por etapa (várias linhas com o mesmo nome formam um único protocolo) e importe.
      </p>

      {msgImport && (
        <p style={{ color: msgImport.erro ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
          {msgImport.texto}
        </p>
      )}
      {erroExclusao && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>{erroExclusao}</p>}
      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <FormProtocolo
          form={form} setForm={setForm} doencas={doencas} estoque={estoque} principios={principios} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
          acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
        />
      )}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar protocolo…" title="Buscar por nome ou doença" />
          </div>
          <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <ThOrdenavel label="Nome" campo="nome" coluna={ordProtocolos.coluna} dir={ordProtocolos.dir} ordenar={ordProtocolos.ordenar} />
              <ThOrdenavel label="Doença" campo="doenca_nome" coluna={ordProtocolos.coluna} dir={ordProtocolos.dir} ordenar={ordProtocolos.ordenar} />
              <ThOrdenavel label="Mastite" campo="eh_mastite" coluna={ordProtocolos.coluna} dir={ordProtocolos.dir} ordenar={ordProtocolos.ordenar} />
              <th>Etapas</th><th></th>
            </tr></thead>
            <tbody>
              {ordProtocolos.linhasOrdenadas.map((p) => (
                <Fragment key={p.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{p.nome}{!p.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.doenca_nome || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.eh_mastite ? "Sim" : "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.etapas.map((e) => `D${e.dia - (p.dia_inicial ?? 0)}`).join(", ")}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(p)}>
                        <Pencil size={13} /> Editar
                      </button>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", color: "var(--red)", marginLeft: "0.4rem" }}
                        onClick={() => excluir(p)} disabled={excluindo === p.id} title="Excluir protocolo — só é possível se ele nunca foi lançado">
                        <Trash2 size={13} /> {excluindo === p.id ? "Excluindo…" : "Excluir"}
                      </button>
                    </td>
                  </tr>
                  {editando === p.id && (
                    <tr><td colSpan={5} style={{ padding: 0 }}>
                      <FormProtocolo
                        form={form} setForm={setForm} doencas={doencas} estoque={estoque} principios={principios} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
                        acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
                      />
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {!itens.length && !editando && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo cadastrado ainda.</td></tr>}
              {!!itens.length && !filtrados.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
            </tbody>
          </table>
          </div>
        </>
      )}
    </div>
  );
}

function FormProtocolo({ form, setForm, doencas, estoque, principios, onSalvar, onCancelar, salvando, msg, acrescentarEtapa, removerEtapa, atualizarEtapa }: {
  form: ProtocoloForm; setForm: (f: ProtocoloForm) => void; doencas: { id: number; nome: string }[]; estoque: EstoqueItemPicker[];
  principios: { id: number; nome: string }[];
  onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
  acrescentarEtapa: () => void; removerEtapa: (idx: number) => void; atualizarEtapa: (idx: number, patch: Partial<ProtocoloEtapa>) => void;
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="ex.: Mastite clínica padrão" /></div>
        <div><label style={labelStyle}>Doença vinculada</label>
          <select style={inputStyle} value={form.doenca_id} onChange={(e) => setForm({ ...form, doenca_id: e.target.value })}>
            <option value="">—</option>{doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
          </select></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.eh_mastite} onChange={(e) => setForm({ ...form, eh_mastite: e.target.checked })} /> É protocolo de mastite</label></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>

      <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.4rem" }}>Etapas (D0, D1, D2...)</p>
      <div className="space-y-2 mb-2">
        {form.etapas.map((e, idx) => (
          <div key={idx} className="grid grid-cols-2 md:grid-cols-8 gap-2 items-end" style={{ background: "var(--surface)", padding: "0.5rem", borderRadius: "6px" }}>
            <div><label style={labelStyle}>Dia (D)</label><input type="number" min={0} style={inputStyle} value={e.dia} onChange={(ev) => atualizarEtapa(idx, { dia: Number(ev.target.value) })} /></div>
            <div><label style={labelStyle}>Definir por</label>
              <select style={inputStyle} value={e.criterio_tipo || "medicamento"} onChange={(ev) => atualizarEtapa(idx, { criterio_tipo: ev.target.value, produto: "" })}>
                {CRITERIOS.map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
              </select></div>
            <div style={{ gridColumn: "span 2" }}>
              <label style={labelStyle}>{(e.criterio_tipo || "medicamento") === "medicamento" ? "Medicamento" : (e.criterio_tipo === "principio_ativo" ? "Princípio ativo" : e.criterio_tipo === "doenca" ? "Doença" : "Classificação")}</label>
              {(e.criterio_tipo || "medicamento") === "medicamento" ? (
                <EstoquePicker itens={estoque} value={e.produto} onChange={(v) => atualizarEtapa(idx, { produto: v })} />
              ) : e.criterio_tipo === "principio_ativo" ? (
                <select style={inputStyle} value={e.produto} onChange={(ev) => atualizarEtapa(idx, { produto: ev.target.value })}>
                  <option value="">Selecione…</option>{principios.map((p) => <option key={p.id} value={p.nome}>{p.nome}</option>)}
                </select>
              ) : e.criterio_tipo === "doenca" ? (
                <select style={inputStyle} value={e.produto} onChange={(ev) => atualizarEtapa(idx, { produto: ev.target.value })}>
                  <option value="">Selecione…</option>{doencas.map((d) => <option key={d.id} value={d.nome}>{d.nome}</option>)}
                </select>
              ) : (
                <select style={inputStyle} value={e.produto} onChange={(ev) => atualizarEtapa(idx, { produto: ev.target.value })}>
                  <option value="">Selecione…</option>{CLASSIFICACOES_MEDICAMENTO.map((cl) => <option key={cl} value={cl}>{cl}</option>)}
                </select>
              )}
            </div>
            <div><label style={labelStyle}>Dosagem</label><input type="number" inputMode="decimal" style={inputStyle} value={e.dosagem} onChange={(ev) => atualizarEtapa(idx, { dosagem: Number(ev.target.value) })} /></div>
            <div><label style={labelStyle}>Unidade</label>
              {(() => {
                const un = unidadesCompat(estoque.find((it) => it.nome === e.produto)?.unidade);
                return (
                  <select style={inputStyle} value={e.unidade} onChange={(ev) => atualizarEtapa(idx, { unidade: ev.target.value })}>
                    {!un.includes(e.unidade) && e.unidade && <option value={e.unidade}>{e.unidade}</option>}
                    {!e.unidade && <option value="">—</option>}
                    {un.map((u) => <option key={u} value={u}>{u}</option>)}
                  </select>
                );
              })()}
            </div>
            <div><label style={labelStyle}>Via</label>
              <select style={inputStyle} value={e.via || ""} onChange={(ev) => atualizarEtapa(idx, { via: ev.target.value })}>
                <option value="">—</option>{VIAS_APLICACAO.map((v) => <option key={v}>{v}</option>)}
              </select></div>
            <div className="flex items-end gap-1">
              <div style={{ flex: 1 }}><label style={labelStyle}>Observação</label>
                <input style={inputStyle} value={e.observacao || ""} onChange={(ev) => atualizarEtapa(idx, { observacao: ev.target.value })} placeholder="ex.: Se necessário" /></div>
              {form.etapas.length > 1 && <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => removerEtapa(idx)}><Trash2 size={13} /></button>}
            </div>
          </div>
        ))}
      </div>
      <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem", marginBottom: "0.8rem" }} onClick={acrescentarEtapa}>
        <Plus size={14} /> Acrescentar etapa
      </button>

      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onSalvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}

// ─────────────────────── Protocolo de indução de lactação ───────────────────────
// Cronograma-molde por dia (D0, D1...), com 3 tipos de etapa: medicamento
// (produto/dose/unidade/via), dispositivo (colocar/retirar implante de
// progesterona) e manejo (uma ação livre, ex.: "Adaptação na ordenha"). Os 2
// protocolos padrão ("18 dias" e "28 dias") nascem de um seed único no
// primeiro boot (ver seed_protocolos_inducao_lactacao) e ficam livres para
// editar/duplicar aqui — não existe endpoint de exclusão (mesma lógica do
// protocolo sanitário: se já foi lançado, desativar em vez de apagar; aqui,
// mais simples ainda, evita perder o histórico de quem já usou).
const TIPOS_ETAPA_INDUCAO: [string, string][] = [
  ["medicamento", "Medicamento"],
  ["dispositivo", "Dispositivo (implante)"],
  ["manejo", "Manejo"],
];
const etapaInducaoVazia = (dia: number): EtapaInducaoLactacao => ({ dia, tipo: "medicamento", produto: "", dose: null, unidade: "ml", via: "" });
type ProtocoloInducaoForm = { nome: string; dia_inicial: number; observacao: string; ativo: boolean; etapas: EtapaInducaoLactacao[] };
const protocoloInducaoFormVazio = (): ProtocoloInducaoForm => ({ nome: "", dia_inicial: 0, observacao: "", ativo: true, etapas: [etapaInducaoVazia(0)] });

function CadastroProtocolosInducao() {
  const [itens, setItens] = useState<ProtocoloInducaoLactacaoCadastro[] | null>(null);
  const [principios, setPrincipios] = useState<{ id: number; nome: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<ProtocoloInducaoForm>(protocoloInducaoFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");

  const carregar = () => fetchProtocolosInducaoLactacaoCadastro().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchPrincipiosAtivos().then(setPrincipios).catch(() => {});
  }, []);

  const abrirNovo = () => { setForm(protocoloInducaoFormVazio()); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (p: ProtocoloInducaoLactacaoCadastro) => {
    setForm({
      nome: p.nome, dia_inicial: p.dia_inicial, observacao: p.observacao || "", ativo: p.ativo,
      etapas: p.etapas.length ? p.etapas.map((e) => ({ ...e })) : [etapaInducaoVazia(p.dia_inicial)],
    });
    setEditando(p.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const acrescentarEtapa = () => setForm((f) => ({ ...f, etapas: [...f.etapas, etapaInducaoVazia(f.etapas.length)] }));
  const removerEtapa = (idx: number) => setForm((f) => (f.etapas.length > 1 ? { ...f, etapas: f.etapas.filter((_, i) => i !== idx) } : f));
  const atualizarEtapa = (idx: number, patch: Partial<EtapaInducaoLactacao>) =>
    setForm((f) => ({ ...f, etapas: f.etapas.map((e, i) => (i === idx ? { ...e, ...patch } : e)) }));

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    if (form.etapas.some((e) => e.dia < 0)) { setMsg("O dia da etapa não pode ser negativo (o protocolo pode começar em D0)."); return; }
    if (form.etapas.some((e) => !e.produto.trim())) { setMsg("Preencha o produto/ação de todas as etapas."); return; }
    if (form.etapas.some((e) => e.tipo === "dispositivo" && !e.acao_dispositivo)) { setMsg("Etapa de dispositivo precisa dizer se é para colocar ou retirar."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados: ProtocoloInducaoLactacaoPayload = {
        nome: form.nome.trim(), dia_inicial: form.dia_inicial, observacao: form.observacao || undefined, ativo: form.ativo,
        etapas: form.etapas.map((e) => ({
          dia: Number(e.dia), tipo: e.tipo, produto: e.produto.trim(),
          principio_ativo_id: e.tipo === "medicamento" ? (principios.find((p) => p.nome === e.produto)?.id ?? null) : null,
          acao_dispositivo: e.tipo === "dispositivo" ? e.acao_dispositivo : null,
          dose: e.tipo === "medicamento" && e.dose != null && e.dose !== ("" as any) ? Number(e.dose) : null,
          unidade: e.tipo === "medicamento" ? (e.unidade || undefined) : undefined,
          via: e.tipo === "medicamento" ? (e.via || undefined) : undefined,
        })),
      };
      if (editando === "novo") await criarProtocoloInducaoLactacao(dados);
      else if (typeof editando === "number") await atualizarProtocoloInducaoLactacao(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((p) => !termoBusca || normalizar(p.nome).includes(termoBusca));
  const ordProtocolos = useOrdenacao(filtrados);

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Milk size={16} /> Protocolos de indução de lactação</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Cronograma por dia (D0, D1, D2...) com 3 tipos de etapa: medicamento (produto/dose/via), dispositivo
        (colocar/retirar o implante de progesterona) e manejo (uma ação livre, ex.: "Adaptação na ordenha"). Usado
        em Lançamentos › Produção › Indução de lactação.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <FormProtocoloInducao
          form={form} setForm={setForm} principios={principios} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
          acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
        />
      )}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar protocolo…" />
          </div>
          <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <ThOrdenavel label="Nome" campo="nome" coluna={ordProtocolos.coluna} dir={ordProtocolos.dir} ordenar={ordProtocolos.ordenar} />
              <th>Duração</th><th>Etapas</th><th></th>
            </tr></thead>
            <tbody>
              {ordProtocolos.linhasOrdenadas.map((p) => (
                <Fragment key={p.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{p.nome}{!p.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.etapas.length ? `D${p.dia_inicial} a D${Math.max(...p.etapas.map((e) => e.dia))}` : "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.etapas.length} etapa(s)</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(p)}>
                        <Pencil size={13} /> Editar
                      </button>
                    </td>
                  </tr>
                  {editando === p.id && (
                    <tr><td colSpan={4} style={{ padding: 0 }}>
                      <FormProtocoloInducao
                        form={form} setForm={setForm} principios={principios} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
                        acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
                      />
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {!itens.length && !editando && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo cadastrado ainda.</td></tr>}
              {!!itens.length && !filtrados.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
            </tbody>
          </table>
          </div>
        </>
      )}
    </div>
  );
}

function FormProtocoloInducao({ form, setForm, principios, onSalvar, onCancelar, salvando, msg, acrescentarEtapa, removerEtapa, atualizarEtapa }: {
  form: ProtocoloInducaoForm; setForm: (f: ProtocoloInducaoForm) => void; principios: { id: number; nome: string }[];
  onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
  acrescentarEtapa: () => void; removerEtapa: (idx: number) => void; atualizarEtapa: (idx: number, patch: Partial<EtapaInducaoLactacao>) => void;
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Nome</label>
          <input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="ex.: Protocolo de Indução — 18 dias" /></div>
        <div><label style={labelStyle}>Observação</label>
          <input style={inputStyle} value={form.observacao} onChange={(e) => setForm({ ...form, observacao: e.target.value })} placeholder="opcional" /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>

      <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.4rem" }}>Etapas (D0, D1, D2...)</p>
      <div className="space-y-2 mb-2">
        {form.etapas.map((e, idx) => (
          <div key={idx} className="grid grid-cols-2 md:grid-cols-8 gap-2 items-end" style={{ background: "var(--surface)", padding: "0.5rem", borderRadius: "6px" }}>
            <div><label style={labelStyle}>Dia (D)</label><input type="number" min={0} style={inputStyle} value={e.dia} onChange={(ev) => atualizarEtapa(idx, { dia: Number(ev.target.value) })} /></div>
            <div><label style={labelStyle}>Tipo</label>
              <select style={inputStyle} value={e.tipo} onChange={(ev) => atualizarEtapa(idx, { tipo: ev.target.value as EtapaInducaoLactacao["tipo"], produto: "", acao_dispositivo: null })}>
                {TIPOS_ETAPA_INDUCAO.map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
              </select></div>

            {e.tipo === "medicamento" && (
              <>
                <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Princípio ativo</label>
                  <select style={inputStyle} value={e.produto} onChange={(ev) => atualizarEtapa(idx, { produto: ev.target.value })}>
                    <option value="">Selecione…</option>
                    {!principios.some((p) => p.nome === e.produto) && e.produto && <option value={e.produto}>{e.produto}</option>}
                    {principios.map((p) => <option key={p.id} value={p.nome}>{p.nome}</option>)}
                  </select></div>
                <div><label style={labelStyle}>Dose (opcional)</label>
                  <input type="number" inputMode="decimal" style={inputStyle} value={e.dose ?? ""} onChange={(ev) => atualizarEtapa(idx, { dose: ev.target.value === "" ? null : Number(ev.target.value) })} /></div>
                <div><label style={labelStyle}>Unidade</label>
                  <select style={inputStyle} value={e.unidade || ""} onChange={(ev) => atualizarEtapa(idx, { unidade: ev.target.value })}>
                    <option value="">—</option>{UNIDADES_PADRAO.map((u) => <option key={u} value={u}>{u}</option>)}
                  </select></div>
                <div><label style={labelStyle}>Via</label>
                  <select style={inputStyle} value={e.via || ""} onChange={(ev) => atualizarEtapa(idx, { via: ev.target.value })}>
                    <option value="">—</option>{VIAS_APLICACAO.map((v) => <option key={v}>{v}</option>)}
                  </select></div>
              </>
            )}

            {e.tipo === "dispositivo" && (
              <>
                <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Dispositivo</label>
                  <input style={inputStyle} value={e.produto} onChange={(ev) => atualizarEtapa(idx, { produto: ev.target.value })} placeholder="ex.: Implante de Progesterona" /></div>
                <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Ação</label>
                  <select style={inputStyle} value={e.acao_dispositivo || ""} onChange={(ev) => atualizarEtapa(idx, { acao_dispositivo: ev.target.value as "colocar" | "retirar" })}>
                    <option value="">Selecione…</option><option value="colocar">Colocar</option><option value="retirar">Retirar</option>
                  </select></div>
              </>
            )}

            {e.tipo === "manejo" && (
              <div style={{ gridColumn: "span 4" }}><label style={labelStyle}>Ação de manejo</label>
                <input style={inputStyle} value={e.produto} onChange={(ev) => atualizarEtapa(idx, { produto: ev.target.value })} placeholder="ex.: Adaptação na ordenha" /></div>
            )}

            <div className="flex items-end">
              {form.etapas.length > 1 && <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => removerEtapa(idx)}><Trash2 size={13} /></button>}
            </div>
          </div>
        ))}
      </div>
      <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem", marginBottom: "0.8rem" }} onClick={acrescentarEtapa}>
        <Plus size={14} /> Acrescentar etapa
      </button>

      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onSalvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}

// ─────────────────────── Evento sanitário (cadastro rico) ───────────────────────
const FREQ_UNIDADES = [["dias", "dia(s)"], ["meses", "mês(es)"], ["anos", "ano(s)"]] as const;
const GATILHOS: [string, string][] = [
  ["nascimento", "Nascimento (quando a cria nasce)"],
  ["desmama", "Desmama"],
  ["mudanca_recria", "Mudança para recria"],
  ["entrada_lote", "Entrada num lote (ex.: pré-parto)"],
  ["novilha_apta", "Aptidão (novilha atingir certa idade)"],
  ["inseminacao", "Inseminação"],
  ["gestacao_confirmada", "Gestação confirmada"],
  ["secagem", "Secagem"],
  ["parto", "Parto"],
  ["mudanca_pre_parto", "Mudança para pré-parto"],
];
const GATILHO_LABEL: Record<string, string> = Object.fromEntries(GATILHOS);

type EventoSanitarioRow = EventoSanitarioPayload & { id: number; doenca_nome?: string | null; condicao_evento_nome?: string | null; proxima_ocorrencia?: string | null };
type EventoForm = {
  nome: string; ativo: boolean; tipo_agendamento: "nenhum" | "epoca" | "evento";
  categoria_alvo: string; sexo_alvo: string; categoria_preventiva: string; doenca_id: string;
  data_primeiro: string; frequencia_valor: string; frequencia_unidade: string;
  gatilho: string; gatilho_lote: string; gatilho_idade_meses: string; offset_dias: string;
  produto_padrao: string; dose_padrao: string; unidade_padrao: string; via_padrao: string;
  avisar_veterinario_30_dias: boolean;
  condicao_evento_id: string;
  exame_definicao_id: string;
  servico_financeiro: string;
};
const eventoFormVazio = (): EventoForm => ({
  nome: "", ativo: true, tipo_agendamento: "nenhum", categoria_alvo: "", sexo_alvo: "", categoria_preventiva: "vacina", doenca_id: "",
  data_primeiro: "", frequencia_valor: "", frequencia_unidade: "meses",
  gatilho: "nascimento", gatilho_lote: "", gatilho_idade_meses: "", offset_dias: "",
  produto_padrao: "", dose_padrao: "", unidade_padrao: "", via_padrao: "",
  avisar_veterinario_30_dias: false,
  condicao_evento_id: "",
  exame_definicao_id: "",
  servico_financeiro: "",
});

export function CadastroEventosSanitarios() {
  const [itens, setItens] = useState<EventoSanitarioRow[] | null>(null);
  const [doencas, setDoencas] = useState<{ id: number; nome: string }[]>([]);
  const [estoque, setEstoque] = useState<EstoqueItemPicker[]>([]);
  const [lotes, setLotes] = useState<{ codigo: string; nome?: string }[]>([]);
  const [exames, setExames] = useState<{ id: number; nome: string }[]>([]);
  const [servicos, setServicos] = useState<{ id: number; nome: string; ativo?: boolean }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<EventoForm>(eventoFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");

  const carregar = () => fetchEventosSanitarios().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchDoencas().then(setDoencas).catch(() => {});
    fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {});
    fetchLotes().then(setLotes).catch(() => {});
    fetchExames().then(setExames).catch(() => {});
    fetchServicosCadastro().then(setServicos).catch(() => {});
  }, []);

  const abrirNovo = () => { setForm(eventoFormVazio()); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (e: EventoSanitarioRow) => {
    setForm({
      nome: e.nome, ativo: e.ativo ?? true, tipo_agendamento: (e.tipo_agendamento as any) || "nenhum",
      categoria_alvo: e.categoria_alvo || "", sexo_alvo: (e as any).sexo_alvo || "", categoria_preventiva: (e as any).categoria_preventiva || "", doenca_id: e.doenca_id ? String(e.doenca_id) : "",
      data_primeiro: e.data_primeiro || "", frequencia_valor: e.frequencia_valor ? String(e.frequencia_valor) : "",
      frequencia_unidade: e.frequencia_unidade || "meses", gatilho: e.gatilho || "nascimento",
      gatilho_lote: e.gatilho_lote || "", gatilho_idade_meses: e.gatilho_idade_meses ? String(e.gatilho_idade_meses) : "",
      offset_dias: e.offset_dias ? String(e.offset_dias) : "",
      produto_padrao: e.produto_padrao || "", dose_padrao: e.dose_padrao != null ? String(e.dose_padrao) : "",
      unidade_padrao: e.unidade_padrao || "", via_padrao: e.via_padrao || "",
      avisar_veterinario_30_dias: !!(e as any).agenda_dias_antes,
      condicao_evento_id: e.condicao_evento_id ? String(e.condicao_evento_id) : "",
      exame_definicao_id: (e as any).exame_definicao_id ? String((e as any).exame_definicao_id) : "",
      servico_financeiro: (e as any).servico_financeiro || "",
    });
    setEditando(e.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    const dados: EventoSanitarioPayload = {
      nome: form.nome.trim(), ativo: form.ativo, tipo_agendamento: form.tipo_agendamento,
      categoria_alvo: form.categoria_alvo.trim() || null, sexo_alvo: (form.sexo_alvo as "F" | "M" | "") || null,
      doenca_id: form.doenca_id ? Number(form.doenca_id) : null,
      categoria_preventiva: form.categoria_preventiva || null,
      data_primeiro: form.tipo_agendamento === "epoca" && form.data_primeiro ? form.data_primeiro : null,
      frequencia_valor: form.tipo_agendamento === "epoca" && form.frequencia_valor ? Number(form.frequencia_valor) : null,
      frequencia_unidade: form.tipo_agendamento === "epoca" ? form.frequencia_unidade : null,
      gatilho: form.tipo_agendamento === "evento" ? form.gatilho : null,
      gatilho_lote: form.tipo_agendamento === "evento" && form.gatilho === "entrada_lote" ? form.gatilho_lote || null : null,
      gatilho_idade_meses: form.tipo_agendamento === "evento" && form.gatilho === "novilha_apta" && form.gatilho_idade_meses ? Number(form.gatilho_idade_meses) : null,
      offset_dias: form.tipo_agendamento === "evento" && form.offset_dias ? Number(form.offset_dias) : null,
      produto_padrao: form.produto_padrao.trim() || null, dose_padrao: form.dose_padrao ? Number(form.dose_padrao) : null,
      unidade_padrao: form.unidade_padrao || null, via_padrao: form.via_padrao || null,
      agenda_dias_antes: form.categoria_preventiva === "exame" && form.avisar_veterinario_30_dias ? 30 : null,
      condicao_evento_id: form.condicao_evento_id ? Number(form.condicao_evento_id) : null,
      exame_definicao_id: form.categoria_preventiva === "exame" && form.exame_definicao_id ? Number(form.exame_definicao_id) : null,
      servico_financeiro: form.servico_financeiro || null,
    };
    setSalvando(true); setMsg(null);
    try {
      if (editando === "novo") await criarEventoSanitario(dados);
      else if (typeof editando === "number") await atualizarEventoSanitario(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) { setMsg(e.message || "Erro ao salvar"); }
    finally { setSalvando(false); }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((e) => !termoBusca || normalizar(e.nome).includes(termoBusca));
  const unidadesProduto = unidadesCompat(estoque.find((it) => it.nome === form.produto_padrao)?.unidade);

  const rotuloAgendamento = (e: EventoSanitarioRow) => {
    if (e.tipo_agendamento === "epoca")
      return `A cada ${e.frequencia_valor} ${FREQ_UNIDADES.find((f) => f[0] === e.frequencia_unidade)?.[1] || e.frequencia_unidade}`;
    if (e.tipo_agendamento === "evento")
      return `Por evento: ${GATILHO_LABEL[e.gatilho || ""] || e.gatilho}${e.gatilho === "entrada_lote" && e.gatilho_lote ? ` (${e.gatilho_lote})` : ""}`;
    return "—";
  };

  const formEl = (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Nome do evento</label>
          <input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder='ex.: "Vacina pré-parto", "Vermífugo"' /></div>
        <div><label style={labelStyle}>Doença combatida</label>
          <select style={inputStyle} value={form.doenca_id} onChange={(e) => setForm({ ...form, doenca_id: e.target.value })}>
            <option value="">—</option>{doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
          </select></div>
        <div><label style={labelStyle}>Sexo-alvo</label>
          <select style={inputStyle} value={form.sexo_alvo} onChange={(e) => setForm({ ...form, sexo_alvo: e.target.value })}>
            <option value="">Ambos</option>
            <option value="F">Só fêmeas</option>
            <option value="M">Só machos</option>
          </select></div>
        <div><label style={labelStyle}>Categoria preventiva</label>
          <select style={inputStyle} value={form.categoria_preventiva} onChange={(e) => setForm({ ...form, categoria_preventiva: e.target.value })}>
            {/* Evento "avulso" (sem categoria) não é mais uma opção nova — só
                preservada aqui se for o valor herdado de um evento antigo, para
                não trocar o valor por engano ao abrir a edição. */}
            {!form.categoria_preventiva && <option value="">— (legado, escolha uma categoria)</option>}
            <option value="vacina">Vacina</option>
            <option value="exame">Exame</option>
            <option value="tratamento">Tratamento</option>
          </select></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>

      <label style={labelStyle}>Quando repetir</label>
      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        {([["nenhum", "Só o nome"], ["epoca", "Por época (recorrência)"], ["evento", "Por evento de vida"]] as const).map(([v, lbl]) => (
          <button key={v} type="button" onClick={() => setForm({ ...form, tipo_agendamento: v })}
            style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
              border: "1px solid " + (form.tipo_agendamento === v ? "var(--dourado)" : "var(--border)"),
              background: form.tipo_agendamento === v ? "rgba(94,26,46,0.4)" : "transparent",
              color: form.tipo_agendamento === v ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: form.tipo_agendamento === v ? 700 : 500 }}>
            {lbl}
          </button>
        ))}
      </div>

      {form.tipo_agendamento === "epoca" && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyle}>Data do 1º evento</label>
            <input type="date" style={inputStyle} value={form.data_primeiro} onChange={(e) => setForm({ ...form, data_primeiro: e.target.value })} /></div>
          <div><label style={labelStyle}>A cada</label>
            <input type="number" min={1} style={inputStyle} value={form.frequencia_valor} onChange={(e) => setForm({ ...form, frequencia_valor: e.target.value })} placeholder="6" /></div>
          <div><label style={labelStyle}>Período</label>
            <select style={inputStyle} value={form.frequencia_unidade} onChange={(e) => setForm({ ...form, frequencia_unidade: e.target.value })}>
              {FREQ_UNIDADES.map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
            </select></div>
          <div><label style={labelStyle}>Categoria-alvo (opcional)</label>
            <input style={inputStyle} value={form.categoria_alvo} onChange={(e) => setForm({ ...form, categoria_alvo: e.target.value })} placeholder="ex.: Bezerras" /></div>
        </div>
      )}

      {form.tipo_agendamento === "evento" && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Gatilho</label>
            <select style={inputStyle} value={form.gatilho} onChange={(e) => setForm({ ...form, gatilho: e.target.value })}>
              {GATILHOS.map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
            </select></div>
          {form.gatilho === "entrada_lote" && (
            <div><label style={labelStyle}>Lote</label>
              <select style={inputStyle} value={form.gatilho_lote} onChange={(e) => setForm({ ...form, gatilho_lote: e.target.value })}>
                <option value="">Selecione…</option>
                {lotes.map((l) => <option key={l.codigo} value={l.codigo}>{l.codigo}{l.nome ? ` — ${l.nome}` : ""}</option>)}
              </select></div>
          )}
          {form.gatilho === "novilha_apta" && (
            <div><label style={labelStyle}>Idade-alvo (meses)</label>
              <input type="number" min={1} style={inputStyle} value={form.gatilho_idade_meses} onChange={(e) => setForm({ ...form, gatilho_idade_meses: e.target.value })} placeholder="ex.: 13" /></div>
          )}
          <div><label style={labelStyle}>Dias após o gatilho</label>
            <input type="number" min={0} style={inputStyle} value={form.offset_dias} onChange={(e) => setForm({ ...form, offset_dias: e.target.value })} placeholder="0" /></div>
          <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Condição — só agendar se NÃO tiver recebido</label>
            <select style={inputStyle} value={form.condicao_evento_id} onChange={(e) => setForm({ ...form, condicao_evento_id: e.target.value })}>
              <option value="">— (sempre agendar)</option>
              {(itens || []).filter((o) => o.id !== editando).map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}
            </select>
            <span style={{ display: "block", fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
              Para alternativas de vacina/estirpe para a mesma doença — ex.: não agendar "Brucelose RB51" se o animal já recebeu "Brucelose B19".
            </span>
          </div>
        </div>
      )}

      {form.tipo_agendamento !== "nenhum" && (
        <>
          <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.4rem" }}>Medicamento padrão (editável na hora da baixa)</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Produto</label>
              <EstoquePicker itens={estoque} value={form.produto_padrao} onChange={(v) => setForm({ ...form, produto_padrao: v, unidade_padrao: unidadesCompat(estoque.find((it) => it.nome === v)?.unidade)[0] || form.unidade_padrao })} /></div>
            <div><label style={labelStyle}>Dose</label>
              <input type="number" inputMode="decimal" style={inputStyle} value={form.dose_padrao} onChange={(e) => setForm({ ...form, dose_padrao: e.target.value })} /></div>
            <div><label style={labelStyle}>Unidade</label>
              <select style={inputStyle} value={form.unidade_padrao} onChange={(e) => setForm({ ...form, unidade_padrao: e.target.value })}>
                <option value="">—</option>
                {!unidadesProduto.includes(form.unidade_padrao) && form.unidade_padrao && <option value={form.unidade_padrao}>{form.unidade_padrao}</option>}
                {unidadesProduto.map((u) => <option key={u} value={u}>{u}</option>)}
              </select></div>
            <div><label style={labelStyle}>Via</label>
              <select style={inputStyle} value={form.via_padrao} onChange={(e) => setForm({ ...form, via_padrao: e.target.value })}>
                <option value="">—</option>{VIAS_APLICACAO.map((v) => <option key={v}>{v}</option>)}
              </select></div>
          </div>
          {form.categoria_preventiva === "exame" && (
            <>
              <div className="mb-3" style={{ maxWidth: 360 }}>
                <label style={labelStyle}>Exame vinculado (Cadastro › Sanitário › Exames)</label>
                <select style={inputStyle} value={form.exame_definicao_id} onChange={(e) => setForm({ ...form, exame_definicao_id: e.target.value })}>
                  <option value="">— (usa diagnóstico padrão: positivo/negativo/indefinido)</option>
                  {exames.map((ex) => <option key={ex.id} value={ex.id}>{ex.nome}</option>)}
                </select>
              </div>
              <label className="flex items-center gap-2 mb-3" style={{ fontSize: "0.8rem", cursor: "pointer" }}>
                <input type="checkbox" checked={form.avisar_veterinario_30_dias} onChange={(e) => setForm({ ...form, avisar_veterinario_30_dias: e.target.checked })} />
                Avisar na Agenda 30 dias antes, para confirmar o exame com o veterinário
              </label>
            </>
          )}
        </>
      )}

      {!!form.categoria_preventiva && (
        <div className="mb-3" style={{ maxWidth: 360 }}>
          <label style={labelStyle}>Serviço financeiro (opcional)</label>
          <select style={inputStyle} value={form.servico_financeiro} onChange={(e) => setForm({ ...form, servico_financeiro: e.target.value })}>
            <option value="">— (sem botão "Lançar financeiro" no calendário)</option>
            {servicos.filter((s) => s.ativo !== false).map((s) => <option key={s.id} value={s.nome}>{s.nome}</option>)}
          </select>
          <span style={{ display: "block", fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
            Liga este evento a um serviço já cadastrado (Configurações › Cadastro › Serviços), para o botão "Lançar financeiro" no calendário sanitário.
          </span>
        </div>
      )}

      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><CalendarClock size={16} /> Eventos sanitários</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Nome da vacina/manejo do calendário sanitário. Defina <strong>quando repetir</strong> — por época (a cada X dias/meses)
        ou por evento de vida (nascimento, entrada num lote como pré-parto, aptidão de novilha…) — e o medicamento padrão.
        Isso alimenta a <strong>Agenda</strong>: ao dar baixa, a aplicação e a saída de estoque são geradas (com o remédio editável na hora).
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && formEl}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar evento sanitário…" />
          </div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><th>Nome</th><th>Agendamento</th><th>Medicamento padrão</th><th>Próxima</th><th></th></tr></thead>
              <tbody>
                {filtrados.map((e) => (
                  <Fragment key={e.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>
                        {e.nome}{!e.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}
                        {e.condicao_evento_nome && (
                          <span style={{ display: "block", fontWeight: 400, fontSize: "0.68rem", color: "var(--text-muted)" }}>
                            se não recebeu: {e.condicao_evento_nome}
                          </span>
                        )}
                      </td>
                      <td style={{ fontSize: "0.78rem" }}>{rotuloAgendamento(e)}</td>
                      <td style={{ fontSize: "0.78rem" }}>{e.produto_padrao ? `${e.produto_padrao}${e.dose_padrao != null ? ` — ${e.dose_padrao} ${e.unidade_padrao || ""}` : ""}` : "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--dourado-light)" }}>{e.proxima_ocorrencia ? new Date(e.proxima_ocorrencia + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                      <td style={{ textAlign: "right" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(e)}>
                          <Pencil size={13} /> Editar
                        </button>
                      </td>
                    </tr>
                    {editando === e.id && <tr><td colSpan={5} style={{ padding: 0 }}>{formEl}</td></tr>}
                  </Fragment>
                ))}
                {!itens.length && !editando && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum evento sanitário cadastrado ainda.</td></tr>}
                {!!itens.length && !filtrados.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

// ─────────────────────── Exames (nome + tipo de resultado) ───────────────────────
type ExameRow = ExameDefinicaoPayload & { id: number; principio_ativo_nome?: string | null };
type ExameForm = {
  nome: string; ativo: boolean; principio_ativo_id: string;
  tipo_resultado: "diagnostico" | "numerico";
  faixa_min: string; faixa_max: string;
  acao_abaixo: string; acao_dentro: string; acao_acima: string;
  observacao: string;
};
const exameFormVazio = (): ExameForm => ({
  nome: "", ativo: true, principio_ativo_id: "", tipo_resultado: "diagnostico",
  faixa_min: "", faixa_max: "", acao_abaixo: "", acao_dentro: "", acao_acima: "", observacao: "",
});

function CadastroExames() {
  const [itens, setItens] = useState<ExameRow[] | null>(null);
  const [principios, setPrincipios] = useState<{ id: number; nome: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<ExameForm>(exameFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");

  const carregar = () => fetchExames().then(setItens).catch((e) => setError(e.message));
  useEffect(() => {
    carregar();
    fetchPrincipiosAtivos().then(setPrincipios).catch(() => {});
  }, []);

  const abrirNovo = () => { setForm(exameFormVazio()); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (e: ExameRow) => {
    setForm({
      nome: e.nome, ativo: e.ativo ?? true, principio_ativo_id: e.principio_ativo_id ? String(e.principio_ativo_id) : "",
      tipo_resultado: (e.tipo_resultado as any) || "diagnostico",
      faixa_min: e.faixa_min != null ? String(e.faixa_min) : "", faixa_max: e.faixa_max != null ? String(e.faixa_max) : "",
      acao_abaixo: e.acao_abaixo || "", acao_dentro: e.acao_dentro || "", acao_acima: e.acao_acima || "",
      observacao: e.observacao || "",
    });
    setEditando(e.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    if (form.tipo_resultado === "numerico" && (!form.faixa_min.trim() || !form.faixa_max.trim())) {
      setMsg("Informe a faixa (de x até y) para exame numérico."); return;
    }
    const dados: ExameDefinicaoPayload = {
      nome: form.nome.trim(), ativo: form.ativo,
      principio_ativo_id: form.principio_ativo_id ? Number(form.principio_ativo_id) : null,
      tipo_resultado: form.tipo_resultado,
      faixa_min: form.tipo_resultado === "numerico" && form.faixa_min ? Number(form.faixa_min) : null,
      faixa_max: form.tipo_resultado === "numerico" && form.faixa_max ? Number(form.faixa_max) : null,
      acao_abaixo: form.tipo_resultado === "numerico" ? (form.acao_abaixo.trim() || null) : null,
      acao_dentro: form.tipo_resultado === "numerico" ? (form.acao_dentro.trim() || null) : null,
      acao_acima: form.tipo_resultado === "numerico" ? (form.acao_acima.trim() || null) : null,
      observacao: form.observacao.trim() || null,
    };
    setSalvando(true); setMsg(null);
    try {
      if (editando === "novo") await criarExame(dados);
      else if (typeof editando === "number") await atualizarExame(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) { setMsg(e.message || "Erro ao salvar"); }
    finally { setSalvando(false); }
  };

  const excluir = async (e: ExameRow) => {
    if (!window.confirm(`Excluir o exame "${e.nome}"?`)) return;
    try { await excluirExame(e.id); await carregar(); }
    catch (err: any) { setError(err.message); }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((e) => !termoBusca || normalizar(e.nome).includes(termoBusca));

  const formEl = (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Nome do exame</label>
          <input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder='ex.: "Tuberculina", "Brucelose B19"' /></div>
        <div><label style={labelStyle}>Princípio ativo</label>
          <select style={inputStyle} value={form.principio_ativo_id} onChange={(e) => setForm({ ...form, principio_ativo_id: e.target.value })}>
            <option value="">—</option>{principios.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
          </select></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>

      <label style={labelStyle}>Resultados possíveis</label>
      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        {([["diagnostico", "Por diagnóstico (positivo/negativo/indefinido)"], ["numerico", "Numérico (faixa de valores)"]] as const).map(([v, lbl]) => (
          <button key={v} type="button" onClick={() => setForm({ ...form, tipo_resultado: v })}
            style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
              border: "1px solid " + (form.tipo_resultado === v ? "var(--dourado)" : "var(--border)"),
              background: form.tipo_resultado === v ? "rgba(94,26,46,0.4)" : "transparent",
              color: form.tipo_resultado === v ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: form.tipo_resultado === v ? 700 : 500 }}>
            {lbl}
          </button>
        ))}
      </div>

      {form.tipo_resultado === "diagnostico" && (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
          No lançamento (Sanitário › Preventivo), o resultado é <strong>positivo</strong> (marca automaticamente
          "A descartar"), <strong>negativo</strong> (liberada) ou <strong>indefinido</strong> (repetir exame) — para fins de relatório.
        </p>
      )}

      {form.tipo_resultado === "numerico" && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyle}>Faixa — de</label>
            <input type="number" inputMode="decimal" style={inputStyle} value={form.faixa_min} onChange={(e) => setForm({ ...form, faixa_min: e.target.value })} /></div>
          <div><label style={labelStyle}>Faixa — até</label>
            <input type="number" inputMode="decimal" style={inputStyle} value={form.faixa_max} onChange={(e) => setForm({ ...form, faixa_max: e.target.value })} /></div>
          <div style={{ gridColumn: "span 4" }}><label style={labelStyle}>O que fazer abaixo da faixa</label>
            <input style={inputStyle} value={form.acao_abaixo} onChange={(e) => setForm({ ...form, acao_abaixo: e.target.value })} placeholder="ex.: Sem ação" /></div>
          <div style={{ gridColumn: "span 4" }}><label style={labelStyle}>O que fazer dentro da faixa</label>
            <input style={inputStyle} value={form.acao_dentro} onChange={(e) => setForm({ ...form, acao_dentro: e.target.value })} placeholder="ex.: Monitorar" /></div>
          <div style={{ gridColumn: "span 4" }}><label style={labelStyle}>O que fazer acima da faixa</label>
            <input style={inputStyle} value={form.acao_acima} onChange={(e) => setForm({ ...form, acao_acima: e.target.value })} placeholder="ex.: Investigar" /></div>
        </div>
      )}

      <div className="mb-3"><label style={labelStyle}>Observação</label>
        <input style={inputStyle} value={form.observacao} onChange={(e) => setForm({ ...form, observacao: e.target.value })} /></div>

      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><FlaskConical size={16} /> Exames</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Cadastro de exames (ex.: tuberculose, brucelose) usados em Sanitário › Preventivo. Vincule ao princípio ativo
        e escolha o tipo de resultado: por diagnóstico (positivo/negativo/indefinido) ou numérico (faixa de x até y,
        com o que fazer abaixo, dentro e acima dela). Depois vincule este exame ao evento sanitário correspondente
        (aba Evento sanitário). Lançamento de exame nunca gera aplicação de medicamento nem baixa de estoque.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && formEl}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar exame…" />
          </div>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><th>Nome</th><th>Princípio ativo</th><th>Tipo de resultado</th><th>Faixa</th><th></th></tr></thead>
              <tbody>
                {filtrados.map((e) => (
                  <Fragment key={e.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>{e.nome}{!e.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                      <td style={{ fontSize: "0.78rem" }}>{e.principio_ativo_nome || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{e.tipo_resultado === "numerico" ? "Numérico" : "Diagnóstico"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{e.tipo_resultado === "numerico" && e.faixa_min != null ? `${e.faixa_min} a ${e.faixa_max}` : "—"}</td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <span style={{ display: "inline-flex", gap: "0.35rem", alignItems: "center" }}>
                          <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(e)}>
                            <Pencil size={13} /> Editar
                          </button>
                          <button title="Excluir" onClick={() => excluir(e)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", padding: 2 }}><Trash2 size={14} /></button>
                        </span>
                      </td>
                    </tr>
                    {editando === e.id && <tr><td colSpan={5} style={{ padding: 0 }}>{formEl}</td></tr>}
                  </Fragment>
                ))}
                {!itens.length && !editando && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum exame cadastrado ainda.</td></tr>}
                {!!itens.length && !filtrados.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

type Item = {
  id: number; nome: string; ativo: boolean;
  // Enriquecimento (documento base de princípios ativos) — ausente em Doenças.
  categoria?: string | null; categoria_software?: string | null;
  uso_principal?: string | null; justificativa?: string | null;
};
type Form = { nome: string; ativo: boolean };
const formVazio: Form = { nome: "", ativo: true };
type FormItemProps = {
  form: Form; setForm: (f: Form) => void; onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
};

// Ordem canônica dos grupos do documento base — mantém a mesma sequência do
// texto original em vez de ordenar alfabeticamente.
const ORDEM_CATEGORIAS = [
  "Antimicrobianos e Antibióticos",
  "Anti-inflamatórios e Analgésicos",
  "Fármacos Reprodutivos e Hormônios",
  "Antiparasitários (Ecto, Endo e Hemoparasiticidas)",
  "Metabólicos, Vitaminas e Minerais",
  "Biológicos (Vacinas e Diagnósticos)",
];

function ListaNomeAtivo({ titulo, icone: Icone, descricao, fetchFn, criarFn, atualizarFn, semRegistros, restaurarCatalogo, mostrarDetalhes }: {
  titulo: string; icone: any; descricao: string; semRegistros: string;
  fetchFn: () => Promise<Item[]>;
  criarFn: (dados: { nome: string; ativo?: boolean }) => Promise<Item>;
  atualizarFn: (id: number, dados: { nome: string; ativo: boolean }) => Promise<Item>;
  restaurarCatalogo?: () => Promise<{ criados: number; total: number }>;
  mostrarDetalhes?: boolean;
}) {
  const [itens, setItens] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [detalhado, setDetalhado] = useState<number | null>(null);
  const [form, setForm] = useState<Form>(formVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [restaurando, setRestaurando] = useState(false);

  const carregar = () => fetchFn().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const restaurar = async () => {
    if (!restaurarCatalogo) return;
    setRestaurando(true); setMsg(null);
    try { const r = await restaurarCatalogo(); await carregar(); setMsg(`Catálogo restaurado: ${r.criados} adicionado(s), ${r.total} no total.`); }
    catch (e: any) { setMsg(e.message || "Erro ao restaurar catálogo"); }
    finally { setRestaurando(false); }
  };

  const abrirNovo = () => { setForm(formVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (i: Item) => { setForm({ nome: i.nome, ativo: i.ativo }); setEditando(i.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = { nome: form.nome.trim(), ativo: form.ativo };
      if (editando === "novo") await criarFn(dados);
      else if (typeof editando === "number") await atualizarFn(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((i) => !termoBusca || normalizar(i.nome).includes(termoBusca));
  const nCols = mostrarDetalhes ? 3 : 2;

  const grupos = mostrarDetalhes
    ? ORDEM_CATEGORIAS
        .map((nome) => ({ nome, itens: filtrados.filter((i) => i.categoria === nome) }))
        .concat([{ nome: "Outros", itens: filtrados.filter((i) => !i.categoria || !ORDEM_CATEGORIAS.includes(i.categoria)) }])
        .filter((g) => g.itens.length > 0)
    : null;

  const renderLinha = (i: Item) => (
    <Fragment key={i.id}>
      <tr>
        <td style={{ fontWeight: 700 }}>
          {mostrarDetalhes && (i.uso_principal || i.justificativa || i.categoria_software) ? (
            <button onClick={() => setDetalhado(detalhado === i.id ? null : i.id)}
              style={{ display: "flex", alignItems: "center", gap: "0.35rem", background: "none", border: "none", cursor: "pointer", color: "inherit", font: "inherit", padding: 0, textAlign: "left" }}>
              {detalhado === i.id ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {i.nome}
            </button>
          ) : i.nome}
          {!i.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}
        </td>
        {mostrarDetalhes && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{i.categoria_software || "—"}</td>}
        <td style={{ textAlign: "right" }}>
          <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(i)}>
            <Pencil size={13} /> Editar
          </button>
        </td>
      </tr>
      {mostrarDetalhes && detalhado === i.id && (
        <tr><td colSpan={nCols} style={{ background: "var(--surface-2)", fontSize: "0.8rem", padding: "0.7rem 1rem" }}>
          <div style={{ marginBottom: "0.4rem" }}><strong>Uso principal:</strong> {i.uso_principal || "—"}</div>
          <div><strong>Justificativa de estoque:</strong> {i.justificativa || "—"}</div>
        </td></tr>
      )}
      {editando === i.id && (
        <tr><td colSpan={nCols} style={{ padding: 0 }}>
          <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />
        </td></tr>
      )}
    </Fragment>
  );

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Icone size={16} /> {titulo}</span>
        <div className="flex items-center gap-2">
          {restaurarCatalogo && (
            <button className="btn-ghost" style={{ fontSize: "0.76rem" }} onClick={restaurar} disabled={restaurando}
              title="(Re)carrega o catálogo base de princípios ativos (documento base) — só adiciona os que faltam.">
              {restaurando ? "Restaurando…" : "Restaurar catálogo base"}
            </button>
          )}
          <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
            <Plus size={14} /> Novo
          </button>
        </div>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>{descricao}</p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {restaurarCatalogo && msg && editando === null && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{msg}</p>}

      {editando === "novo" && <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder={`Buscar em ${titulo.toLowerCase()}…`} title="Buscar por nome" />
          </div>
          <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Nome</th>{mostrarDetalhes && <th>Categoria (software)</th>}<th></th></tr></thead>
            <tbody>
              {grupos
                ? grupos.map((g) => (
                    <Fragment key={g.nome}>
                      <tr><td colSpan={nCols} style={{ background: "var(--surface-2)", fontWeight: 700, fontSize: "0.74rem", color: "var(--dourado-light)", padding: "0.4rem 0.7rem" }}>{g.nome}</td></tr>
                      {g.itens.map(renderLinha)}
                    </Fragment>
                  ))
                : filtrados.map(renderLinha)}
              {!itens.length && !editando && <tr><td colSpan={nCols} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{semRegistros}</td></tr>}
              {!!itens.length && !filtrados.length && <tr><td colSpan={nCols} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
            </tbody>
          </table>
          </div>
        </>
      )}
    </div>
  );
}

function FormItem({ form, setForm, onSalvar, onCancelar, salvando, msg }: FormItemProps) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
      </div>
      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onSalvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}

// ── Princípio ativo — cadastro rico (categoria/uso/justificativa/doença e
// marcas comerciais vinculadas) ─────────────────────────────────────────────
// Usa os endpoints da Farmácia (/farmacia/principios e /farmacia/medicamentos),
// que já suportam esses campos — a lista simples nome+ativo (ListaNomeAtivo)
// continua servindo só para Doença, que não tem esse enriquecimento.
type PrincipioForm = {
  nome: string; ativo: boolean; categoria: string; categoria_software: string;
  uso_principal: string; justificativa: string; eh_biologico: boolean; doenca_id: string;
};
const principioFormVazio = (): PrincipioForm => ({
  nome: "", ativo: true, categoria: "", categoria_software: "",
  uso_principal: "", justificativa: "", eh_biologico: false, doenca_id: "",
});

function ListaPrincipiosAtivos() {
  const [itens, setItens] = useState<PrincipioFarmacia[] | null>(null);
  const [doencas, setDoencas] = useState<{ id: number; nome: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [detalhado, setDetalhado] = useState<number | null>(null);
  const [form, setForm] = useState<PrincipioForm>(principioFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [restaurando, setRestaurando] = useState(false);
  const [marcas, setMarcas] = useState<Record<number, MarcaComercial[]>>({});
  const [novaMarca, setNovaMarca] = useState({ nome_comercial: "", laboratorio: "" });
  const [indicacoes, setIndicacoes] = useState<Record<number, IndicacaoTerapeutica[]>>({});
  const [novaIndicacao, setNovaIndicacao] = useState({ doenca_id: "", prioridade: "1" });

  const carregar = () => fetchFarmaciaPrincipios().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); fetchDoencas().then(setDoencas).catch(() => {}); }, []);

  const carregarMarcas = (id: number) =>
    fetchFarmaciaDetalhe(id).then((d: any) => setMarcas((m) => ({ ...m, [id]: d.marcas || [] }))).catch(() => {});
  const carregarIndicacoes = (id: number) =>
    fetchIndicacoes(id).then((r: IndicacaoTerapeutica[]) => setIndicacoes((m) => ({ ...m, [id]: r }))).catch(() => {});

  const restaurar = async () => {
    setRestaurando(true); setMsg(null);
    try { const r = await restaurarCatalogoPrincipios(); await carregar(); setMsg(`Catálogo restaurado: ${r.criados} adicionado(s), ${r.total} no total.`); }
    catch (e: any) { setMsg(e.message || "Erro ao restaurar catálogo"); }
    finally { setRestaurando(false); }
  };

  const abrirNovo = () => { setForm(principioFormVazio()); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (i: PrincipioFarmacia) => {
    setForm({
      nome: i.nome, ativo: i.ativo, categoria: i.categoria || "",
      categoria_software: i.categoria_software || "", uso_principal: i.uso_principal || "",
      justificativa: i.justificativa || "", eh_biologico: i.eh_biologico, doenca_id: i.doenca_id ? String(i.doenca_id) : "",
    });
    setEditando(i.id); setMsg(null);
    carregarMarcas(i.id);
    carregarIndicacoes(i.id);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    setSalvando(true); setMsg(null);
    const dados = {
      nome: form.nome.trim(), ativo: form.ativo, categoria: form.categoria || null,
      categoria_software: form.categoria_software.trim() || null,
      uso_principal: form.uso_principal.trim() || null, justificativa: form.justificativa.trim() || null,
      eh_biologico: form.eh_biologico, doenca_id: form.eh_biologico && form.doenca_id ? Number(form.doenca_id) : null,
    };
    try {
      if (editando === "novo") {
        const criado = await criarPrincipioFarmacia(dados);
        await carregar();
        // Mantém aberto no registro recém-criado — permite cadastrar as marcas
        // comerciais (ex.: "VACINA RB 51") na sequência, sem reabrir a edição.
        setEditando(criado.id);
        carregarMarcas(criado.id);
      } else if (typeof editando === "number") {
        await atualizarPrincipioFarmacia(editando, dados);
        setEditando(null);
        await carregar();
      }
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const adicionarMarca = async (principioId: number) => {
    if (!novaMarca.nome_comercial.trim()) return;
    try {
      await criarMarcaFarmacia({
        principio_ativo_id: principioId, nome_comercial: novaMarca.nome_comercial.trim(),
        laboratorio: novaMarca.laboratorio.trim() || undefined,
      });
      setNovaMarca({ nome_comercial: "", laboratorio: "" });
      await carregarMarcas(principioId);
    } catch (e: any) {
      setMsg(e.message || "Erro ao adicionar marca comercial");
    }
  };
  const removerMarca = async (principioId: number, marcaId: number) => {
    try { await excluirMarcaFarmacia(marcaId); await carregarMarcas(principioId); }
    catch (e: any) { setMsg(e.message || "Erro ao excluir marca comercial"); }
  };

  const adicionarIndicacao = async (principioId: number) => {
    if (!novaIndicacao.doenca_id) return;
    try {
      await criarIndicacao({
        principio_ativo_id: principioId, doenca_id: Number(novaIndicacao.doenca_id),
        prioridade: Number(novaIndicacao.prioridade),
      });
      setNovaIndicacao({ doenca_id: "", prioridade: "1" });
      await carregarIndicacoes(principioId);
    } catch (e: any) {
      setMsg(e.message || "Erro ao adicionar doença indicada");
    }
  };
  const removerIndicacao = async (principioId: number, indicacaoId: number) => {
    try { await excluirIndicacao(indicacaoId); await carregarIndicacoes(principioId); }
    catch (e: any) { setMsg(e.message || "Erro ao excluir doença indicada"); }
  };
  const labelPrioridade = (p: number) => (p === 1 ? "1ª escolha" : p === 2 ? "2ª opção" : p === 3 ? "3ª opção" : `${p}ª opção`);

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((i) => !termoBusca || normalizar(i.nome).includes(termoBusca));
  const grupos = ORDEM_CATEGORIAS
    .map((nome) => ({ nome, itens: filtrados.filter((i) => i.categoria === nome) }))
    .concat([{ nome: "Outros", itens: filtrados.filter((i) => !i.categoria || !ORDEM_CATEGORIAS.includes(i.categoria)) }])
    .filter((g) => g.itens.length > 0);

  const formEl = (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
        <div><label style={labelStyle}>Categoria</label>
          <select style={inputStyle} value={form.categoria} onChange={(e) => setForm({ ...form, categoria: e.target.value })}>
            <option value="">—</option>{ORDEM_CATEGORIAS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
        <div><label style={labelStyle}>Categoria (software)</label>
          <input style={inputStyle} value={form.categoria_software} onChange={(e) => setForm({ ...form, categoria_software: e.target.value })} placeholder='ex.: "Antibiótico Sistêmico"' /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.eh_biologico} onChange={(e) => setForm({ ...form, eh_biologico: e.target.checked, doenca_id: e.target.checked ? form.doenca_id : "" })} /> É biológico (vacina/diagnóstico)</label></div>
        {form.eh_biologico && (
          <div><label style={labelStyle}>Doença combatida</label>
            <select style={inputStyle} value={form.doenca_id} onChange={(e) => setForm({ ...form, doenca_id: e.target.value })}>
              <option value="">—</option>{doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
            </select></div>
        )}
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Uso principal</label>
          <textarea style={{ ...inputStyle, minHeight: "3.2rem", resize: "vertical" }} value={form.uso_principal} onChange={(e) => setForm({ ...form, uso_principal: e.target.value })} /></div>
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Justificativa de estoque</label>
          <textarea style={{ ...inputStyle, minHeight: "3.2rem", resize: "vertical" }} value={form.justificativa} onChange={(e) => setForm({ ...form, justificativa: e.target.value })} /></div>
      </div>

      {typeof editando === "number" && (
        <div style={{ marginBottom: "0.8rem" }}>
          <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.4rem" }}>Marcas comerciais</p>
          {(marcas[editando] || []).map((m) => (
            <div key={m.id} className="flex items-center gap-2" style={{ fontSize: "0.8rem", marginBottom: "0.3rem" }}>
              <span style={{ flex: 1 }}>{m.nome_comercial}{m.laboratorio ? ` — ${m.laboratorio}` : ""}</span>
              <button className="btn-ghost" style={{ fontSize: "0.7rem" }} onClick={() => removerMarca(editando, m.id)}><Trash2 size={12} /></button>
            </div>
          ))}
          {!(marcas[editando] || []).length && <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.3rem" }}>Nenhuma marca comercial cadastrada ainda.</p>}
          <div className="flex items-center gap-2" style={{ marginTop: "0.4rem" }}>
            <input style={{ ...inputStyle, flex: 1 }} placeholder='Nome comercial (ex.: "VACINA RB 51")' value={novaMarca.nome_comercial}
              onChange={(e) => setNovaMarca({ ...novaMarca, nome_comercial: e.target.value })} />
            <input style={{ ...inputStyle, flex: 1 }} placeholder="Laboratório (opcional)" value={novaMarca.laboratorio}
              onChange={(e) => setNovaMarca({ ...novaMarca, laboratorio: e.target.value })} />
            <button className="btn-ghost" style={{ fontSize: "0.76rem", whiteSpace: "nowrap" }} onClick={() => adicionarMarca(editando)}>
              <Plus size={13} /> Adicionar
            </button>
          </div>
        </div>
      )}

      {typeof editando === "number" && (
        <div style={{ marginBottom: "0.8rem" }}>
          <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.4rem" }}>Doenças indicadas</p>
          {(indicacoes[editando] || []).map((ind) => (
            <div key={ind.id} className="flex items-center gap-2" style={{ fontSize: "0.8rem", marginBottom: "0.3rem" }}>
              <span style={{ flex: 1 }}>{ind.doenca} — {labelPrioridade(ind.prioridade)}</span>
              <button className="btn-ghost" style={{ fontSize: "0.7rem" }} onClick={() => removerIndicacao(editando, ind.id)}><Trash2 size={12} /></button>
            </div>
          ))}
          {!(indicacoes[editando] || []).length && <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.3rem" }}>Nenhuma doença indicada ainda.</p>}
          <div className="flex items-center gap-2" style={{ marginTop: "0.4rem" }}>
            <select style={{ ...inputStyle, flex: 1 }} value={novaIndicacao.doenca_id}
              onChange={(e) => setNovaIndicacao({ ...novaIndicacao, doenca_id: e.target.value })}>
              <option value="">Selecione a doença…</option>{doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
            </select>
            <select style={{ ...inputStyle, flex: 1 }} value={novaIndicacao.prioridade}
              onChange={(e) => setNovaIndicacao({ ...novaIndicacao, prioridade: e.target.value })}>
              <option value="1">1ª escolha</option>
              <option value="2">2ª opção</option>
              <option value="3">3ª opção</option>
            </select>
            <button className="btn-ghost" style={{ fontSize: "0.76rem", whiteSpace: "nowrap" }} onClick={() => adicionarIndicacao(editando)}>
              <Plus size={13} /> Adicionar
            </button>
          </div>
        </div>
      )}

      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Syringe size={16} /> Princípios ativos</span>
        <div className="flex items-center gap-2">
          <button className="btn-ghost" style={{ fontSize: "0.76rem" }} onClick={restaurar} disabled={restaurando}
            title="(Re)carrega o catálogo base de princípios ativos (documento base) — só adiciona os que faltam.">
            {restaurando ? "Restaurando…" : "Restaurar catálogo base"}
          </button>
          <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
            <Plus size={14} /> Novo
          </button>
        </div>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Hierarquia do estoque de medicamentos, hormônios e vacinas — agrupados por categoria, com uso principal e
        justificativa de estoque do documento base. Marcas comerciais (ex.: "VACINA RB 51") ficam vinculadas a cada princípio.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {msg && editando === null && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{msg}</p>}

      {editando === "novo" && formEl}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar em princípios ativos…" />
          </div>
          <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Nome</th><th>Categoria (software)</th><th>Marcas</th><th></th></tr></thead>
            <tbody>
              {grupos.map((g) => (
                <Fragment key={g.nome}>
                  <tr><td colSpan={4} style={{ background: "var(--surface-2)", fontWeight: 700, fontSize: "0.74rem", color: "var(--dourado-light)", padding: "0.4rem 0.7rem" }}>{g.nome}</td></tr>
                  {g.itens.map((i) => (
                    <Fragment key={i.id}>
                      <tr>
                        <td style={{ fontWeight: 700 }}>
                          {(i.uso_principal || i.justificativa || i.categoria_software) ? (
                            <button onClick={() => setDetalhado(detalhado === i.id ? null : i.id)}
                              style={{ display: "flex", alignItems: "center", gap: "0.35rem", background: "none", border: "none", cursor: "pointer", color: "inherit", font: "inherit", padding: 0, textAlign: "left" }}>
                              {detalhado === i.id ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {i.nome}
                            </button>
                          ) : i.nome}
                          {!i.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}
                        </td>
                        <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{i.categoria_software || "—"}</td>
                        <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{i.qtd_marcas_estoque || 0}</td>
                        <td style={{ textAlign: "right" }}>
                          <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(i)}>
                            <Pencil size={13} /> Editar
                          </button>
                        </td>
                      </tr>
                      {detalhado === i.id && (
                        <tr><td colSpan={4} style={{ background: "var(--surface-2)", fontSize: "0.8rem", padding: "0.7rem 1rem" }}>
                          <div style={{ marginBottom: "0.4rem" }}><strong>Uso principal:</strong> {i.uso_principal || "—"}</div>
                          <div><strong>Justificativa de estoque:</strong> {i.justificativa || "—"}</div>
                        </td></tr>
                      )}
                      {editando === i.id && <tr><td colSpan={4} style={{ padding: 0 }}>{formEl}</td></tr>}
                    </Fragment>
                  ))}
                </Fragment>
              ))}
              {!itens.length && !editando && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum princípio ativo cadastrado ainda.</td></tr>}
              {!!itens.length && !filtrados.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
            </tbody>
          </table>
          </div>
        </>
      )}
    </div>
  );
}
