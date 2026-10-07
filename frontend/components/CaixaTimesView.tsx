"use client";
// Caixa do time (participação nos lucros) e rateio — Fase 3 do Caixa dos funcionários.
// O dinheiro é do coletivo; em datas fixas (Parâmetros financeiros) é repartido pelos
// dias de cada membro, com penalidade documentada (art. 482 CLT) e destino por pessoa.
import { useEffect, useState } from "react";
import { ArrowLeft, Plus, Undo2, Users } from "lucide-react";
import { Modal } from "@/components/Modal";
import { CampoMoeda } from "@/components/CampoMoeda";
import { Dropzone } from "@/components/Dropzone";
import {
  fetchCaixasTime, fetchCaixaTime, criarCaixaTime, adicionarMembrosTime, removerMembroTime, lancarEntradaTime,
  estornarMovimentoTime, criarRateioTime, fetchRateioTime, ajustarLinhaRateio, excluirRascunhoRateio,
  confirmarRateioTime, desfazerRateioTime, fetchCaixasFuncionarios, anexarArquivoPessoa, formatBRL, formatDate,
  type CaixaTimeResumo, type CaixaTimeDetalhe, type CaixaRateio, type CaixaPessoaLinha, type CaixaRateioLinhaItem,
} from "@/lib/api";

const CATEGORIA_PENALIDADE = "Documento de ciência de penalidade";
const GRUPOS = [{ id: "clt", label: "CLT" }, { id: "empreita", label: "Empreita" }, { id: "contrato", label: "Contrato" }, { id: "diaria", label: "Diária" }];
const ROTULO_GRUPO: Record<string, string> = { clt: "CLT", empreita: "Empreita", contrato: "Contrato", diaria: "Diária" };
const TIPOS = [{ id: "deposito", label: "Depósito da fazenda" }, { id: "bonificacao", label: "Bonificação por produtividade" }, { id: "comissao", label: "Comissão" }, { id: "outro", label: "Outro tipo (sem especificar)" }];
const ROTULO_MOV: Record<string, string> = { deposito: "Depósito", bonificacao: "Bonificação", comissao: "Comissão", outro: "Outro", rateio: "Rateio do PL", estorno: "Estorno", retencao: "Retenção em folha" };
const FORMAS = [{ id: "pix", label: "Pix" }, { id: "dinheiro", label: "Dinheiro" }, { id: "transferencia", label: "Transferência" }];

const lbl = { display: "block", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem" } as const;
const campo = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.82rem",
} as const;
const hojeISO = () => new Date().toISOString().slice(0, 10);
const rotuloTipos = (t: string[]) => t.map((x) => ROTULO_GRUPO[x] || x).join(", ");

