"use client";
// ─────────────────────────────────────────────────────────────────────────────
// TELA AGENDA do app móvel (/app) — "Hoje, <data>" com as tarefas do dia
// (e as atrasadas ainda pendentes) em cartões grandes de tocar. Cada cartão
// tem um check circular que marca/desmarca "realizado" no MESMO endpoint do
// site desktop (POST/DELETE /agenda/realizados). Funciona offline: a lista vem
// do cache e o "realizado" entra na fila de envio.
// ─────────────────────────────────────────────────────────────────────────────
import { useCallback, useEffect, useState } from "react";
import { MobCard, MobTitulo, MobCheck, MobAviso, corCategoria } from "@/components/mobile/ui";
import { fetchAgenda, today } from "@/lib/api";
import { fetchComCache, cacheEm, enviarOuEnfileirar, useOnline } from "@/lib/offline";

/** Soma `n` dias a uma data ISO ("YYYY-MM-DD") e devolve outra ISO. */
function maisDias(iso: string, n: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().split("T")[0];
}

type Evento = {
  id: string;
  data: string;
  categoria: string;
  descricao: string;
  numero_animal?: string | null;
  observacao?: string | null;
  lote?: string | null;
  tipo?: string | null;
  animais?: string[] | null;
  produto?: string | null;
  dose?: number | null;
  unidade?: string | null;
  via?: string | null;
};

type Agenda = { eventos?: Evento[] };

// Categoria do backend ("Reprodutivo", "Gestão/Financeiro", "alimentacao"…)
// → chave de cor (corCategoria) + rótulo em MAIÚSCULAS do cartão.
function catInfo(categoria: string): { chave: string; rotulo: string } {
  const c = (categoria || "").toLowerCase();
  if (c === "reprodutivo") return { chave: "reprodutivo", rotulo: "REPRODUTIVO" };
  if (c === "sanidade") return { chave: "sanidade", rotulo: "SANIDADE" };
  if (c === "produção" || c === "producao") return { chave: "producao", rotulo: "PRODUÇÃO" };
  if (c === "alimentação" || c === "alimentacao") return { chave: "alimentacao", rotulo: "ALIMENTAÇÃO" };
  if (c === "gestão/financeiro" || c === "financeiro") return { chave: "financeiro", rotulo: "FINANCEIRO" };
  return { chave: "atividades", rotulo: (categoria || "ATIVIDADE").toUpperCase() };
}

// Identificação em negrito + detalhe cinza de cada cartão, a partir do evento.
function linhas(e: Evento): { principal: string; detalhe: string | null } {
  if (e.numero_animal) return { principal: `Nº ${e.numero_animal}`, detalhe: e.descricao || e.observacao || null };
  if (e.tipo === "protocolo_iatf" && e.animais?.length) {
    return { principal: e.descricao, detalhe: `${e.animais.length} animal${e.animais.length !== 1 ? "is" : ""}` };
  }
  if (e.lote) return { principal: `Lote ${e.lote}`, detalhe: e.descricao || e.observacao || null };
  return { principal: e.descricao, detalhe: e.observacao || null };
}

function resumo(e: Evento): string {
  const { principal } = linhas(e);
  return `${principal} — ${e.descricao}`.slice(0, 80);
}

function fmtData(iso: string, opts: Intl.DateTimeFormatOptions): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", opts);
}

