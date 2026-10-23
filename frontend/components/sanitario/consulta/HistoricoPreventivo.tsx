"use client";
// Sanidade › Preventiva › Histórico: por animal (registros, inclusive o que
// veio da planilha como "só registro" e os estornados, mais a situação de hoje
// em cada vacina) ou por vacina/exame, e o registro de decisões do módulo.
import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { ErroCarregamento } from "@/components/ui";
import { historico, historicoAnimal, listarCaixas, listarLog, situacaoAnimal } from "@/lib/apiSanitario";
import { ROTULO_ORIGEM, ROTULO_RESULTADO, fmtData, fmtDataHora, type Registro } from "@/lib/sanitarioTipos";
import { ChipSituacao, Faixa, Seg, useCarregar } from "../comum";
import { carregarAnimaisSan } from "../SeletorAnimais";

function ListaRegistros({ regs, mostrarAnimal }: { regs: Registro[]; mostrarAnimal?: boolean }) {
  if (!regs.length) return <p className="san-nota" style={{ margin: 0 }}>Sem registros.</p>;
  return (
    <div className="san-log">
      {regs.map((h) => (
        <div key={h.id}>
          <time>{fmtData(h.data)}</time>
          <span style={h.estado !== "valido" ? { opacity: 0.65 } : undefined}>
            {mostrarAnimal && <b className="san-num">{h.numero} · </b>}<b>{h.caixa || h.outro_texto || "—"}</b>
            {h.ciclo_chave && !h.ciclo_chave.startsWith("X:") ? ` · ciclo ${h.ciclo_chave}` : ""}{h.resultado ? ` · ${ROTULO_RESULTADO[h.resultado]}` : ""}
            {h.so_registro && <> <span className="san-tag">só registro</span></>}
            {h.estado !== "valido" && <> <span className="san-tag alerta">estornado</span></>}
            <br /><span className="san-nota">{ROTULO_ORIGEM[h.origem] || h.origem}{h.decisao_curral ? " · decisão no curral" : ""}{h.apos_fechamento ? " · lançado após o fechamento" : ""}
              {h.fora_da_regra ? " · fora da regra, com consentimento" : ""}{h.retroativo ? " · retroativo" : ""}{h.estornado_motivo ? ` · estorno: ${h.estornado_motivo}` : ""}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

function PorAnimal() {
  const [busca, setBusca] = useState("");
  const [animalId, setAnimalId] = useState<number | null>(null);
  const animais = useCarregar(() => carregarAnimaisSan(), []);
  const hist = useCarregar(() => (animalId ? historicoAnimal(animalId) : Promise.resolve(null)), [animalId]);
  const sit = useCarregar(() => (animalId ? situacaoAnimal(animalId) : Promise.resolve(null)), [animalId]);
  const achado = useMemo(() => (animais.dados || []).find((a) => a.numero === busca.trim()), [animais.dados, busca]);
  const sugestoes = useMemo(() => busca.trim() && !achado ? (animais.dados || []).filter((a) => a.numero.includes(busca.trim())).slice(0, 8) : [], [animais.dados, busca, achado]);
  const atual = (animais.dados || []).find((a) => a.id === animalId);
  return (
    <div className="san-bloco-corpo" style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
      <form className="san-linha" onSubmit={(e) => { e.preventDefault(); if (achado) setAnimalId(achado.id); }}>
        <div className="san-campo medio">
          <label htmlFor="hBusca">Brinco</label>
          <input id="hBusca" className="san-input" type="search" inputMode="numeric" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex.: 0701" />
        </div>
        <button type="submit" className="btn-primary" disabled={!achado}><Search size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />Ver histórico</button>
      </form>
      {animais.erro && <Faixa tipo="alerta">{animais.erro}</Faixa>}
      {sugestoes.length > 0 && (
        <div className="san-acoes">{sugestoes.map((a) => <button key={a.id} type="button" className="btn-ghost san-btn-sm" onClick={() => { setBusca(a.numero); setAnimalId(a.id); }}>{a.numero}</button>)}</div>
      )}
      {busca.trim() && !achado && !sugestoes.length && animais.dados && <p className="san-nota" style={{ margin: 0 }}>Brinco não encontrado entre os animais ativos.</p>}
      {atual && <p className="san-nota" style={{ margin: 0 }}>{atual.categoria || "—"} · {atual.lote || "sem lote"} · {atual.sexo === "M" ? "macho" : "fêmea"}</p>}
      {animalId && (sit.erro ? <ErroCarregamento mensagem={sit.erro} onRetry={sit.recarregar} /> : sit.dados && sit.dados.caixas.length > 0 && (
        <div>
          <span className="san-rot">Situação hoje nas vacinas ativas</span>
          <div className="san-tags" style={{ marginTop: 4 }}>
            {sit.dados.caixas.map((c, i) => <span key={`${c.caixa_id}-${i}`} title={c.texto || undefined}>{c.caixa}: <ChipSituacao estado={c.estado} texto={c.texto} /></span>)}
          </div>
        </div>
      ))}
      {animalId && (hist.erro ? <ErroCarregamento mensagem={hist.erro} onRetry={hist.recarregar} />
        : !hist.dados ? <div className="skeleton" style={{ height: "6rem" }} /> : <ListaRegistros regs={hist.dados.registros} />)}
      <p className="san-nota" style={{ margin: 0 }}>Planilha importada entra como <b>só registro</b>: aparece aqui, mas não conta para cobertura nem tira o animal da caixa.</p>
    </div>
  );
}

function PorVacina() {
  const caixas = useCarregar(() => listarCaixas("todas"), []);
  const [cx, setCx] = useState("");
  const hist = useCarregar(() => (cx ? historico({ caixa_id: Number(cx) }) : Promise.resolve(null)), [cx]);
  return (
    <div className="san-bloco-corpo" style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
      <div className="san-campo medio" style={{ maxWidth: 320 }}>
        <label htmlFor="hCx">Vacina ou exame</label>
        <select id="hCx" className="san-input" value={cx} onChange={(e) => setCx(e.target.value)}>
          <option value="">Escolha…</option>{(caixas.dados || []).map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
        </select>
      </div>
      {cx && (hist.erro ? <ErroCarregamento mensagem={hist.erro} onRetry={hist.recarregar} /> : !hist.dados ? <div className="skeleton" style={{ height: "6rem" }} /> : <ListaRegistros regs={hist.dados} mostrarAnimal />)}
    </div>
  );
}

export function HistoricoPreventivo() {
  const [modo, setModo] = useState<"animal" | "vacina">("animal");
  const log = useCarregar(() => listarLog({ limite: 300 }), []);
  return (
    <div className="san-grid2">
      <section className="san-bloco">
        <div className="san-bloco-cab"><h3>Histórico</h3>
          <Seg<"animal" | "vacina"> rotulo="Histórico por" valor={modo} onChange={setModo} opcoes={[{ id: "animal", label: "Por animal" }, { id: "vacina", label: "Por vacina" }]} /></div>
        {modo === "animal" ? <PorAnimal /> : <PorVacina />}
      </section>
      <section className="san-bloco">
        <div className="san-bloco-cab"><h3>Registro de decisões</h3><span className="san-nota san-num">{log.dados?.length ?? ""}</span></div>
        <div className="san-bloco-corpo" style={{ maxHeight: 640, overflow: "auto" }}>
          {log.erro ? <ErroCarregamento mensagem={log.erro} onRetry={log.recarregar} /> : !log.dados ? <div className="skeleton" style={{ height: "8rem" }} />
            : log.dados.length ? <div className="san-log">{log.dados.map((l) => <div key={l.id}><time>{fmtDataHora(l.em)}</time><span>{l.texto || l.tipo}</span></div>)}</div>
              : <p className="san-nota" style={{ margin: 0 }}>Nada registrado ainda.</p>}
        </div>
      </section>
    </div>
  );
}