export default function CaixaTimesView() {
  const [times, setTimes] = useState<CaixaTimeResumo[] | null>(null);
  const [totalPl, setTotalPl] = useState(0);
  const [erro, setErro] = useState<string | null>(null);
  const [aberto, setAberto] = useState<number | null>(null);
  const [novo, setNovo] = useState(false);
  const carregar = () => fetchCaixasTime().then((d) => { setTimes(d.times); setTotalPl(d.total_pl); setErro(null); }).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  if (aberto != null) return <TimeDetalhe id={aberto} onVoltar={() => { setAberto(null); carregar(); }} />;
  return (
    <div>
      <div className="flex items-center justify-between" style={{ gap: "0.6rem", flexWrap: "wrap", marginBottom: "0.7rem" }}>
        <div className="card" style={{ padding: "0.6rem 0.9rem" }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Nos caixas do time (PL)</div>
          <strong style={{ fontSize: "1.15rem" }}>{formatBRL(totalPl)}</strong>
        </div>
        <button type="button" className="btn-primary" onClick={() => setNovo(true)}><Plus size={14} /> Novo caixa do time</button>
      </div>
      <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", maxWidth: "75ch" }}>
        Dinheiro do coletivo, repartido nas datas dos Parâmetros financeiros (padrão 01/06 e 01/12), em partes proporcionais aos dias de cada membro.
      </p>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      {times === null ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : (
        <table className="fazenda-table" style={{ minWidth: 560 }}>
          <thead><tr><th>Caixa</th><th>Membros</th><th style={{ textAlign: "right" }}>Saldo</th><th>Próxima entrega</th><th></th></tr></thead>
          <tbody>
            {times.map((t) => (
              <tr key={t.id}>
                <td>{t.nome}{t.auto_tipos.length > 0 && <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}> · todos: {rotuloTipos(t.auto_tipos)} (automático)</span>}</td>
                <td>{t.membros}</td><td style={{ textAlign: "right", fontWeight: 700 }}>{formatBRL(t.saldo)}</td>
                <td style={{ color: "var(--text-muted)" }}>{formatDate(t.proxima_entrega)}</td>
                <td style={{ textAlign: "right" }}><button type="button" className="btn-primary" style={{ fontSize: "0.72rem", padding: "0.15rem 0.6rem" }} onClick={() => setAberto(t.id)}>Abrir</button></td>
              </tr>
            ))}
            {!times.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)" }}>Nenhum caixa do time ainda. Crie um para guardar a participação nos lucros do grupo.</td></tr>}
          </tbody>
        </table>
      )}
      {novo && <NovoTimeModal onClose={() => setNovo(false)} onFeito={(t) => { setNovo(false); carregar(); setAberto(t.id); }} />}
    </div>
  );
}

function NovoTimeModal({ onClose, onFeito }: { onClose: () => void; onFeito: (t: CaixaTimeResumo) => void }) {
  const [nome, setNome] = useState("");
  const [tipos, setTipos] = useState<Set<string>>(new Set());
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  async function criar() {
    if (!nome.trim()) { setErro("Dê um nome ao caixa."); return; }
    setSalvando(true); setErro(null);
    try { onFeito(await criarCaixaTime({ nome: nome.trim(), auto_tipos: Array.from(tipos) })); }
    catch (e: any) { setErro(e.message); setSalvando(false); }
  }
  return (
    <Modal title="Novo caixa do time" onClose={onClose} width="460px">
      <label style={lbl} htmlFor="nt-nome">Nome</label>
      <input id="nt-nome" style={campo} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Turma da ordenha" />
      <label style={{ ...lbl, marginTop: "0.7rem" }}>Entram automaticamente (todos os ativos do tipo, atualiza sozinho)</label>
      <div className="flex" style={{ gap: "0.8rem", flexWrap: "wrap" }}>
        {GRUPOS.map((g) => (
          <label key={g.id} style={{ display: "flex", gap: "0.3rem", alignItems: "center", fontSize: "0.82rem", color: "var(--text)" }}>
            <input type="checkbox" checked={tipos.has(g.id)} onChange={() => setTipos((s) => { const n = new Set(s); n.has(g.id) ? n.delete(g.id) : n.add(g.id); return n; })} /> {g.label}
          </label>
        ))}
      </div>
      <p style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>Depois você pode acrescentar pessoas por nome.</p>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
      <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: "0.8rem" }}>
        <button type="button" className="btn-ghost" onClick={onClose} disabled={salvando}>Cancelar</button>
        <button type="button" className="btn-primary" onClick={criar} disabled={salvando}>Criar caixa</button>
      </div>
    </Modal>
  );
}