function fmtCacheEm(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function AgendaMovel() {
  const online = useOnline();
  const hoje = today();
  const chaveCache = `agenda_mob_${hoje}`;

  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [doCache, setDoCache] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(false);
  // Ids marcados como "feito" nesta sessão (otimista) — mantém o cartão visível
  // para permitir desfazer, já que o backend some com ele no próximo reload.
  const [feitos, setFeitos] = useState<Set<string>>(new Set());
  const [aviso, setAviso] = useState<{ tipo: "ok" | "offline" | "erro"; msg: string } | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    const { dados, doCache } = await fetchComCache<Agenda>(chaveCache, () => fetchAgenda(hoje));
    setAgenda(dados);
    setDoCache(doCache);
    // fetchComCache engole o erro e cai no cache; se falhou ONLINE é erro de
    // verdade (servidor/permissão 403), não "offline".
    setErro(doCache && navigator.onLine);
    setFeitos(new Set());
    setCarregando(false);
  }, [chaveCache, hoje]);

  useEffect(() => { carregar(); }, [carregar]);

  // Só hoje e as atrasadas ainda pendentes (data <= hoje), atrasadas primeiro.
  const eventos = (agenda?.eventos || [])
    .filter((e) => e.data <= hoje)
    .sort((a, b) => (a.data < b.data ? -1 : a.data > b.data ? 1 : 0));

  const pendentes = eventos.filter((e) => !feitos.has(e.id)).length;

  async function alternar(e: Evento) {
    const jaFeito = feitos.has(e.id);
    setAviso(null);
    // Atualiza otimista na hora.
    setFeitos((p) => {
      const n = new Set(p);
      jaFeito ? n.delete(e.id) : n.add(e.id);
      return n;
    });
    // Dar baixa num evento sanitário de um animal COM medicamento padrão:
    // gera a aplicação (que dá a saída de estoque) em vez de só marcar feito.
    const darBaixaSanidade = !jaFeito && e.tipo === "evento_sanitario" && e.numero_animal && e.produto && e.dose != null && e.unidade;
    try {
      let r;
      if (darBaixaSanidade) {
        r = await enviarOuEnfileirar("/sanidade/aplicacoes", {
          data_aplicacao: hoje, animais: [e.numero_animal],
          itens: [{ produto: e.produto, quantidade: e.dose, unidade: e.unidade, via: e.via || undefined }],
        }, `Aplicação ${e.produto} — animal ${e.numero_animal}`, "POST");
      } else if (jaFeito) {
        r = await enviarOuEnfileirar(`/agenda/realizados/${encodeURIComponent(e.id)}`, {}, `Desfazer: ${resumo(e)}`, "DELETE");
      } else {
        r = await enviarOuEnfileirar("/agenda/realizados", { evento_id: e.id }, `Concluir: ${resumo(e)}`, "POST");
      }
      if (!r.enviado) setAviso({ tipo: "offline", msg: "Guardado — será enviado quando conectar." });
      else if (darBaixaSanidade) setAviso({ tipo: "ok", msg: "Aplicação lançada e estoque baixado." });
    } catch (err) {
      // Servidor recusou (ex.: 403 sem permissão) — desfaz o otimista.
      setFeitos((p) => {
        const n = new Set(p);
        jaFeito ? n.add(e.id) : n.delete(e.id);
        return n;
      });
      setAviso({ tipo: "erro", msg: err instanceof Error ? err.message : "Não foi possível salvar." });
    }
  }

  const cacheISO = cacheEm(chaveCache);

  // Próximos 2 dias (amanhã e depois de amanhã) para consulta antecipada.
  const d1 = maisDias(hoje, 1);
  const d2 = maisDias(hoje, 2);
  const eventosDe = (dia: string) => (agenda?.eventos || []).filter((e) => e.data === dia);

  function renderCartao(e: Evento) {
    const { chave, rotulo } = catInfo(e.categoria);
    const { principal, detalhe } = linhas(e);
    const feito = feitos.has(e.id);
    const atrasada = e.data < hoje;
    return (
      <MobCard key={e.id} style={{ marginBottom: "0.6rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: "0.68rem", fontWeight: 800, letterSpacing: "0.06em", color: corCategoria(chave), marginBottom: "0.2rem" }}>
              {rotulo}
            </div>
            <div style={{ fontSize: "1.15rem", fontWeight: 800, lineHeight: 1.2, color: feito ? "var(--mob-muted)" : "var(--mob-text)", textDecoration: feito ? "line-through" : "none" }}>
              {principal}
            </div>
            {detalhe && (
              <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.15rem", overflow: "hidden", textOverflow: "ellipsis" }}>
                {detalhe}
              </div>
            )}
            {atrasada && (
              <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--mob-vermelho)", marginTop: "0.25rem" }}>
                Atrasada · {fmtData(e.data, { day: "2-digit", month: "2-digit" })}
              </div>
            )}
          </div>
          <MobCheck feito={feito} onClick={() => alternar(e)} />
        </div>
      </MobCard>
    );
  }

  // Seção recolhível de um dia seguinte (amanhã / depois de amanhã).
  function DiaSeguinte({ dia, prefixo }: { dia: string; prefixo: string }) {
    const evs = eventosDe(dia);
    return (
      <details style={{ marginTop: "0.7rem" }}>
        <summary style={{ cursor: "pointer", fontWeight: 700, fontSize: "0.95rem", padding: "0.85rem 1rem", background: "var(--mob-surface)", border: "1px solid var(--mob-border)", borderRadius: 14, listStyle: "none", display: "flex", justifyContent: "space-between", alignItems: "center", boxShadow: "var(--mob-sombra)" }}>
          <span>{prefixo}, {fmtData(dia, { day: "numeric", month: "long" })}</span>
          <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)", fontWeight: 700 }}>{evs.length}</span>
        </summary>
        <div style={{ marginTop: "0.6rem" }}>
          {evs.length === 0
            ? <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem", padding: "0.3rem 0.2rem" }}>Nada agendado.</p>
            : evs.map(renderCartao)}
        </div>
      </details>
    );
  }

  return (
    <div>
      <MobTitulo badge={`${pendentes} ${pendentes === 1 ? "Tarefa" : "Tarefas"}`}>
        Hoje, {fmtData(hoje, { day: "numeric", month: "long" }).replace(/ de (.)/, (_, l) => ` de ${l.toUpperCase()}`)}
      </MobTitulo>

      {/* Modo offline: agenda veio do cache */}
      {doCache && !online && cacheISO && (
        <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", margin: "0 0 0.8rem" }}>
          Sem internet — mostrando agenda de {fmtCacheEm(cacheISO)}.
        </p>
      )}

      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}

      {carregando && !agenda ? (
        <p style={{ color: "var(--mob-muted)", padding: "1.5rem 0" }}>Carregando agenda…</p>
      ) : erro && !agenda ? (
        <MobAviso tipo="erro">Não foi possível carregar a agenda. Tente novamente mais tarde.</MobAviso>
      ) : (
        <>
          {erro && agenda && (
            <p style={{ fontSize: "0.78rem", color: "var(--mob-ambar)", margin: "0 0 0.8rem" }}>
              Não foi possível atualizar — mostrando a última agenda salva.
            </p>
          )}

          {!agenda ? (
            <p style={{ color: "var(--mob-muted)", padding: "1.5rem 0" }}>
              Sem internet e sem agenda salva ainda. Conecte-se uma vez para baixar.
            </p>
          ) : eventos.length === 0 ? (
            <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--mob-muted)" }}>
              <p style={{ fontSize: "1.15rem", fontWeight: 700, color: "var(--mob-text)" }}>Nada pendente para hoje 🎉</p>
              <p style={{ fontSize: "0.85rem", marginTop: "0.4rem" }}>
                Toda a agenda do dia está em dia. Bom trabalho!
              </p>
            </div>
          ) : (
            eventos.map(renderCartao)
          )}

          {/* Consulta antecipada: os dois dias seguintes, recolhidos. */}
          {agenda && (
            <>
              <DiaSeguinte dia={d1} prefixo="Amanhã" />
              <DiaSeguinte dia={d2} prefixo="Depois de amanhã" />
            </>
          )}
        </>
      )}
    </div>
  );
}
