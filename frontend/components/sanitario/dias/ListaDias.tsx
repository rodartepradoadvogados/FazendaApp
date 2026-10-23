"use client";
// Central de Protocolos › Vacinas e exames marcados — os dias de "Vacina" e
// "Exame": marcados, em andamento e fechados; caixas que aglomeraram (só
// administradores); conflitos entre dois celulares; "Marcar Vacina ou Exame".
// Pode abrir já com animais escolhidos em Sanidade › Animais na janela
// (`paresIniciais`, vindo da querystring `marcar=`).
import { useState } from "react";
import { Bell, Plus, Printer, Smartphone } from "lucide-react";
import { ErroCarregamento, TelaSkeleton } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { decidirConflito, listarConflitos, listarDias, mensagemDoErro, painel } from "@/lib/apiSanitario";
import { ROTULO_ESTADO_DIA, diaSemana, fmtData, fmtDataHora, hojeISO, MESES_CURTOS, somarDias, textoProduto, type Dia } from "@/lib/sanitarioTipos";
import { Chip, Faixa, useCarregar, useEuSanitario } from "../comum";
import { ModalFicha } from "../FichaCampo";
import { DetalheDia } from "./DetalheDia";
import { ModalMarcarDia } from "./ModalMarcarDia";

function CartaoDia({ d, onAbrir, onFicha }: { d: Dia; onAbrir: () => void; onFicha: () => void }) {
  const [, mm, dd] = d.data.split("-");
  const aberto = d.estado === "marcado" || d.estado === "em_execucao";
  const total = d.contagens.feitos + d.contagens.pendentes;
  return (
    <div className="san-dia">
      <div className="san-dia-data" aria-hidden="true"><span>{diaSemana(d.data)}</span><b>{dd}</b><span>{MESES_CURTOS[Number(mm) - 1]}</span></div>
      <div style={{ minWidth: 0 }}>
        <h4>{d.nome}</h4>
        <div className="meta">
          {d.hora && <span><b>{d.hora}</b></span>}
          <span>Veterinário: <b>{d.veterinario?.texto || (d.veterinario?.pessoa_id ? "cadastrado" : "não informado")}</b>{d.veterinario?.crmv ? ` · ${d.veterinario.crmv}` : ""}</span>
          <span><b className="san-num">{d.contagens.animais}</b> animais</span>
          <span>{aberto ? "Feitas" : "Registradas"}: <b className="san-num">{d.contagens.feitos} de {total}</b></span>
          {d.estado === "em_execucao" ? <Chip tipo="aviso">{ROTULO_ESTADO_DIA[d.estado]}</Chip>
            : d.estado === "marcado" ? <Chip tipo="marcada">{ROTULO_ESTADO_DIA[d.estado]}</Chip>
              : d.estado === "fechado" ? <Chip tipo="ok">Fechado{d.fechamento_auto ? " (automático)" : ""}</Chip> : <Chip tipo="inativa">Cancelado</Chip>}
        </div>
        <div className="san-nota" style={{ marginTop: "0.25rem" }}>{d.caixas.map((c) => `${c.nome_curto}: ${c.tipo === "exame" ? "exame" : textoProduto(c.produto)}`).join(" · ")}</div>
        {d.decisao_riscos && <div className="san-nota">Decisão registrada: {d.decisao_riscos.texto || d.decisao_riscos.decisao}</div>}
        {d.data_prevista && d.data_prevista !== d.data && <div className="san-nota">Data prevista era {fmtData(d.data_prevista, true)}.</div>}
      </div>
      <div className="san-acoes">
        {aberto ? <button type="button" className="btn-primary san-btn-sm" onClick={onAbrir}>Executar</button>
          : <button type="button" className="btn-ghost san-btn-sm" onClick={onAbrir}>Ver</button>}
        {d.estado !== "cancelado" && (
          <button type="button" className="btn-ghost san-btn-sm" onClick={onFicha}><Printer size={12} aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: 4 }} />Ficha de campo</button>
        )}
      </div>
    </div>
  );
}

