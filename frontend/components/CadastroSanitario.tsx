"use client";
import { Fragment, useEffect, useRef, useState } from "react";
import { ClipboardList, Plus, Pencil, AlertTriangle, Trash2, Search, Upload, Download, Milk } from "lucide-react";
import {
  fetchPrincipiosAtivos,
  fetchDoencas,
  fetchProtocolosSanitarios, criarProtocoloSanitario, atualizarProtocoloSanitario, excluirProtocoloSanitario, importarProtocoloSanitarioExcel,
  fetchProtocolosInducaoLactacaoCadastro, criarProtocoloInducaoLactacao, atualizarProtocoloInducaoLactacao, excluirProtocoloInducaoLactacao,
  fetchEstoque,
  type ProtocoloEtapa,
  type EtapaInducaoLactacao, type ProtocoloInducaoLactacaoCadastro, type ProtocoloInducaoLactacaoPayload,
  formatarDoseEtapa,
} from "@/lib/api";
import { exportarExcel } from "@/lib/export";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { EstoquePicker, type EstoqueItemPicker } from "./EstoquePicker";
import { VIAS_APLICACAO } from "@/lib/constants";
import { CLASSIFICACOES_MEDICAMENTO } from "@/lib/api";
import { normalizarBusca as normalizar } from "@/lib/busca";
import { WizardProtocolo, type PassoWizard } from "@/components/protocolos/WizardProtocolo";
import { Modal } from "@/components/Modal";

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

