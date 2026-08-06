"use client";
// Sub-tela: Protocolos — os 4 tipos juntos, em andamento e concluídos, com
// filtro por tipo. É o espelho no app da Central de Protocolos do site,
// consumindo os MESMOS endpoints (/central-protocolos/*).
//
// Lançar continua sendo em Lançar > Protocolos. O que existe aqui é a BAIXA
// de um protocolo já lançado — a exceção deliberada à regra "o Menu é só
// consulta", porque até 08/2026 a Agenda era o único lugar do sistema capaz
// de marcar uma etapa como realizada e escondia a etapa cujo dia tinha
// passado: protocolo que perdia o dia travava em "em andamento" para sempre.
// No curral é justamente onde se descobre que faltou dar baixa.
import { useState } from "react";
import { MobVoltar, MobCard, MobCampo, MobAviso } from "@/components/mobile/ui";
import {
  fetchCentralProtocolosAcompanhamento, fetchCentralProtocolosHistorico, formatDate,
  fetchDetalheProtocolo,
  type LinhaCentralProtocolos, type DetalheCentralProtocolo,
} from "@/lib/api";
import { enviarOuEnfileirar } from "@/lib/offline";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

const LABEL_TIPO: Record<string, string> = { produtivo: "Produtivo", reprodutivo: "Reprodutivo", sanitario: "Sanitário" };
const COR_TIPO: Record<string, string> = {
  produtivo: "var(--mob-azul)", reprodutivo: "var(--mob-roxo)", sanitario: "var(--mob-verde)",
};
const COR_ESTADO: Record<string, string> = {
  realizada: "var(--mob-verde)", atrasada: "var(--mob-vermelho)", pendente: "var(--mob-muted)",
};

type Aba = "andamento" | "concluidos";

function hoje() { return new Date().toISOString().slice(0, 10); }