function TimeDetalhe({ id, onVoltar }: { id: number; onVoltar: () => void }) {
  const [t, setT] = useState<CaixaTimeDetalhe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [entrada, setEntrada] = useState(false);
  const [addMembro, setAddMembro] = useState(false);
  const [rateioId, setRateioId] = useState<number | null>(null);
  const [estornando, setEstornando] = useState<number | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const carregar = () => fetchCaixaTime(id).then((d) => { setT(d); setErro(null); }).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (rateioId != null) return <RateioTela rateioId={rateioId} onVoltar={() => { setRateioId(null); carregar(); }} />;
  if (!t) return <div>{erro ? <p role="alert" style={{ color: "var(--red)" }}>{erro}</p> : <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}<button type="button" className="btn-ghost" onClick={onVoltar}>Voltar</button></div>;

  const rascunho = t.rateios.find((r) => r.situacao === "rascunho");
  async function novoRateio() {
    setOcupado(true); setErro(null);
    try { const r = await criarRateioTime(id); setRateioId(r.id); } catch (e: any) { setErro(e.message); }
    setOcupado(false);
  }
  async function remover(pessoaId: number, nome: string) {
    if (!window.confirm(`Dar saída de ${nome} deste caixa hoje? Ele continua contando os dias em que participou.`)) return;
    try { await removerMembroTime(id, pessoaId); await carregar(); } catch (e: any) { setErro(e.message); }
  }
  return (
    <div>
      <button type="button" className="btn-ghost" onClick={onVoltar} style={{ marginBottom: "0.5rem", fontSize: "0.78rem" }}><ArrowLeft size={13} /> Caixas do time</button>
      <div className="flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.6rem", marginBottom: "0.8rem" }}>
        <div>
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Caixa do time · participação nos lucros</div>
          <h2 style={{ margin: 0, fontSize: "1.05rem" }}>{t.nome}</h2>
        </div>
        <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
          <button type="button" className="btn-primary" onClick={() => setEntrada(true)}><Plus size={14} /> Entrada</button>
          {rascunho
            ? <button type="button" className="btn-ghost" onClick={() => setRateioId(rascunho.id)}>Abrir rateio em rascunho</button>
            : <button type="button" className="btn-ghost" onClick={novoRateio} disabled={ocupado || t.saldo <= 0}>Abrir rateio do PL</button>}
        </div>
      </div>
      <div className="flex" style={{ gap: "0.7rem", flexWrap: "wrap", marginBottom: "0.8rem" }}>
        <div className="card" style={{ padding: "0.6rem 0.9rem" }}><div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Saldo do caixa</div><strong style={{ fontSize: "1.15rem" }}>{formatBRL(t.saldo)}</strong></div>
        <div className="card" style={{ padding: "0.6rem 0.9rem" }}><div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Período em apuração</div><strong>{formatDate(t.periodo_inicio)} a {formatDate(t.periodo_fim)}</strong></div>
        <div className="card" style={{ padding: "0.6rem 0.9rem" }}><div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Próxima entrega</div><strong>{formatDate(t.proxima_entrega)}</strong></div>
      </div>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}

      <div className="flex items-center justify-between" style={{ marginBottom: "0.3rem" }}>
        <strong style={{ fontSize: "0.88rem" }}><Users size={14} style={{ display: "inline", marginRight: 5 }} />Membros no período</strong>
        <button type="button" className="btn-ghost" style={{ fontSize: "0.74rem" }} onClick={() => setAddMembro(true)}>Adicionar por nome</button>
      </div>
      <div style={{ overflowX: "auto", marginBottom: "1rem" }}>
        <table className="fazenda-table" style={{ minWidth: 560 }}>
          <thead><tr><th>Pessoa</th><th>Tipo</th><th>Entrou</th><th style={{ textAlign: "right" }}>Dias no período</th><th>Entrada por</th><th></th></tr></thead>
          <tbody>
            {t.membros_lista.map((m) => (
              <tr key={m.pessoa_id} style={m.dias === 0 ? { opacity: 0.55 } : undefined}>
                <td>{m.nome}</td><td style={{ color: "var(--text-muted)" }}>{rotuloTipos(m.grupos)}</td>
                <td>{m.entrada ? formatDate(m.entrada) : "—"}{m.saida ? ` · saiu ${formatDate(m.saida)}` : ""}</td>
                <td style={{ textAlign: "right" }}>{m.dias}</td>
                <td style={{ color: "var(--text-muted)" }}>{m.origem === "tipo" ? "tipo (automático)" : "nome"}</td>
                <td style={{ textAlign: "right" }}>{!m.saida && <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => remover(m.pessoa_id, m.nome)}>Dar saída</button>}</td>
              </tr>
            ))}
            {!t.membros_lista.length && <tr><td colSpan={6} style={{ color: "var(--text-muted)" }}>Sem membros. Adicione pessoas por nome ou refaça o caixa com um tipo automático.</td></tr>}
          </tbody>
        </table>
      </div>

      <strong style={{ fontSize: "0.88rem" }}>Movimentos do caixa</strong>
      <div style={{ overflowX: "auto", marginTop: "0.3rem" }}>
        <table className="fazenda-table" style={{ minWidth: 640 }}>
          <thead><tr><th>Data</th><th>Tipo</th><th>Motivo</th><th style={{ textAlign: "right" }}>Valor</th><th style={{ textAlign: "right" }}>Saldo</th><th>Lançamento</th><th></th></tr></thead>
          <tbody>
            {t.movimentos.map((m) => {
              const riscado = m.estornado ? { textDecoration: "line-through", color: "var(--text-muted)" } : {};
              return (
                <tr key={m.id}>
                  <td style={riscado}>{formatDate(m.data)}</td><td style={riscado}>{ROTULO_MOV[m.tipo] || m.tipo}</td><td style={{ ...riscado, maxWidth: 320 }}>{m.motivo}</td>
                  <td style={{ textAlign: "right", fontWeight: 700, color: m.valor >= 0 ? "var(--green-light, #3ecf8e)" : "var(--red)", ...riscado }}>{m.valor >= 0 ? "+ " : "− "}{formatBRL(Math.abs(m.valor))}</td>
                  <td style={{ textAlign: "right" }}>{formatBRL(m.saldo_depois)}</td>
                  <td style={{ color: "var(--text-muted)", fontSize: "0.74rem" }}>{m.numero_lancamento || "—"}</td>
                  <td style={{ textAlign: "right" }}>{m.pode_estornar && <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setEstornando(m.id)}><Undo2 size={12} /> Estornar</button>}</td>
                </tr>
              );
            })}
            {!t.movimentos.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)" }}>Sem movimentos. Use "Entrada" para colocar dinheiro no caixa do time.</td></tr>}
          </tbody>
        </table>
      </div>
      {t.rateios.length > 0 && (
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.7rem" }}>
          Rateios: {t.rateios.map((r, i) => (
            <span key={r.id}>{i > 0 && " · "}<button type="button" className="btn-ghost" style={{ fontSize: "0.76rem", padding: 0, textDecoration: "underline" }} onClick={() => setRateioId(r.id)}>{formatDate(r.data_entrega)} ({r.situacao}, {formatBRL(r.total)})</button></span>
          ))}
        </p>
      )}
      {entrada && <EntradaTimeModal timeId={id} onClose={() => setEntrada(false)} onFeito={() => { setEntrada(false); carregar(); }} />}
      {addMembro && <AddMembrosModal timeId={id} onClose={() => setAddMembro(false)} onFeito={() => { setAddMembro(false); carregar(); }} />}
      {estornando != null && <EstornoTimeModal timeId={id} movId={estornando} onClose={() => setEstornando(null)} onFeito={() => { setEstornando(null); carregar(); }} />}
    </div>
  );
}