// Evento sanitário e Exames (preventivo antigo) saíram: vacinas e exames são
// cadastrados na Central de Protocolos › Cadastro › Sanidade › Preventiva
// (Sanitário Preventivo v2).
const ABAS = [
  ["protocolos", "Protocolo sanitário", ClipboardList],
  ["inducao", "Indução de lactação", Milk],
] as const;
// Reexportado para o Cadastro compor a árvore de sub-navegação (Configurações
// › Cadastro › Sanitário › estas abas) sem duplicar rótulos/ícones.
export type AbaCadastroSanitario = (typeof ABAS)[number][0];
export const ABAS_CADASTRO_SANITARIO = ABAS;

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const buscaInputStyle: React.CSSProperties = { width: "100%", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.75rem 0.5rem 2rem", fontSize: "0.85rem" };

// Aceita controle externo (Cadastro precisa da aba ativa para compor a
// árvore de sub-navegação Configurações › Cadastro › Sanitário) — sem props,
// funciona como antes, com estado próprio.
export default function CadastroSanitario({ abaControlada }: {
  abaControlada?: AbaCadastroSanitario; onAbaChange?: (id: AbaCadastroSanitario) => void;
} = {}) {
  const [abaInterna] = useState<AbaCadastroSanitario>("protocolos");
  const aba = abaControlada ?? abaInterna;

  return (
    <div>
      {aba === "protocolos" && <CadastroProtocolosSanitarios />}
      {aba === "inducao" && <CadastroProtocolosInducao />}
    </div>
  );
}

type Protocolo = {
  id: number; nome: string; doenca_id: number | null; doenca_nome: string | null; eh_mastite: boolean; ativo: boolean;
  finalidade?: string | null;  // curativo | preventivo (null em protocolo antigo = curativo)
  dia_inicial?: number;
  etapas: ProtocoloEtapa[];
};
type ProtocoloForm = { nome: string; doenca_id: string; eh_mastite: boolean; dia_inicial: number; finalidade: string; ativo: boolean; etapas: ProtocoloEtapa[] };
const etapaVazia = (dia: number): ProtocoloEtapa => ({ dia, criterio_tipo: "medicamento", produto: "", dosagem: 0, unidade: "ml", via: "", observacao: "" });
// Protocolos novos nascem em D0 (mesmo padrão da indução de lactação); um
// protocolo já existente que veio com dia_inicial=1 (pré-padronização D0)
// mantém o próprio dia_inicial ao ser editado — ver abrirEdicao.
const protocoloFormVazio = (): ProtocoloForm => ({ nome: "", doenca_id: "", eh_mastite: false, dia_inicial: 0, finalidade: "curativo", ativo: true, etapas: [etapaVazia(0)] });

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
  // Prévia somente-leitura do cronograma — antes só existia no passo 4
  // ("Revisão") do assistente de edição, obrigando a clicar Editar e navegar
  // 3 passos só para conferir produto/dose/via de um protocolo já pronto.
  const [verCronograma, setVerCronograma] = useState<Protocolo | null>(null);

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
      dia_inicial: p.dia_inicial ?? 0, finalidade: p.finalidade || "curativo", ativo: p.ativo,
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

  // Devolve true só quando salvou de verdade — é o sinal que o wizard usa
  // para limpar o rascunho do localStorage (ver WizardProtocolo.onConcluir).
  const salvar = async (): Promise<boolean> => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return false; }
    if (form.etapas.some((e) => e.dia < 0)) { setMsg("O dia da etapa não pode ser negativo (o protocolo pode começar em D0)."); return false; }
    if (form.etapas.some((e) => !e.produto.trim() || !e.dosagem || Number(e.dosagem) <= 0)) { setMsg("Preencha produto e dosagem em todas as etapas."); return false; }
    setSalvando(true); setMsg(null);
    try {
      const dados = {
        nome: form.nome.trim(), doenca_id: form.doenca_id ? Number(form.doenca_id) : undefined,
        eh_mastite: form.eh_mastite, dia_inicial: form.dia_inicial, finalidade: form.finalidade, ativo: form.ativo,
        etapas: form.etapas.map((e) => ({ ...e, dia: Number(e.dia), dosagem: Number(e.dosagem), via: e.via || undefined, observacao: e.observacao || undefined })),
      };
      if (editando === "novo") await criarProtocoloSanitario(dados);
      else if (typeof editando === "number") await atualizarProtocoloSanitario(editando, dados);
      setEditando(null);
      await carregar();
      return true;
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
      return false;
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
    <>
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
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
                  <ThOrdenavel label="Finalidade" campo="finalidade" coluna={ordProtocolos.coluna} dir={ordProtocolos.dir} ordenar={ordProtocolos.ordenar} />
                  <ThOrdenavel label="Mastite" campo="eh_mastite" coluna={ordProtocolos.coluna} dir={ordProtocolos.dir} ordenar={ordProtocolos.ordenar} />
                  <th>Etapas</th><th></th>
                </tr></thead>
                <tbody>
                  {ordProtocolos.linhasOrdenadas.map((p) => (
                    <tr key={p.id}>
                      <td style={{ fontWeight: 700 }}>{p.nome}{!p.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                      <td style={{ fontSize: "0.78rem" }}>{p.doenca_nome || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{(p.finalidade || "curativo") === "preventivo" ? "Preventivo" : "Curativo"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{p.eh_mastite ? "Sim" : "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{p.etapas.map((e) => `D${e.dia - (p.dia_inicial ?? 0)}`).join(", ")}</td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} onClick={() => setVerCronograma(p)} title="Ver produto, dose e via de cada etapa, sem entrar em edição">
                          <Search size={13} /> Ver cronograma
                        </button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", marginLeft: "0.4rem" }} onClick={() => abrirEdicao(p)}>
                          <Pencil size={13} /> Editar
                        </button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", color: "var(--red)", marginLeft: "0.4rem" }}
                          onClick={() => excluir(p)} disabled={excluindo === p.id} title="Excluir protocolo — só é possível se ele nunca foi lançado">
                          <Trash2 size={13} /> {excluindo === p.id ? "Excluindo…" : "Excluir"}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!itens.length && !editando && <tr><td colSpan={6} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo cadastrado ainda.</td></tr>}
                  {!!itens.length && !filtrados.length && <tr><td colSpan={6} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
                </tbody>
              </table>
              </div>
            </>
          )}
        </div>
      </div>
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
        {editando !== null ? (
          <FormProtocolo
            key={editando} form={form} setForm={setForm} doencas={doencas} estoque={estoque} principios={principios}
            onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} editando={editando}
            acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
          />
        ) : (
          <div className="card" style={{ textAlign: "center", padding: "2.2rem 1rem" }}>
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Selecione um protocolo para editar, ou clique em Novo.</p>
          </div>
        )}
      </div>
    </div>
    {verCronograma && (
      <Modal title={`Cronograma — ${verCronograma.nome}`} onClose={() => setVerCronograma(null)} width="640px">
        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
          Prévia somente-leitura, para conferir produto, dose e via de cada etapa antes de lançar. Para alterar, feche e use Editar.
        </p>
        <table className="fazenda-table">
          <thead><tr><th>Dia</th><th>Produto</th><th>Dose</th><th>Via</th></tr></thead>
          <tbody>
            {verCronograma.etapas.map((e, idx) => (
              <tr key={idx}>
                <td>D{e.dia - (verCronograma.dia_inicial ?? 0)}</td>
                <td>{e.produto || "—"}</td>
                <td>{formatarDoseEtapa(e)}</td>
                <td>{e.via || "—"}</td>
              </tr>
            ))}
            {!verCronograma.etapas.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)" }}>Nenhuma etapa cadastrada.</td></tr>}
          </tbody>
        </table>
      </Modal>
    )}
    </>
  );
}

// Wizard de 4 etapas (redesign "Cooperativa", T5) — divisão escolhida para o
// Sanitário curativo:
//  1. Identificação — nome + ativo (o mínimo para existir um protocolo).
//  2. Critérios — doença combatida, finalidade e a flag de mastite: definem
//     PARA QUE situação este protocolo serve (o equivalente, num cadastro de
//     molde, ao "quem é elegível" — aqui não há animal para filtrar ainda,
//     só o contexto clínico que o protocolo atende).
//  3. Roteiro (etapas) — o coração do protocolo: o cronograma D0/D1/D2...
//     com produto, dosagem, via — conteúdo que já existia, só reagrupado.
//  4. Revisão — resumo antes de gravar, com o botão que efetivamente salva
//     (a validação completa do endpoint continua rodando aqui, sem mudança).
function FormProtocolo({ form, setForm, doencas, estoque, principios, onSalvar, onCancelar, salvando, msg, editando, acrescentarEtapa, removerEtapa, atualizarEtapa }: {
  form: ProtocoloForm; setForm: (f: ProtocoloForm) => void; doencas: { id: number; nome: string }[]; estoque: EstoqueItemPicker[];
  principios: { id: number; nome: string }[];
  onSalvar: () => Promise<boolean>; onCancelar: () => void; salvando: boolean; msg: string | null; editando: number | "novo";
  acrescentarEtapa: () => void; removerEtapa: (idx: number) => void; atualizarEtapa: (idx: number, patch: Partial<ProtocoloEtapa>) => void;
}) {
  const passos: PassoWizard<ProtocoloForm>[] = [
    {
      id: "identificacao", titulo: "Identificação",
      validar: (f) => (!f.nome.trim() ? "Informe o nome do protocolo." : null),
      render: ({ form: f, setForm: sf }) => (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Nome</label>
            <input style={inputStyle} value={f.nome} onChange={(e) => sf({ ...f, nome: e.target.value })} placeholder="ex.: Mastite clínica padrão" autoFocus /></div>
          <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
            <input type="checkbox" checked={f.ativo} onChange={(e) => sf({ ...f, ativo: e.target.checked })} /> Ativo</label></div>
        </div>
      ),
    },
    {
      id: "criterios", titulo: "Critérios",
      render: ({ form: f, setForm: sf }) => (
        <div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div><label style={labelStyle}>Doença vinculada</label>
              <select style={inputStyle} value={f.doenca_id} onChange={(e) => sf({ ...f, doenca_id: e.target.value })}>
                <option value="">—</option>{doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
              </select></div>
            <div><label style={labelStyle}>Finalidade</label>
              <select style={inputStyle} value={f.finalidade} onChange={(e) => sf({ ...f, finalidade: e.target.value })}>
                <option value="curativo">Curativo (trata animal doente)</option>
                {/* "Preventivo" saiu das opções (decisão D3 do Sanitário Preventivo v2):
                    só aparece num protocolo antigo que já foi gravado assim. */}
                {f.finalidade === "preventivo" && <option value="preventivo">Preventivo (protocolo antigo)</option>}
              </select></div>
            <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
              <input type="checkbox" checked={f.eh_mastite} onChange={(e) => sf({ ...f, eh_mastite: e.target.checked })} /> É protocolo de mastite</label></div>
          </div>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            Protocolo sanitário é o tratamento curativo em <strong>dias fixos</strong> (D0/D1/D2…). Vacinas e exames ficam na
            Central de Protocolos › Cadastro › Sanidade › Preventiva.
            Marcar "É protocolo de mastite" habilita, no lançamento, os campos de CMT, teto afetado e classificação.
          </p>
        </div>
      ),
    },
    {
      id: "roteiro", titulo: "Roteiro",
      validar: (f) => {
        if (f.etapas.some((e) => e.dia < 0)) return "O dia da etapa não pode ser negativo (o protocolo pode começar em D0).";
        if (f.etapas.some((e) => !e.produto.trim() || !e.dosagem || Number(e.dosagem) <= 0)) return "Preencha produto e dosagem em todas as etapas.";
        return null;
      },
      render: ({ form: f }) => (
        <div>
          <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.4rem" }}>Etapas (D0, D1, D2...)</p>
          <div className="space-y-2 mb-2">
            {f.etapas.map((e, idx) => (
              <div key={idx} className="grid grid-cols-2 md:grid-cols-8 gap-2 items-end" style={{ background: "var(--surface)", padding: "0.5rem", borderRadius: "var(--r-sm)" }}>
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
                <div><label style={labelStyle}>Dosagem{(e.modo_dose === "por_peso") && <span style={{ color: "var(--text-muted)", fontWeight: 400 }}> (a cada X kg)</span>}</label>
                  <input type="number" inputMode="decimal" style={inputStyle} value={e.dosagem} onChange={(ev) => atualizarEtapa(idx, { dosagem: Number(ev.target.value) })} /></div>
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
                <div>
                  <label style={labelStyle}>Como calcular a dose</label>
                  <div className="flex gap-1">
                    <button type="button"
                      className={(e.modo_dose || "fixa") === "fixa" ? "btn-primary" : "btn-secondary"}
                      style={{ fontSize: "0.7rem", padding: "0.3rem 0.5rem", flex: 1 }}
                      onClick={() => atualizarEtapa(idx, { modo_dose: "fixa", dose_referencia_kg: null })}
                      title="Sempre a mesma dose, qualquer que seja o peso do animal">
                      Dose fixa
                    </button>
                    <button type="button"
                      className={e.modo_dose === "por_peso" ? "btn-primary" : "btn-secondary"}
                      style={{ fontSize: "0.7rem", padding: "0.3rem 0.5rem", flex: 1 }}
                      onClick={() => atualizarEtapa(idx, { modo_dose: "por_peso" })}
                      title="Calcula pelo peso do animal no lançamento — usa o último peso registrado, um peso lançado na hora, ou dose manual">
                      Por peso vivo
                    </button>
                  </div>
                </div>
                {e.modo_dose === "por_peso" && (
                  <div>
                    <label style={labelStyle}>A cada quantos kg de peso vivo</label>
                    <input type="number" inputMode="decimal" style={inputStyle} value={e.dose_referencia_kg ?? ""}
                      onChange={(ev) => atualizarEtapa(idx, { dose_referencia_kg: ev.target.value ? Number(ev.target.value) : null })}
                      placeholder="ex.: 15" />
                    <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", margin: "0.2rem 0 0" }}>
                      {e.dosagem > 0 && e.dose_referencia_kg
                        ? `"${formatarDoseEtapa(e)}" — no lançamento, cada animal recebe sua própria dose calculada pelo peso.`
                        : "Preencha dosagem e o peso de referência para ver a fórmula."}
                    </p>
                  </div>
                )}
                <div className="flex items-end gap-1">
                  <div style={{ flex: 1 }}><label style={labelStyle}>Observação</label>
                    <input style={inputStyle} value={e.observacao || ""} onChange={(ev) => atualizarEtapa(idx, { observacao: ev.target.value })} placeholder="ex.: Se necessário" /></div>
                  {f.etapas.length > 1 && <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => removerEtapa(idx)}><Trash2 size={13} /></button>}
                </div>
              </div>
            ))}
          </div>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={acrescentarEtapa}>
            <Plus size={14} /> Acrescentar etapa
          </button>
        </div>
      ),
    },
    {
      id: "revisao", titulo: "Revisão",
      render: ({ form: f }) => (
        <div>
          <p style={{ fontSize: "0.82rem", marginBottom: "0.6rem" }}>
            <strong>{f.nome || "(sem nome)"}</strong>{!f.ativo && <span style={{ color: "var(--text-muted)" }}> (inativo)</span>}
            {f.eh_mastite && <span style={{ color: "var(--dourado-light)" }}> — protocolo de mastite</span>}
          </p>
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
            Doença: {doencas.find((d) => String(d.id) === f.doenca_id)?.nome || "—"} ·{" "}
            Finalidade: {f.finalidade === "preventivo" ? "Preventivo" : "Curativo"}
          </p>
          <table className="fazenda-table">
            <thead><tr><th>Dia</th><th>Produto</th><th>Dosagem</th><th>Via</th></tr></thead>
            <tbody>
              {f.etapas.map((e, idx) => (
                <tr key={idx}><td>D{e.dia}</td><td>{e.produto || "—"}</td><td>{formatarDoseEtapa(e)}</td><td>{e.via || "—"}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ),
    },
  ];

  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
      <WizardProtocolo<ProtocoloForm>
        chaveRascunho={editando === "novo" ? "wizard-protocolo:sanitario-curativo" : null}
        form={form} setForm={setForm}
        ehVazio={(f) => !f.nome.trim() && !f.doenca_id && f.etapas.every((e) => !e.produto.trim() && !e.dosagem)}
        passos={passos}
        onCancelar={onCancelar}
        onConcluir={onSalvar}
        salvando={salvando}
        rotuloConcluir="Salvar"
        erro={msg}
      />
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

// Exportado para a Central de Protocolos (app/protocolos) reaproveitar o
// MESMO editor usado aqui em Configurações — dois lugares de acesso, um só
// formulário e um só endpoint, para os dois nunca divergirem.
export function CadastroProtocolosInducao() {
  const [itens, setItens] = useState<ProtocoloInducaoLactacaoCadastro[] | null>(null);
  const [principios, setPrincipios] = useState<{ id: number; nome: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<ProtocoloInducaoForm>(protocoloInducaoFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [excluindo, setExcluindo] = useState<number | null>(null);
  const [erroExclusao, setErroExclusao] = useState<string | null>(null);

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

  // Bloqueado no backend (409) se o protocolo já foi lançado alguma vez —
  // nesse caso o usuário desativa em vez de excluir (checkbox "Ativo").
  const excluir = async (p: ProtocoloInducaoLactacaoCadastro) => {
    if (!window.confirm(`Excluir o protocolo "${p.nome}"? Isso não pode ser desfeito.`)) return;
    setExcluindo(p.id); setErroExclusao(null);
    try {
      await excluirProtocoloInducaoLactacao(p.id);
      await carregar();
    } catch (e: any) {
      setErroExclusao(e.message || "Erro ao excluir protocolo");
    } finally {
      setExcluindo(null);
    }
  };

  const acrescentarEtapa = () => setForm((f) => ({ ...f, etapas: [...f.etapas, etapaInducaoVazia(f.etapas.length)] }));
  const removerEtapa = (idx: number) => setForm((f) => (f.etapas.length > 1 ? { ...f, etapas: f.etapas.filter((_, i) => i !== idx) } : f));
  const atualizarEtapa = (idx: number, patch: Partial<EtapaInducaoLactacao>) =>
    setForm((f) => ({ ...f, etapas: f.etapas.map((e, i) => (i === idx ? { ...e, ...patch } : e)) }));

  const salvar = async (): Promise<boolean> => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return false; }
    if (form.etapas.some((e) => e.dia < 0)) { setMsg("O dia da etapa não pode ser negativo (o protocolo pode começar em D0)."); return false; }
    if (form.etapas.some((e) => !e.produto.trim())) { setMsg("Preencha o produto/ação de todas as etapas."); return false; }
    if (form.etapas.some((e) => e.tipo === "dispositivo" && !e.acao_dispositivo)) { setMsg("Etapa de dispositivo precisa dizer se é para colocar ou retirar."); return false; }
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
      return true;
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
      return false;
    } finally {
      setSalvando(false);
    }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((p) => !termoBusca || normalizar(p.nome).includes(termoBusca));
  const ordProtocolos = useOrdenacao(filtrados);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
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

          {erroExclusao && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>{erroExclusao}</p>}
          {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
          {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

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
                    <tr key={p.id}>
                      <td style={{ fontWeight: 700 }}>{p.nome}{!p.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                      <td style={{ fontSize: "0.78rem" }}>{p.etapas.length ? `D${p.dia_inicial} a D${Math.max(...p.etapas.map((e) => e.dia))}` : "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{p.etapas.length} etapa(s)</td>
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
                  ))}
                  {!itens.length && !editando && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum protocolo cadastrado ainda.</td></tr>}
                  {!!itens.length && !filtrados.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
                </tbody>
              </table>
              </div>
            </>
          )}
        </div>
      </div>
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
        {editando !== null ? (
          <FormProtocoloInducao
            key={editando} form={form} setForm={setForm} principios={principios} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} editando={editando}
            acrescentarEtapa={acrescentarEtapa} removerEtapa={removerEtapa} atualizarEtapa={atualizarEtapa}
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

// Wizard de 4 etapas (T5) para a Indução de lactação — divisão escolhida:
//  1. Identificação — nome + ativo.
//  2. Critérios — aqui a única informação de contexto além do nome é a
//     observação livre (este tipo não tem doença/finalidade/categoria-alvo
//     como o Sanitário); mesmo com um campo só, mantém a mesma forma dos
//     demais tipos para o usuário não precisar reaprender o fluxo a cada
//     protocolo que cadastra.
//  3. Roteiro (etapas) — o cronograma D0/D1/D2... com os 3 tipos de etapa
//     (medicamento/dispositivo/manejo), já existente.
//  4. Revisão — resumo antes de gravar.
function FormProtocoloInducao({ form, setForm, principios, onSalvar, onCancelar, salvando, msg, editando, acrescentarEtapa, removerEtapa, atualizarEtapa }: {
  form: ProtocoloInducaoForm; setForm: (f: ProtocoloInducaoForm) => void; principios: { id: number; nome: string }[];
  onSalvar: () => Promise<boolean>; onCancelar: () => void; salvando: boolean; msg: string | null; editando: number | "novo";
  acrescentarEtapa: () => void; removerEtapa: (idx: number) => void; atualizarEtapa: (idx: number, patch: Partial<EtapaInducaoLactacao>) => void;
}) {
  const passos: PassoWizard<ProtocoloInducaoForm>[] = [
    {
      id: "identificacao", titulo: "Identificação",
      validar: (f) => (!f.nome.trim() ? "Informe o nome do protocolo." : null),
      render: ({ form: f, setForm: sf }) => (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Nome</label>
            <input style={inputStyle} value={f.nome} onChange={(e) => sf({ ...f, nome: e.target.value })} placeholder="ex.: Protocolo de Indução — 18 dias" autoFocus /></div>
          <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
            <input type="checkbox" checked={f.ativo} onChange={(e) => sf({ ...f, ativo: e.target.checked })} /> Ativo</label></div>
        </div>
      ),
    },
    {
      id: "criterios", titulo: "Critérios",
      render: ({ form: f, setForm: sf }) => (
        <div>
          <label style={labelStyle}>Observação</label>
          <input style={inputStyle} value={f.observacao} onChange={(e) => sf({ ...f, observacao: e.target.value })} placeholder="opcional" />
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
            Contexto geral do protocolo — ex.: para quais vacas/lactações costuma ser indicado. O roteiro dia a dia vem na próxima etapa.
          </p>
        </div>
      ),
    },
    {
      id: "roteiro", titulo: "Roteiro",
      validar: (f) => {
        if (f.etapas.some((e) => e.dia < 0)) return "O dia da etapa não pode ser negativo (o protocolo pode começar em D0).";
        if (f.etapas.some((e) => !e.produto.trim())) return "Preencha o produto/ação de todas as etapas.";
        if (f.etapas.some((e) => e.tipo === "dispositivo" && !e.acao_dispositivo)) return "Etapa de dispositivo precisa dizer se é para colocar ou retirar.";
        return null;
      },
      render: ({ form: f }) => (
        <div>
          <p style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700, marginBottom: "0.4rem" }}>Etapas (D0, D1, D2...)</p>
          <div className="space-y-2 mb-2">
            {f.etapas.map((e, idx) => (
              <div key={idx} className="grid grid-cols-2 md:grid-cols-8 gap-2 items-end" style={{ background: "var(--surface)", padding: "0.5rem", borderRadius: "var(--r-sm)" }}>
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
                  {f.etapas.length > 1 && <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => removerEtapa(idx)}><Trash2 size={13} /></button>}
                </div>
              </div>
            ))}
          </div>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={acrescentarEtapa}>
            <Plus size={14} /> Acrescentar etapa
          </button>
        </div>
      ),
    },
    {
      id: "revisao", titulo: "Revisão",
      render: ({ form: f }) => (
        <div>
          <p style={{ fontSize: "0.82rem", marginBottom: "0.8rem" }}>
            <strong>{f.nome || "(sem nome)"}</strong>{!f.ativo && <span style={{ color: "var(--text-muted)" }}> (inativo)</span>}
          </p>
          <table className="fazenda-table">
            <thead><tr><th>Dia</th><th>Tipo</th><th>Produto/ação</th><th>Dose</th></tr></thead>
            <tbody>
              {f.etapas.map((e, idx) => (
                <tr key={idx}>
                  <td>D{e.dia}</td>
                  <td>{TIPOS_ETAPA_INDUCAO.find(([v]) => v === e.tipo)?.[1] || e.tipo}</td>
                  <td>{e.tipo === "dispositivo" ? `${e.produto} (${e.acao_dispositivo || "?"})` : e.produto}</td>
                  <td>{e.tipo === "medicamento" && e.dose != null ? `${e.dose} ${e.unidade || ""}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ),
    },
  ];

  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
      <WizardProtocolo<ProtocoloInducaoForm>
        chaveRascunho={editando === "novo" ? "wizard-protocolo:inducao" : null}
        form={form} setForm={setForm}
        ehVazio={(f) => !f.nome.trim() && !f.observacao.trim() && f.etapas.every((e) => !e.produto.trim())}
        passos={passos}
        onCancelar={onCancelar}
        onConcluir={onSalvar}
        salvando={salvando}
        rotuloConcluir="Salvar"
        erro={msg}
      />
    </div>
  );
}