export function ListaDias({ paresIniciais, caixasIniciais, diaInicial }: {
  paresIniciais?: { caixa_id: number; animal_id: number }[]; caixasIniciais?: number[]; diaInicial?: number | null;
}) {
  const toast = useToast();
  const { admin } = useEuSanitario();
  const [aberto, setAberto] = useState<number | null>(diaInicial ?? null);
  const [marcar, setMarcar] = useState<{ caixas: number[]; pares?: { caixa_id: number; animal_id: number }[] } | null>(
    paresIniciais?.length || caixasIniciais?.length ? { caixas: caixasIniciais || [], pares: paresIniciais } : null);
  const [ficha, setFicha] = useState<number | null>(null);
  const hoje = hojeISO();
  const abertos = useCarregar(() => listarDias({ estado: "abertos" }), []);
  const fechados = useCarregar(() => listarDias({ de: somarDias(hoje, -180) }), []);
  const pn = useCarregar(() => (admin ? painel(30) : Promise.resolve(null)), [admin]);
  const conf = useCarregar(() => listarConflitos(), []);
  const [decidindo, setDecidindo] = useState(false);

  if (aberto != null) return <DetalheDia diaId={aberto} onVoltar={() => { setAberto(null); abertos.recarregar(); fechados.recarregar(); }} />;

  const listaFechados = (fechados.dados || []).filter((d) => d.estado === "fechado" || d.estado === "cancelado").reverse();
  const aglomeradas = pn.dados?.aglomeradas || [];
  return (
    <div className="san-pagina">
      <div className="san-cab">
        <div>
          <h2>Vacinas e exames marcados</h2>
          <p>Marque, edite, execute e feche os dias de Vacina e de Exame. O nome do dia é sempre “Vacina” ou “Exame”.</p>
        </div>
        <button type="button" className="btn-primary" onClick={() => setMarcar({ caixas: [] })}>
          <Plus size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />Marcar Vacina ou Exame
        </button>
      </div>

      {admin && aglomeradas.length > 0 && (
        <section className="san-bloco">
          <div className="san-bloco-cab"><h3>Caixas que aglomeraram</h3><span className="san-nota">só administradores veem</span></div>
          {aglomeradas.map((a) => (
            <div key={a.caixa_id} className="san-nota-ag">
              <span className="ico"><Bell size={15} aria-hidden="true" /></span>
              <div><p><b>{a.caixa}</b> aglomerou <b className="san-num">{a.animais}</b> animais (mínimo {a.minimo ?? "—"})</p></div>
              <div className="san-acoes"><button type="button" className="btn-primary san-btn-sm" onClick={() => setMarcar({ caixas: [a.caixa_id] })}>Marcar data</button></div>
            </div>
          ))}
        </section>
      )}

      {(conf.dados || []).length > 0 && (
        <section className="san-bloco">
          <div className="san-bloco-cab"><h3>Conflitos entre celulares</h3><span className="san-nota">o aplicador ou o administrador decide qual vale</span></div>
          {(conf.dados || []).map((c) => (
            <div key={c.id} className="san-nota-ag">
              <span className="ico"><Smartphone size={15} aria-hidden="true" /></span>
              <div><p>{c.texto}</p><small>{fmtDataHora(c.em)}</small></div>
              <div className="san-acoes">
                <button type="button" className="btn-ghost san-btn-sm" disabled={decidindo} onClick={async () => {
                  setDecidindo(true);
                  try { await decidirConflito(c.id, "existente"); toast("Mantido o que já estava gravado."); conf.recarregar(); }
                  catch (e) { toast(mensagemDoErro(e), "erro"); } finally { setDecidindo(false); }
                }}>Manter o primeiro</button>
                <button type="button" className="btn-ghost san-btn-sm" disabled={decidindo} onClick={async () => {
                  setDecidindo(true);
                  try { await decidirConflito(c.id, "novo"); toast("Vale o registro do segundo celular."); conf.recarregar(); abertos.recarregar(); }
                  catch (e) { toast(mensagemDoErro(e), "erro"); } finally { setDecidindo(false); }
                }}>Usar o segundo</button>
              </div>
            </div>
          ))}
        </section>
      )}
      {conf.erro && <Faixa tipo="atencao">Não foi possível ver os conflitos entre celulares: {conf.erro}</Faixa>}

      <section className="san-bloco">
        <div className="san-bloco-cab"><h3>Marcados</h3><span className="san-nota san-num">{abertos.dados?.length ?? ""}</span></div>
        {abertos.erro ? <div className="san-bloco-corpo"><ErroCarregamento mensagem={abertos.erro} onRetry={abertos.recarregar} /></div>
          : !abertos.dados ? <div className="san-bloco-corpo"><TelaSkeleton kpis={0} label="Carregando os dias marcados" /></div>
            : abertos.dados.length ? abertos.dados.map((d) => <CartaoDia key={d.id} d={d} onAbrir={() => setAberto(d.id)} onFicha={() => setFicha(d.id)} />)
              : <div className="san-bloco-corpo san-nota">Nenhum dia marcado. Quando uma caixa aglomerar, a Agenda avisa os administradores.</div>}
      </section>

      <section className="san-bloco">
        <div className="san-bloco-cab">
          <h3>Fechados e cancelados · últimos 180 dias</h3>
          <button type="button" className="san-link" onClick={fechados.recarregar}>Atualizar</button>
        </div>
        {fechados.erro ? <div className="san-bloco-corpo"><ErroCarregamento mensagem={fechados.erro} onRetry={fechados.recarregar} /></div>
          : !fechados.dados ? <div className="san-bloco-corpo"><TelaSkeleton kpis={0} tabela={false} label="Carregando os dias fechados" /></div>
            : listaFechados.length ? listaFechados.map((d) => <CartaoDia key={d.id} d={d} onAbrir={() => setAberto(d.id)} onFicha={() => setFicha(d.id)} />)
              : <div className="san-bloco-corpo san-nota">Nenhum dia fechado ainda.</div>}
      </section>

      {marcar && (
        <ModalMarcarDia caixasIniciais={marcar.caixas} paresIniciais={marcar.pares} onFechar={() => setMarcar(null)}
          onSalvo={(dias, msg) => { setMarcar(null); toast(msg); abertos.recarregar(); if (dias.length === 1) setAberto(null); }} />
      )}
      {ficha != null && <ModalFicha diaId={ficha} onFechar={() => setFicha(null)} />}
    </div>
  );
}