export default function Protocolos({ onVoltar }: { onVoltar: () => void }) {
  const [aba, setAba] = useState<Aba>("andamento");
  const [tipo, setTipo] = useState<string>("");
  const [aberto, setAberto] = useState<{ origem: string; id: number } | null>(null);

  const ativos = useCarregar<LinhaCentralProtocolos[]>(
    "menu_protocolos_andamento", () => fetchCentralProtocolosAcompanhamento(),
  );
  const concluidos = useCarregar<LinhaCentralProtocolos[]>(
    "menu_protocolos_concluidos", () => fetchCentralProtocolosHistorico(),
  );

  const atual = aba === "andamento" ? ativos : concluidos;
  const linhas = (atual.dados || []).filter((l) => !tipo || l.tipo === tipo);

  if (aberto) {
    return <DetalheProtocoloApp origem={aberto.origem} origemId={aberto.id} onVoltar={() => setAberto(null)} />;
  }

  return (
    <div>
      <MobVoltar titulo="Protocolos" onVoltar={onVoltar} />
      <AvisoCopia chave={aba === "andamento" ? "menu_protocolos_andamento" : "menu_protocolos_concluidos"} mostrar={atual.doCache} />

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.7rem" }}>
        {([["andamento", "Em andamento"], ["concluidos", "Concluídos"]] as [Aba, string][]).map(([id, label]) => (
          <button key={id} type="button" className={`mob-pill${aba === id ? " ativa" : ""}`} onClick={() => setAba(id)}>
            {label}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.9rem" }}>
        {([["", "Todos"], ["reprodutivo", "Reprodutivo"], ["produtivo", "Produtivo"], ["sanitario", "Sanitário"]] as [string, string][]).map(([id, label]) => (
          <button key={id || "todos"} type="button" className={`mob-pill${tipo === id ? " ativa" : ""}`} onClick={() => setTipo(id)}>
            {label}
          </button>
        ))}
      </div>

      {atual.carregando && !atual.dados ? (
        <Carregando />
      ) : !atual.dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : linhas.length === 0 ? (
        <Vazio>
          {aba === "andamento" ? "Nenhum protocolo em andamento" : "Nenhum protocolo concluído"}
          {tipo ? ` do tipo ${LABEL_TIPO[tipo]}.` : "."}
        </Vazio>
      ) : (
        linhas.map((l) => {
          // Sanitário é lançado por animal e aqui aparece só agrupado para
          // exibição — a baixa dele segue pela Agenda.
          const abrivel = l.origem !== "sanitario";
          return (
            <MobCard key={`${l.origem}-${l.origem_id}`} style={{ marginBottom: "0.7rem" }}
                     onClick={abrivel ? () => setAberto({ origem: l.origem, id: l.origem_id }) : undefined}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.5rem", marginBottom: "0.35rem" }}>
                <span style={{ fontWeight: 800, fontSize: "0.92rem", lineHeight: 1.3 }}>{l.nome}</span>
                <span style={{
                  fontSize: "0.68rem", fontWeight: 800, flexShrink: 0, padding: "0.12rem 0.5rem", borderRadius: 999,
                  color: COR_TIPO[l.tipo] || "var(--mob-muted)",
                  border: `1px solid ${COR_TIPO[l.tipo] || "var(--mob-border)"}`,
                }}>{LABEL_TIPO[l.tipo] || l.tipo}</span>
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>
                {formatDate(l.data_inicio)} a {formatDate(l.data_fim)}
                {l.animais ? ` · ${l.animais} animal(is)` : ""}
              </div>
              <div style={{ fontSize: "0.85rem", marginTop: "0.3rem" }}>
                <span style={{ fontWeight: 800, color: "var(--mob-acao)" }}>
                  {l.etapas_realizadas}/{l.etapas_total} etapas
                </span>
                {aba === "andamento" && l.etapas_faltam > 0 && (
                  <span style={{ color: "var(--mob-muted)" }}> · faltam {l.etapas_faltam}</span>
                )}
                {l.status === "cancelado" && <span style={{ color: "var(--mob-vermelho)" }}> · cancelado</span>}
                {l.status === "encerrado" && <span style={{ color: "var(--mob-ambar)" }}> · encerrado</span>}
              </div>
              {abrivel && aba === "andamento" && (
                <div style={{ fontSize: "0.76rem", color: "var(--mob-acao)", marginTop: "0.35rem", fontWeight: 700 }}>
                  Toque para dar baixa →
                </div>
              )}
            </MobCard>
          );
        })
      )}
    </div>
  );
}

// ───────────── Detalhe: a grade animal × dia, em coluna única ─────────────
// No celular a grade do site não cabe: aqui a leitura é por DIA (é assim que
// o trabalho acontece no tronco — "hoje é o D7 deste lote"), e cada dia abre
// a lista de animais daquele passo.
function DetalheProtocoloApp({ origem, origemId, onVoltar }: {
  origem: string; origemId: number; onVoltar: () => void;
}) {
  const [det, setDet] = useState<DetalheCentralProtocolo | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "offline" | "erro"; msg: string } | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [diaBaixa, setDiaBaixa] = useState<number | null>(null);
  const [dataBaixa, setDataBaixa] = useState("");
  const [animaisFora, setAnimaisFora] = useState<string[]>([]);

  const cache = useCarregar<DetalheCentralProtocolo>(
    `menu_protocolo_${origem}_${origemId}`, () => fetchDetalheProtocolo(origem, origemId),
  );
  const d = det || cache.dados;

  function abrirBaixa(dia: number) {
    const info = d?.dias.find((x) => x.dia === dia);
    setDiaBaixa(dia);
    setDataBaixa(info && info.data_prevista < hoje() ? info.data_prevista : hoje());
    setAnimaisFora([]);
    setAviso(null);
  }

  async function confirmar() {
    if (diaBaixa == null || !d) return;
    const pendentes = d.animais
      .filter((a) => a.celulas.some((c) => c.dia === diaBaixa && !c.realizada))
      .map((a) => a.numero_matriz);
    const marcados = pendentes.filter((n) => !animaisFora.includes(n));
    if (!marcados.length) { setAviso({ tipo: "erro", msg: "Selecione ao menos um animal." }); return; }

    setSalvando(true); setErro(null);
    try {
      const r = await enviarOuEnfileirar(
        `/central-protocolos/${origem}/${origemId}/baixa`,
        {
          dia: diaBaixa,
          animais: marcados.length === pendentes.length ? null : marcados,
          data_realizacao: dataBaixa || null,
        },
        `Baixa do protocolo ${d.nome} — D${diaBaixa}`,
        "POST",
      );
      setDiaBaixa(null);
      setAviso(r.enviado
        ? { tipo: "ok", msg: "Baixa registrada." }
        : { tipo: "offline", msg: "Guardado — será enviado quando conectar." });
      if (r.enviado) {
        // Só relê do servidor quando o envio de fato aconteceu; offline, o
        // recarregamento traria de volta a grade sem a baixa.
        await fetchDetalheProtocolo(origem, origemId).then(setDet).catch(() => {});
      }
    } catch (e: any) {
      setErro(e?.message || "Não foi possível salvar.");
    } finally { setSalvando(false); }
  }

  if (cache.carregando && !d) return (<div><MobVoltar titulo="Protocolo" onVoltar={onVoltar} /><Carregando /></div>);
  if (!d) return (
    <div><MobVoltar titulo="Protocolo" onVoltar={onVoltar} />
      <Vazio>Sem dados salvos deste protocolo. Conecte-se uma vez para baixar.</Vazio></div>
  );

  const pendentesDoDia = diaBaixa == null ? [] :
    d.animais.filter((a) => a.celulas.some((c) => c.dia === diaBaixa && !c.realizada));

  return (
    <div>
      <MobVoltar titulo={d.nome} onVoltar={onVoltar} />
      <AvisoCopia chave={`menu_protocolo_${origem}_${origemId}`} mostrar={cache.doCache && !det} />

      <div style={{ fontSize: "0.85rem", marginBottom: "0.8rem" }}>
        <strong>{d.etapas_realizadas}</strong> de {d.etapas_total} etapas
        {d.etapas_atrasadas > 0 && <span style={{ color: "var(--mob-vermelho)", fontWeight: 700 }}> · {d.etapas_atrasadas} atrasada(s)</span>}
        <span style={{ color: "var(--mob-muted)" }}> · {d.animais.length} animal(is)</span>
      </div>

      {d.encerrado_em && (
        <MobAviso tipo="offline">
          Encerrado em {formatDate(d.encerrado_em)}{d.encerrado_motivo ? ` — ${d.encerrado_motivo}` : ""}. Para reabrir, use o site.
        </MobAviso>
      )}
      {erro && <MobAviso tipo="erro">{erro}</MobAviso>}
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}

      {diaBaixa == null ? (
        d.dias.map((dia) => {
          const feito = dia.realizadas >= dia.total;
          const atrasado = !feito && dia.data_prevista < hoje();
          return (
            <MobCard key={dia.dia} style={{ marginBottom: "0.6rem" }}
                     onClick={feito || d.encerrado_em ? undefined : () => abrirBaixa(dia.dia)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.5rem" }}>
                <span style={{ fontWeight: 800, fontSize: "0.95rem" }}>{dia.rotulo}</span>
                <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)" }}>{formatDate(dia.data_prevista)}</span>
              </div>
              {dia.descricao && (
                <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>{dia.descricao}</div>
              )}
              <div style={{ fontSize: "0.85rem", marginTop: "0.35rem", fontWeight: 700,
                            color: COR_ESTADO[feito ? "realizada" : atrasado ? "atrasada" : "pendente"] }}>
                {feito ? `✓ ${dia.total} aplicada(s)` : `${dia.realizadas}/${dia.total} — ${atrasado ? "atrasado" : "a vencer"}`}
              </div>
              {!feito && !d.encerrado_em && (
                <div style={{ fontSize: "0.76rem", color: "var(--mob-acao)", marginTop: "0.3rem", fontWeight: 700 }}>
                  Toque para dar baixa →
                </div>
              )}
            </MobCard>
          );
        })
      ) : (
        <>
          <MobCampo label="Em que dia foi aplicado?">
            <input type="date" className="mob-input" value={dataBaixa} max={hoje()}
                   onChange={(e) => setDataBaixa(e.target.value)} />
          </MobCampo>
          <p style={{ fontSize: "0.76rem", color: "var(--mob-muted)", margin: "-0.4rem 0 0.9rem" }}>
            A data real da aplicação — é ela que vai para a ficha do animal, não a data de hoje.
          </p>

          <MobCampo label={`Animais (${pendentesDoDia.length - animaisFora.length} de ${pendentesDoDia.length})`}>
            <div>
              {pendentesDoDia.map((a) => {
                const marcado = !animaisFora.includes(a.numero_matriz);
                return (
                  <label key={a.numero_matriz}
                         style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.55rem 0.2rem",
                                  fontSize: "0.92rem", borderBottom: "1px solid var(--mob-border)" }}>
                    <input type="checkbox" checked={marcado} style={{ width: 22, height: 22 }}
                           onChange={(e) => setAnimaisFora((p) => e.target.checked
                             ? p.filter((n) => n !== a.numero_matriz) : [...p, a.numero_matriz])} />
                    {a.numero_matriz}
                  </label>
                );
              })}
            </div>
          </MobCampo>

          <button type="button" className="mob-btn" onClick={confirmar} disabled={salvando}>
            {salvando ? "Salvando…" : "Confirmar baixa"}
          </button>
          <button type="button" className="mob-btn mob-btn-sec" style={{ marginTop: "0.6rem" }}
                  onClick={() => setDiaBaixa(null)} disabled={salvando}>
            Cancelar
          </button>
        </>
      )}
    </div>
  );
}