function EntradaTimeModal({ timeId, onClose, onFeito }: { timeId: number; onClose: () => void; onFeito: () => void }) {
  const [tipo, setTipo] = useState("deposito");
  const [valor, setValor] = useState("");
  const [data, setData] = useState(hojeISO());
  const [motivo, setMotivo] = useState("");
  const [base, setBase] = useState("");
  const [pct, setPct] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const calculado = tipo === "comissao" && Number(base) > 0 && Number(pct) > 0 ? Math.round(Number(base) * Number(pct)) / 100 : null;
  async function lancar() {
    setErro(null);
    if (!motivo.trim()) { setErro("Informe o motivo."); return; }
    if (!((calculado ?? Number(valor)) > 0)) { setErro("Informe um valor maior que zero."); return; }
    setSalvando(true);
    try {
      await lancarEntradaTime(timeId, {
        tipo, data, motivo: motivo.trim(), valor: calculado == null ? Number(valor) : undefined,
        base_valor: tipo === "comissao" && base ? Number(base) : undefined, percentual: tipo === "comissao" && pct ? Number(pct) : undefined,
      });
      onFeito();
    } catch (e: any) { setErro(e.message); setSalvando(false); }
  }
  return (
    <Modal title="Entrada no caixa do time" onClose={onClose} width="520px">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div><label style={lbl} htmlFor="et-tipo">Tipo de entrada</label>
          <select id="et-tipo" style={campo} value={tipo} onChange={(e) => setTipo(e.target.value)}>{TIPOS.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</select></div>
        <div><label style={lbl} htmlFor="et-data">Data</label><input id="et-data" type="date" style={campo} value={data} onChange={(e) => setData(e.target.value)} /></div>
        {tipo === "comissao" ? (<>
          <div><label style={lbl}>Base (R$)</label><input type="number" min="0" step="0.01" style={campo} value={base} onChange={(e) => setBase(e.target.value)} /></div>
          <div><label style={lbl}>Percentual (%)</label><input type="number" min="0" step="0.01" style={campo} value={pct} onChange={(e) => setPct(e.target.value)} /></div>
        </>) : <div style={{ gridColumn: "1 / -1" }}><label style={lbl}>Valor (R$) para o caixa do time</label><CampoMoeda style={campo} value={Number(valor) || 0} onChange={(v) => setValor(v ? String(v) : "")} /></div>}
        <div style={{ gridColumn: "1 / -1" }}><label style={lbl} htmlFor="et-motivo">Motivo (obrigatório)</label><input id="et-motivo" style={campo} value={motivo} onChange={(e) => setMotivo(e.target.value)} /></div>
      </div>
      <p style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>Vira despesa de pessoal já baixada no Financeiro, com número de lançamento. O valor pertence ao time e só chega às pessoas no rateio.</p>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
      <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: "0.8rem" }}>
        <button type="button" className="btn-ghost" onClick={onClose} disabled={salvando}>Cancelar</button>
        <button type="button" className="btn-primary" onClick={lancar} disabled={salvando}>{salvando ? "Lançando…" : "Lançar entrada"}</button>
      </div>
    </Modal>
  );
}

