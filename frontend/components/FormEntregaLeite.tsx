"use client";
// Lançamentos › Produção › Venda mensal do leite — tela gerencial (kit components/gerencial/kit.tsx).
// Também roda no app de campo: `salvarEntrega` é a prop de injeção offline (retorno `{ enviado: false }` = "guardado, sem internet",
// e nesse caso a lista NÃO é recarregada — offline apagaria a lista já carregada).
// Regras puras (conversão kg/L, validação, payload, balanço) em lib/vendaLeite.ts, com testes.
//  · POST /producao/entrega-leite é UPSERT por mês: salvar um mês que já existe SUBSTITUI o valor — a tela avisa e o botão diz "Substituir".
//  · Editar = PUT /producao/entrega-leite/{id}. Excluir = SEMPRE confirmarExclusao("entrega_leite", id): admin exclui na hora,
//    operador SOLICITA e aguarda aprovação de um administrador.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Check, Pencil, Trash2, X } from "lucide-react";
import {
  criarEntregaLeiteMensal, fetchEntregaLeiteMensal, atualizarEntregaLeite, confirmarExclusao, ehAdmin, fetchRelatorioControleEntrega,
} from "@/lib/api";
import { Modal } from "@/components/Modal";
import { Ajuda, Aviso, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas } from "@/components/gerencial/kit";
import { CSS_RAIZ } from "@/components/gerencial/producaoCss";
import { lerNumero, nb, hojeLocal } from "@/lib/producaoGerencial";
import {
  KG_POR_L, balancoDoMes, casasDe, ehUnidade, emKg, intervaloDoMes, mesBR, montarPayloadEntrega, ordenarEntregas, textoQtd,
  type DadosEntrega, type RegistroEntrega, type UnidadeEntrega,
} from "@/lib/vendaLeite";

type SalvarEntregaLeite = (dados: DadosEntrega) => Promise<{ enviado?: boolean } | void>;
type EstadoLista = "carregando" | "ok" | "erro";
type Edicao = { competencia: string; quantidade: string; unidade: UnidadeEntrega; observacao: string };
type Balanco = { controle: number | null; receita: number | null; precoKg: number | null };

const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const brl2 = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2, maximumFractionDigits: 2 });

const CSS = `
.gm-campos { display: grid; grid-template-columns: 11rem 17rem auto minmax(0, 1fr); gap: 0.75rem 1.1rem; align-items: start; }
.gm-campos .gv-campo input[type="text"], .gm-campos .gv-campo input[type="month"] { min-height: 2.35rem; }
.gm-grupo-un { display: flex; flex-direction: column; gap: 0.25rem; }
.gm-rot { font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); }
.gm-conv { display: flex; flex-direction: column; gap: 0.15rem; padding-top: 0.15rem; }
.gm-conv b { font-size: 1.05rem; font-variant-numeric: tabular-nums; }
.gm-conv span { font-size: 0.74rem; color: var(--text-muted); }
.gm-obs { max-width: 52rem; }
.gm-btn { display: inline-flex; align-items: center; gap: 0.35rem; min-height: 2rem; padding: 0.25rem 0.7rem; font-size: 0.78rem; font-weight: 600; border-radius: var(--r-sm); cursor: pointer; font-family: inherit; }
.gm-perigo { background: transparent; color: var(--ft-verm); border: 1px solid var(--ft-verm); }
.gm-perigo:hover:not(:disabled) { background: color-mix(in srgb, var(--ft-verm) 9%, transparent); }
.gm-perigo-cheio { background: var(--ft-verm); color: var(--surface); border: 1px solid var(--ft-verm); }
.gm-perigo-cheio:hover:not(:disabled) { background: color-mix(in srgb, var(--ft-verm) 85%, black); }
.gm-acoes { display: inline-flex; gap: 0.4rem; justify-content: flex-end; flex-wrap: wrap; }
.gm-tabela td.gm-obs-cel { white-space: normal; color: var(--text-muted); font-size: 0.78rem; }
.gm-tabela td .gv-celula-input, .gm-tabela td select, .gm-tabela td input[type="month"], .gm-tabela td input.gm-livre { min-height: 2rem; }
.gm-tabela td select, .gm-tabela td input[type="month"], .gm-tabela td input.gm-livre { background: var(--surface-2); color: var(--text); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); padding: 0.28rem 0.45rem; font-size: 0.82rem; }
.gm-tabela td input.gm-livre { width: 100%; }
.gm-qtd { display: inline-flex; gap: 0.4rem; align-items: center; }
.gm-esqueleto { display: block; height: 0.9rem; }
.gm-modal-corpo { display: flex; flex-direction: column; gap: 1rem; }
.gm-modal-corpo p { margin: 0; font-size: 0.88rem; line-height: 1.5; }
.gm-modal-rodape { display: flex; justify-content: flex-end; gap: 0.5rem; flex-wrap: wrap; }
@media (max-width: 899px) { .gm-campos { grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); } }
`;