function AddMembrosModal({ timeId, onClose, onFeito }: { timeId: number; onClose: () => void; onFeito: () => void }) {
  const [pessoas, setPessoas] = useState<CaixaPessoaLinha[]>([]);
  const [escolhidos, setEscolhidos] = useState<Set<number>>(new Set());
  const [entrada, setEntrada] = useState(hojeISO());
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => { fetchCaixasFuncionarios().then((d) => setPessoas(d.pessoas)).catch((e) => setErro(e.message)); }, []);
  async function salvar() {
    if (!escolhidos.size) { setErro("Escolha ao menos uma pessoa."); return; }
    try { await adicionarMembrosTime(timeId, Array.from(escolhidos), entrada); onFeito(); } catch (e: any) { setErro(e.message); }
  }
  return (
    <Modal title="Adicionar membros por nome" onClose={onClose} width="460px">
      <label style={lbl} htmlFor="am-ent">Entra no caixa em</label>
      <input id="am-ent" type="date" style={{ ...campo, marginBottom: "0.6rem" }} value={entrada} onChange={(e) => setEntrada(e.target.value)} />
      <div style={{ maxHeight: 240, overflowY: "auto", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.5rem" }}>
        {pessoas.map((p) => (
          <label key={p.pessoa_id} style={{ display: "flex", gap: "0.5rem", alignItems: "center", fontSize: "0.82rem", margin: "0.15rem 0", color: "var(--text)" }}>
            <input type="checkbox" checked={escolhidos.has(p.pessoa_id)} onChange={() => setEscolhidos((s) => { const n = new Set(s); n.has(p.pessoa_id) ? n.delete(p.pessoa_id) : n.add(p.pessoa_id); return n; })} />
            {p.nome} <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{rotuloTipos(p.grupos)}</span>
          </label>
        ))}
      </div>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
      <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: "0.8rem" }}>
        <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
        <button type="button" className="btn-primary" onClick={salvar}>Adicionar</button>
      </div>
    </Modal>
  );
}

function EstornoTimeModal({ timeId, movId, onClose, onFeito }: { timeId: number; movId: number; onClose: () => void; onFeito: () => void }) {
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  async function ok() {
    if (!motivo.trim()) { setErro("Informe o motivo do estorno."); return; }
    try { await estornarMovimentoTime(timeId, movId, motivo.trim()); onFeito(); } catch (e: any) { setErro(e.message); }
  }
  return (
    <Modal title="Estornar entrada do caixa do time" onClose={onClose} width="460px">
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginTop: 0 }}>Cria o movimento contrário com a data de hoje; o Financeiro recebe o lançamento contrário. Só é possível enquanto o valor não foi repartido.</p>
      <label style={lbl} htmlFor="est-m">Motivo (obrigatório)</label>
      <input id="est-m" style={campo} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
      <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: "0.8rem" }}>
        <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
        <button type="button" className="btn-primary" style={{ background: "var(--red)" }} onClick={ok}>Confirmar estorno</button>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Rateio: partes por dias, penalidade documentada e destino por pessoa.
// ---------------------------------------------------------------------------
function RateioTela({ rateioId, onVoltar }: { rateioId: number; onVoltar: () => void }) {
  const [r, setR] = useState<CaixaRateio | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  useEffect(() => { fetchRateioTime(rateioId).then(setR).catch((e) => setErro(e.message)); }, [rateioId]);

  async function agir(fn: () => Promise<CaixaRateio | unknown>, msg?: string, sair = false) {
    setOcupado(true); setErro(null);
    try { const res = await fn(); if (sair) { onVoltar(); return; } if (res) setR(res as CaixaRateio); if (msg) setAviso(msg); }
    catch (e: any) { setErro(e.message); }
    setOcupado(false);
  }
  if (!r) return <div>{erro ? <p role="alert" style={{ color: "var(--red)" }}>{erro}</p> : <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}<button type="button" className="btn-ghost" onClick={onVoltar}>Voltar</button></div>;
  const editavel = r.situacao === "rascunho";
  const somaFinal = r.linhas.reduce((s, l) => s + l.parte_final, 0);
  return (
    <div>
      <button type="button" className="btn-ghost" onClick={onVoltar} style={{ marginBottom: "0.5rem", fontSize: "0.78rem" }}><ArrowLeft size={13} /> {r.time_nome}</button>
      <div style={{ marginBottom: "0.7rem" }}>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Caixa do time · {r.time_nome}</div>
        <h2 style={{ margin: 0, fontSize: "1.05rem" }}>Rateio do PL · {formatDate(r.data_entrega)} · período {formatDate(r.periodo_inicio)} a {formatDate(r.periodo_fim)}</h2>
        <p style={{ margin: "0.2rem 0 0", fontSize: "0.8rem" }}>
          <b style={{ color: r.situacao === "confirmado" ? "var(--green-light, #3ecf8e)" : r.situacao === "desfeito" ? "var(--text-muted)" : "var(--amber)" }}>
            {r.situacao === "rascunho" ? "Rascunho" : r.situacao === "confirmado" ? "Confirmado" : "Desfeito"}
          </b> · total {formatBRL(r.total)}
        </p>
      </div>
      {editavel && r.documentos_pendentes.length > 0 && (
        <p role="alert" style={{ color: "var(--amber)", fontSize: "0.82rem" }}>
          <b>{r.documentos_pendentes.length} documento{r.documentos_pendentes.length > 1 ? "s" : ""} pendente{r.documentos_pendentes.length > 1 ? "s" : ""}:</b>{" "}
          {r.documentos_pendentes.join(", ")} {r.documentos_pendentes.length > 1 ? "têm" : "tem"} penalidade. O rateio só confirma com o documento de ciência anexado.
        </p>
      )}
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      {aviso && <p style={{ color: "var(--green-light, #3ecf8e)", fontSize: "0.82rem" }}>{aviso}</p>}
      <div style={{ overflowX: "auto" }}>
        <table className="fazenda-table" style={{ minWidth: 900 }}>
          <thead><tr><th>Pessoa</th><th style={{ textAlign: "right" }}>Dias</th><th style={{ textAlign: "right" }}>Parte calculada</th><th>Penalidade</th><th style={{ textAlign: "right" }}>Parte final</th><th>Destino</th></tr></thead>
          <tbody>
            {r.linhas.map((l) => <LinhaRateio key={l.pessoa_id} rateioId={r.id} linha={l} editavel={editavel && !ocupado} onResultado={setR} onErro={setErro} />)}
            <tr><td colSpan={2}><b>Total</b></td><td style={{ textAlign: "right" }}>{formatBRL(r.linhas.reduce((s, l) => s + l.parte_calculada, 0))}</td>
              <td style={{ color: "var(--text-muted)", fontSize: "0.76rem" }}>{r.retirado_por_penalidade > 0 ? `Retirado por penalidade: ${formatBRL(r.retirado_por_penalidade)}, dividido entre os demais` : ""}</td>
              <td style={{ textAlign: "right", fontWeight: 700 }}>{formatBRL(somaFinal)}</td><td></td></tr>
          </tbody>
        </table>
      </div>
      <div className="flex gap-2" style={{ marginTop: "0.9rem", flexWrap: "wrap" }}>
        {editavel && <>
          <button type="button" className="btn-primary" disabled={ocupado || !r.pode_confirmar}
            title={r.pode_confirmar ? "" : "Anexe os documentos de ciência pendentes"}
            onClick={() => window.confirm("Confirmar o rateio? Cada parte vira crédito no caixa individual (ou pagamento direto).") && agir(() => confirmarRateioTime(r.id), "Rateio confirmado: os créditos foram lançados nos caixas individuais.")}>Confirmar rateio</button>
          <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} disabled={ocupado}
            onClick={() => window.confirm("Excluir este rascunho?") && agir(() => excluirRascunhoRateio(r.id), undefined, true)}>Excluir rascunho</button>
        </>}
        {r.situacao === "confirmado" && (
          <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} disabled={ocupado}
            onClick={() => window.confirm("Desfazer o rateio? Só é possível se nenhuma parte foi sacada.") && agir(() => desfazerRateioTime(r.id), "Rateio desfeito: o valor voltou ao caixa do time.")}>Desfazer rateio</button>
        )}
      </div>
    </div>
  );
}