function Esqueleto({ linhas = 4 }: { linhas?: number }) {
  return (
    <>
      {Array.from({ length: linhas }, (_, k) => (
        <tr key={k} aria-hidden="true">
          <td><span className="skeleton gm-esqueleto" style={{ width: "4.5rem" }} /></td>
          <td className="gv-dir"><span className="skeleton gm-esqueleto" style={{ width: "6rem", marginLeft: "auto" }} /></td>
          <td className="gv-dir"><span className="skeleton gm-esqueleto" style={{ width: "5rem", marginLeft: "auto" }} /></td>
          <td><span className="skeleton gm-esqueleto" style={{ width: "60%" }} /></td>
          <td><span className="skeleton gm-esqueleto" style={{ width: "4rem" }} /></td>
          <td><span className="skeleton gm-esqueleto" style={{ width: "9rem", marginLeft: "auto" }} /></td>
        </tr>
      ))}
    </>
  );
}

function ConfirmaExclusao({ r, admin, ocupado, aoCancelar, aoConfirmar }: {
  r: RegistroEntrega; admin: boolean; ocupado: boolean; aoCancelar: () => void; aoConfirmar: () => void;
}) {
  const alvo = `${mesBR(r.competencia)} (${textoQtd(r.quantidade_litros, ehUnidade(r.unidade))})`;
  return (
    <Modal title={admin ? "Excluir entrega" : "Solicitar exclusão da entrega"} onClose={aoCancelar} width="31rem">
      <div className="gm-modal-corpo">
        <p>
          {admin
            ? <>Excluir a entrega de <strong>{alvo}</strong>? Isso não pode ser desfeito.</>
            : <>Solicitar a exclusão da entrega de <strong>{alvo}</strong>? Um administrador precisa aprovar antes de ela ser excluída de fato.</>}
        </p>
        <div className="gm-modal-rodape">
          <button type="button" className="btn-ghost" onClick={aoCancelar} autoFocus>Cancelar</button>
          <button type="button" className="gm-btn gm-perigo-cheio" disabled={ocupado} onClick={aoConfirmar}>
            <Trash2 size={14} aria-hidden="true" /> {ocupado ? "Enviando…" : admin ? "Excluir entrega" : "Solicitar exclusão"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function LinhaEdicao({ r, ev, ocupado, onMudar, onSalvar, onCancelar }: {
  r: RegistroEntrega; ev: Edicao; ocupado: boolean; onMudar: (p: Partial<Edicao>) => void; onSalvar: () => void; onCancelar: () => void;
}) {
  const evQ = lerNumero(ev.quantidade);
  const valida = evQ !== null && !Number.isNaN(evQ) && evQ > 0;
  return (
    <tr className="gv-linha-marcada">
      <td><input type="month" aria-label="Mês" value={ev.competencia} onChange={(e) => onMudar({ competencia: e.target.value })} /></td>
      <td className="gv-dir">
        <span className="gm-qtd">
          <input className="gv-celula-input" type="text" inputMode="decimal" aria-label="Quantidade" value={ev.quantidade} onChange={(e) => onMudar({ quantidade: e.target.value })} />
          <select aria-label="Unidade" value={ev.unidade} onChange={(e) => onMudar({ unidade: e.target.value as UnidadeEntrega })}>
            <option value="kg">kg</option><option value="L">L</option>
          </select>
        </span>
      </td>
      <td className="gv-dir gv-num gp-muda">{valida ? `${nb(emKg(evQ as number, ev.unidade), 1)} kg` : "—"}</td>
      <td><input className="gm-livre" type="text" aria-label="Observação" value={ev.observacao} placeholder="Opcional" onChange={(e) => onMudar({ observacao: e.target.value })} /></td>
      <td className="gp-muda">{r.usuario_nome || "—"}</td>
      <td>
        <span className="gm-acoes">
          <button type="button" className="btn-primary-gold gm-btn" disabled={ocupado} onClick={onSalvar}><Check size={14} aria-hidden="true" /> {ocupado ? "…" : "Salvar"}</button>
          <button type="button" className="btn-ghost gm-btn" disabled={ocupado} onClick={onCancelar}><X size={14} aria-hidden="true" /> Cancelar</button>
        </span>
      </td>
    </tr>
  );
}

export function FormEntregaLeite({ salvarEntrega = criarEntregaLeiteMensal }: { salvarEntrega?: SalvarEntregaLeite } = {}) {
  const admin = ehAdmin();
  const [mes, setMes] = useState(() => hojeLocal().slice(0, 7));
  const [qtd, setQtd] = useState("");
  const [un, setUn] = useState<UnidadeEntrega>("kg");
  const [obs, setObs] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [retorno, setRetorno] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);

  const [lista, setLista] = useState<RegistroEntrega[]>([]);
  const [estado, setEstado] = useState<EstadoLista>("carregando");
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);
  const [erroLista, setErroLista] = useState<string | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [ev, setEv] = useState<Edicao>({ competencia: "", quantidade: "", unidade: "kg", observacao: "" });
  const [confirmar, setConfirmar] = useState<number | null>(null);

  const [balanco, setBalanco] = useState<Balanco | null>(null);
  const pedidoBalanco = useRef(0);

  const carregarRegistros = useCallback(() => {
    setEstado((e) => (e === "ok" ? e : "carregando"));
    fetchEntregaLeiteMensal()
      .then((d) => { setLista(ordenarEntregas<RegistroEntrega>(d.registros ?? [])); setEstado("ok"); })
      .catch(() => setEstado("erro"));
  }, []);
  useEffect(carregarRegistros, [carregarRegistros]);

  // Controle leiteiro e receita do mês escolhido (relatório Controle × Entregue do período = mês inteiro). Falhou/sem dado: "—", nunca 0.
  useEffect(() => {
    const periodo = intervaloDoMes(mes);
    const n = ++pedidoBalanco.current;
    if (!periodo) { setBalanco(null); return; }
    fetchRelatorioControleEntrega(periodo.inicio, periodo.fim)
      .then((d) => {
        if (n !== pedidoBalanco.current) return;
        setBalanco({ controle: d.controle_projetado_kg ?? null, receita: d.receita_projetada ?? null, precoKg: d.preco_medio_kg ?? null });
      })
      .catch(() => { if (n === pedidoBalanco.current) setBalanco(null); });
  }, [mes, lista]);

  const q = lerNumero(qtd);
  const qtdValida = q !== null && !Number.isNaN(q) && q > 0;
  const qtdInvalida = q !== null && (Number.isNaN(q) || q <= 0);
  const jaExiste = lista.find((r) => r.competencia === mes);
  const faltaMes = !mes;
  const semSalvar = salvando || faltaMes || !qtdValida;

  // Faixa de números do mês escolhido: o que se digita (ou o já lançado) × o controle leiteiro × a receita.
  const entregueKg = qtdValida ? emKg(q as number, un) : jaExiste ? emKg(jaExiste.quantidade_litros, ehUnidade(jaExiste.unidade)) : null;
  const controle = balanco?.controle ?? null;
  const receita = balanco?.receita ?? null;
  const bal = balancoDoMes(entregueKg, controle);
  const faixa = [
    { rotulo: `Entregue em ${mes ? mesBR(mes) : "—"} · kg`, valor: entregueKg !== null ? nb(entregueKg, entregueKg % 1 ? 1 : 0) : "—" },
    { rotulo: "Produzido no controle leiteiro · kg", valor: controle !== null ? nb(controle) : "—" },
    {
      rotulo: bal && bal.dif < 0 ? "Entregue acima do controle — confira" : "Diferença (não entregue)",
      valor: bal ? `${nb(Math.abs(bal.dif), Math.abs(bal.dif) % 1 ? 1 : 0)} kg · ${nb(Math.abs(bal.pct), 1)}%` : "—",
      tom: bal && bal.dif < 0 ? ("alerta" as const) : undefined,
    },
    { rotulo: `Receita recebida${receita !== null && balanco?.precoKg ? ` · ${brl2(balanco.precoKg)}/kg` : ""}`, valor: receita !== null ? brl(receita) : "—" },
  ];

  const resumo = faltaMes ? "Falta escolher o mês" : qtdValida
    ? `Entrega de ${mesBR(mes)} · ${textoQtd(q as number, un)}${un === "L" ? ` (≈ ${nb(emKg(q as number, un), 1)} kg)` : ""}`
    : `Entrega de ${mesBR(mes)} · sem quantidade`;
  const detalhe = faltaMes ? "O mês é obrigatório."
    : qtdInvalida ? "A quantidade precisa ser um número maior que zero."
    : !qtdValida ? "Falta a quantidade entregue (maior que zero)."
    : jaExiste ? `Já existe entrega em ${mesBR(mes)} (${textoQtd(jaExiste.quantidade_litros, ehUnidade(jaExiste.unidade))}) — salvar SUBSTITUI esse valor.`
    : "Entra no balanço Controle × Entregue (Histórico › Produção).";

  async function salvar() {
    setRetorno(null); setAvisoExclusao(null);
    const p = montarPayloadEntrega({ competencia: mes, quantidade: qtd, unidade: un, observacao: obs });
    if ("erro" in p) { setRetorno({ tipo: "erro", texto: p.erro }); return; }
    setSalvando(true);
    try {
      const r = await salvarEntrega(p.dados);
      setQtd(""); setObs("");
      if (r?.enviado === false) {
        setRetorno({ tipo: "ok", texto: "Sem internet — guardado, será enviado quando conectar." });
      } else {
        setRetorno({ tipo: "ok", texto: `Entrega de ${mesBR(p.dados.competencia)} ${jaExiste ? "substituída" : "lançada"} — ${textoQtd(p.dados.quantidade_litros, p.dados.unidade)} · já está na tabela abaixo.` });
        carregarRegistros(); // só recarrega quando enviou de fato — offline apagaria a lista já carregada
      }
    } catch (e: any) {
      setRetorno({ tipo: "erro", texto: e.message || "Erro ao lançar entrega mensal do leite" });
    } finally {
      setSalvando(false);
    }
  }

  const iniciarEdicao = (r: RegistroEntrega) => {
    setEditId(r.id); setErroLista(null);
    setEv({ competencia: r.competencia, quantidade: String(r.quantidade_litros), unidade: ehUnidade(r.unidade), observacao: r.observacao || "" });
  };

  async function salvarEdicao(r: RegistroEntrega) {
    const p = montarPayloadEntrega({ competencia: ev.competencia, quantidade: ev.quantidade, unidade: ev.unidade, observacao: ev.observacao });
    if ("erro" in p) { setErroLista("Informe o mês e uma quantidade maior que zero."); return; }
    setOcupado(r.id); setErroLista(null);
    try {
      await atualizarEntregaLeite(r.id, { competencia: p.dados.competencia, quantidade_litros: p.dados.quantidade_litros, unidade: p.dados.unidade, observacao: p.dados.observacao ?? null });
      setEditId(null);
      carregarRegistros();
    } catch (e: any) { setErroLista(e.message || "Erro ao editar entrega de leite"); }
    finally { setOcupado(null); }
  }

  // Passa pelo fluxo central e auditado de exclusão (POST /exclusoes/confirmar) — admin exclui na hora,
  // operador solicita e aguarda aprovação.
  async function excluir(r: RegistroEntrega) {
    setOcupado(r.id); setErroLista(null); setAvisoExclusao(null);
    try {
      const resultado = await confirmarExclusao("entrega_leite", String(r.id));
      if (resultado.status === "excluido") {
        setAvisoExclusao(`Entrega de ${mesBR(r.competencia)} excluída.`);
        carregarRegistros();
      } else {
        setAvisoExclusao("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
      }
    } catch (e: any) { setErroLista(e.message || "Erro ao excluir"); }
    finally { setOcupado(null); setConfirmar(null); }
  }

  const alvoConfirmar = lista.find((x) => x.id === confirmar);
  const vazio = estado === "ok" && lista.length === 0;
  const qtdIdLinha = "vl-qtd";

  return (
    <div className="gp-raiz">
      <style>{CSS_RAIZ + CSS}</style>
      <Faixa itens={faixa} />

      <Passo n={1} id="vl-p1" titulo="Entrega do mês">
        <div className="gm-campos">
          <Campo rotulo="Mês (obrigatório)" id="vl-mes"><input type="month" value={mes} onChange={(e) => setMes(e.target.value)} /></Campo>
          <Campo rotulo="Quantidade (maior que zero)" id={qtdIdLinha}>
            <input type="text" inputMode="decimal" autoComplete="off" value={qtd} placeholder="ex.: 12480" aria-invalid={qtdInvalida}
              onChange={(e) => setQtd(e.target.value)} />
          </Campo>
          <div className="gm-grupo-un">
            <span className="gm-rot">Unidade</span>
            <Pilulas<UnidadeEntrega> rotulo="Unidade da entrega" valor={un} onChange={setUn}
              opcoes={[{ id: "kg", nome: "Quilo (kg)", titulo: "Como o laticínio mede a entrega no contrato" }, { id: "L", nome: "Litro (L)", titulo: "Como o laticínio mede a entrega no contrato" }]} />
          </div>
          <div className="gm-conv" aria-live="polite">
            <span className="gm-rot">Na conta do balanço</span>
            {qtdValida
              ? <><b>{nb(emKg(q as number, un), un === "L" ? 1 : casasDe(q as number))} kg</b><span>{un === "L" ? `${textoQtd(q as number, un)} × ${nb(KG_POR_L, 3)} kg/L` : "já está em quilos"}</span></>
              : <><b className="gp-muda">—</b><span>{qtdInvalida ? "Use só números (12480 ou 12480,5), sem ponto de milhar." : "Digite a quantidade do mês."}</span></>}
          </div>
        </div>
        <div className="gm-obs gv-campo">
          <label htmlFor="vl-obs">Observação (opcional)</label>
          <input id="vl-obs" type="text" value={obs} onChange={(e) => setObs(e.target.value)} placeholder="Ex.: soma das notinhas, total do app do laticínio" />
        </div>
        <Ajuda>
          Some as notinhas de entrega (ou o total do app do laticínio) do mês inteiro e lance <strong>uma vez por mês</strong>. O controle leiteiro é sempre em kg:
          lançando em litro, o sistema converte ({nb(KG_POR_L, 3)} kg por litro) antes de comparar. O relatório de Produção usa este número contra o controle projetado e a receita recebida.
        </Ajuda>
        {qtdInvalida && <Aviso tom="erro">Quantidade inválida: informe um número maior que zero.</Aviso>}
        {jaExiste && qtdValida && (
          <Aviso>Já existe entrega lançada em {mesBR(mes)} ({textoQtd(jaExiste.quantidade_litros, ehUnidade(jaExiste.unidade))}). Salvar aqui <strong>substitui</strong> esse valor; para corrigir só um detalhe, use Editar na tabela abaixo.</Aviso>
        )}
      </Passo>

      <Passo n={2} id="vl-p2" titulo="Entregas lançadas" direita={
        <span className="gp-contagem" aria-live="polite">
          {estado === "carregando" ? "Carregando…" : estado === "ok" ? `${lista.length} ${lista.length === 1 ? "mês lançado" : "meses lançados"}` : ""}
        </span>
      }>
        {avisoExclusao && <Aviso>{avisoExclusao}</Aviso>}
        {erroLista && <Aviso tom="erro">{erroLista}</Aviso>}
        {estado === "erro" ? (
          <div className="gp-vazio" role="alert">
            <b>Não foi possível carregar as entregas</b>
            <span>Confira a conexão e tente de novo — as entregas já lançadas continuam guardadas.</span>
            <button type="button" className="btn-ghost" onClick={carregarRegistros}>Tentar de novo</button>
          </div>
        ) : vazio ? (
          <div className="gp-vazio"><b>Nenhuma entrega lançada ainda</b><span>Lance a primeira no passo 1: uma entrega por mês.</span></div>
        ) : (
          <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "22rem" }} aria-busy={estado === "carregando"}>
            <table className="gv-tabela gm-tabela">
              <thead>
                <tr>
                  <th scope="col" style={{ width: "9.5rem" }}>Mês</th>
                  <th scope="col" className="gv-dir" title="Valor lançado, na unidade do contrato (kg ou L)">Quantidade</th>
                  <th scope="col" className="gv-dir" title="Normalizado em quilos para o balanço (1 L = 1,029 kg)">≈ kg</th>
                  <th scope="col">Observação</th>
                  <th scope="col">Lançado por</th>
                  <th scope="col" className="gv-dir">Ações</th>
                </tr>
              </thead>
              <tbody>
                {estado === "carregando" ? <Esqueleto /> : lista.map((r) => {
                  const u = ehUnidade(r.unidade);
                  if (editId === r.id) {
                    return (
                      <LinhaEdicao key={r.id} r={r} ev={ev} ocupado={ocupado === r.id}
                        onMudar={(p) => setEv((s) => ({ ...s, ...p }))} onSalvar={() => salvarEdicao(r)} onCancelar={() => { setEditId(null); setErroLista(null); }} />
                    );
                  }
                  const kgReg = emKg(r.quantidade_litros, u);
                  return (
                    <tr key={r.id}>
                      <td className="gv-forte gv-num">{mesBR(r.competencia)}</td>
                      <td className="gv-dir gv-num gv-forte">{textoQtd(r.quantidade_litros, u)}</td>
                      <td className={`gv-dir gv-num${u === "kg" ? " gp-muda" : ""}`}>{nb(kgReg, kgReg % 1 ? 1 : 0)} kg</td>
                      <td className="gm-obs-cel">{r.observacao || "—"}</td>
                      <td className="gp-muda">{r.usuario_nome || "—"}</td>
                      <td>
                        <span className="gm-acoes">
                          <button type="button" className="btn-ghost gm-btn" onClick={() => iniciarEdicao(r)} aria-label={`Editar a entrega de ${mesBR(r.competencia)}`}><Pencil size={14} aria-hidden="true" /> Editar</button>
                          <button type="button" className="gm-btn gm-perigo" disabled={ocupado === r.id} onClick={() => setConfirmar(r.id)}
                            aria-label={`${admin ? "Excluir" : "Solicitar exclusão da"} entrega de ${mesBR(r.competencia)}`}><Trash2 size={14} aria-hidden="true" /> {admin ? "Excluir" : "Solicitar exclusão"}</button>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {estado === "carregando" && <span className="gp-sr" role="status">Carregando as entregas lançadas…</span>}
          </div>
        )}
        <Ajuda>
          {admin ? "Excluir é imediato para administradores e fica registrado." : "Operador não exclui direto: a exclusão vira uma solicitação que um administrador aprova."} A coluna “≈ kg” é o que entra no balanço (litro × {nb(KG_POR_L, 3)}).
        </Ajuda>
      </Passo>

      <BarraAcao
        resumo={resumo}
        detalhe={detalhe}
        retorno={retorno ? (retorno.tipo === "ok" ? <span role="status" className="gp-ok">✓ {retorno.texto}</span> : <span role="alert" className="gp-erro">{retorno.texto}</span>) : undefined}
        acao={<BotaoOuro desabilitado={semSalvar} onClick={salvar}>{salvando ? "Salvando…" : jaExiste && qtdValida ? `Substituir entrega de ${mesBR(mes)}` : "Salvar entrega do mês"}</BotaoOuro>}
      />
      {alvoConfirmar && <ConfirmaExclusao r={alvoConfirmar} admin={admin} ocupado={ocupado === alvoConfirmar.id} aoCancelar={() => setConfirmar(null)} aoConfirmar={() => excluir(alvoConfirmar)} />}
    </div>
  );
}