function LinhaRateio({ rateioId, linha, editavel, onResultado, onErro }: {
  rateioId: number; linha: CaixaRateioLinhaItem; editavel: boolean; onResultado: (r: CaixaRateio) => void; onErro: (e: string | null) => void;
}) {
  const [pct, setPct] = useState(String(linha.penalidade_pct || ""));
  const [motivo, setMotivo] = useState(linha.penalidade_motivo || "");
  useEffect(() => { setPct(String(linha.penalidade_pct || "")); setMotivo(linha.penalidade_motivo || ""); }, [linha.penalidade_pct, linha.penalidade_motivo]);

  async function salvar(extra: Partial<{ penalidade_pct: number; penalidade_motivo: string; documento_anexo_id: number | null; destino: string; forma_pagamento: string | null }> = {}) {
    onErro(null);
    const penal = extra.penalidade_pct ?? (Number(pct) || 0);
    try {
      onResultado(await ajustarLinhaRateio(rateioId, linha.pessoa_id, {
        penalidade_pct: penal, penalidade_motivo: penal > 0 ? (extra.penalidade_motivo ?? motivo) : null,
        documento_anexo_id: penal > 0 ? (extra.documento_anexo_id !== undefined ? extra.documento_anexo_id : linha.documento_anexo_id) : null,
        destino: extra.destino ?? linha.destino, forma_pagamento: (extra.destino ?? linha.destino) === "direto" ? (extra.forma_pagamento ?? linha.forma_pagamento ?? "pix") : null,
      }));
    } catch (e: any) { onErro(e.message); }
  }
  async function anexar(file: File) {
    try { const a = await anexarArquivoPessoa(linha.pessoa_id, file, CATEGORIA_PENALIDADE); await salvar({ documento_anexo_id: a.id }); }
    catch (e: any) { onErro(e.message); }
  }
  const penal = linha.penalidade_pct > 0;
  return (
    <tr>
      <td>{linha.nome}<div style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{rotuloTipos(linha.grupos)}</div></td>
      <td style={{ textAlign: "right" }}>{linha.dias}</td>
      <td style={{ textAlign: "right" }}>{formatBRL(linha.parte_calculada)}</td>
      <td style={{ minWidth: 260 }}>
        {editavel ? (
          <div>
            <div className="flex" style={{ gap: "0.3rem", alignItems: "center" }}>
              <input type="number" min="0" max="100" step="1" aria-label={`Penalidade de ${linha.nome} (%)`} style={{ ...campo, width: 70 }} value={pct}
                onChange={(e) => setPct(e.target.value)} onBlur={() => (Number(pct) || 0) !== linha.penalidade_pct && (Number(pct) > 0 ? motivo.trim() ? salvar() : undefined : salvar())} /> <span style={{ fontSize: "0.78rem" }}>%</span>
              {Number(pct) > 0 && <input style={campo} placeholder="Motivo (ex.: art. 482 CLT)" value={motivo} onChange={(e) => setMotivo(e.target.value)} onBlur={() => motivo.trim() && salvar()} />}
            </div>
            {Number(pct) > 0 && (linha.documento_anexo_id
              ? <span style={{ fontSize: "0.74rem", color: "var(--green-light, #3ecf8e)" }}>Documento de ciência anexado</span>
              : <div style={{ marginTop: "0.3rem" }}><Dropzone accept="application/pdf,image/jpeg,image/png" label="Anexar documento de ciência" hint="PDF, JPG ou PNG" onFiles={(f) => f[0] && anexar(f[0])} /></div>)}
          </div>
        ) : penal ? <span style={{ fontSize: "0.78rem" }}>{linha.penalidade_pct}% · {linha.penalidade_motivo}</span> : <span style={{ color: "var(--text-muted)" }}>—</span>}
      </td>
      <td style={{ textAlign: "right", fontWeight: 700 }}>{formatBRL(linha.parte_final)}</td>
      <td>
        {editavel ? (
          <div className="flex" style={{ gap: "0.3rem", flexWrap: "wrap" }}>
            <select aria-label={`Destino de ${linha.nome}`} style={{ ...campo, width: "auto" }} value={linha.destino} onChange={(e) => salvar({ destino: e.target.value })}>
              <option value="individual">Crédito no caixa</option><option value="direto">Pagar direto</option>
            </select>
            {linha.destino === "direto" && (
              <select aria-label="Forma de pagamento" style={{ ...campo, width: "auto" }} value={linha.forma_pagamento || "pix"} onChange={(e) => salvar({ destino: "direto", forma_pagamento: e.target.value })}>
                {FORMAS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
              </select>
            )}
          </div>
        ) : <span style={{ fontSize: "0.78rem" }}>{linha.destino === "direto" ? "Pagamento direto" : "Crédito no caixa"}</span>}
      </td>
    </tr>
  );
}
