"use client";
// Sub-tela: Acompanhamento (cronogramas sanitários) — NOVA, pedida para
// fechar o gap do app de campo: antes, um cronograma sanitário (regra do
// calendário marcada "Usar cronograma sanitário") só aparecia como pendência
// do DIA na Agenda, e sumia depois de decidido — não havia lista navegável
// de "o que está em aberto". Aqui: todo cronograma aberto/agendado/aguardando
// confirmação, com o detalhe por animal (sugerido → incluir/excluir) e a
// decisão de quem aplica (veterinário/equipe própria) ou adiar — mesmas
// ações da Agenda, mesmo endpoint (POST /agenda/realizados, prefixo
// cronograma_sanitario_*), só que numa tela que fica disponível o tempo
// todo, não só no dia previsto.
import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Stethoscope } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchCronogramasSanitarios, marcarEventoRealizado, fetchPessoas, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";
import { MobPill, LinhaPills } from "@/components/mobile/lancar/comum";

const PREFIXO = "cronograma_sanitario_";

type CronogramaAnimal = { id: number; numero_matriz: string; status: "sugerido" | "incluido" | "excluido" | "aplicado" };
type Cronograma = {
  id: number; calendario_sanitario_id: number; evento_sanitario_nome: string; categoria_alvo: string | null;
  data_evento: string; data_original: string | null; status: "aberto" | "agendado" | "concluido" | "cancelado";
  modo_execucao: "veterinario" | "propria" | null; veterinario_pessoa_id: number | null; veterinario_nome: string | null;
  animais_contagem: { sugerido: number; incluido: number; excluido: number; aplicado: number };
  animais: CronogramaAnimal[];
};

const STATUS_LABEL: Record<string, string> = {
  aberto: "Aguardando decisão", agendado: "Agendado", concluido: "Concluído", cancelado: "Cancelado",
};
const STATUS_COR: Record<string, string> = {
  aberto: "var(--mob-ambar)", agendado: "var(--mob-azul)", concluido: "var(--mob-verde)", cancelado: "var(--mob-muted)",
};
const STATUS_ANIMAL_LABEL: Record<string, string> = {
  sugerido: "Sugerido", incluido: "Incluído", excluido: "Excluído", aplicado: "Aplicado",
};
const STATUS_ANIMAL_COR: Record<string, string> = {
  sugerido: "var(--mob-ambar)", incluido: "var(--mob-verde)", excluido: "var(--mob-muted)", aplicado: "var(--mob-azul)",
};

export default function Cronogramas({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando, erro, recarregar } = useCarregar<Cronograma[]>(
    "menu_cronogramas_sanitarios", () => fetchCronogramasSanitarios()
  );
  const [filtro, setFiltro] = useState<"ativos" | "todos">("ativos");
  const [aberto, setAberto] = useState<number | null>(null);

  const lista = useMemo(() => {
    const todos = dados || [];
    const ativos = todos.filter((c) => c.status === "aberto" || c.status === "agendado");
    return (filtro === "ativos" ? ativos : todos).slice().sort((a, b) => a.data_evento.localeCompare(b.data_evento));
  }, [dados, filtro]);

  return (
    <div>
      <MobVoltar titulo="Acompanhamento" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_cronogramas_sanitarios" mostrar={doCache} />
      <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", margin: "-0.3rem 0 0.8rem" }}>
        Cronogramas das regras marcadas &ldquo;Usar cronograma sanitário&rdquo; — quem entrou na janela, quem foi incluído/excluído, e quem vai aplicar.
      </p>

      <LinhaPills>
        <MobPill ativa={filtro === "ativos"} onClick={() => setFiltro("ativos")}>Em aberto</MobPill>
        <MobPill ativa={filtro === "todos"} onClick={() => setFiltro("todos")}>Todos</MobPill>
      </LinhaPills>

      {erro && <p style={{ color: "var(--mob-vermelho)", fontSize: "0.85rem", marginBottom: "0.6rem", fontWeight: 600 }}>Não foi possível carregar.</p>}

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : lista.length === 0 ? (
        <Vazio icon={Stethoscope}>{filtro === "ativos" ? "Nenhum cronograma em aberto no momento." : "Nenhum cronograma encontrado."}</Vazio>
      ) : (
        lista.map((c) => (
          <CronogramaCard key={c.id} cron={c} expandido={aberto === c.id}
            onAlternar={() => setAberto((v) => (v === c.id ? null : c.id))}
            onMudou={recarregar} />
        ))
      )}
    </div>
  );
}

function CronogramaCard({ cron, expandido, onAlternar, onMudou }: {
  cron: Cronograma; expandido: boolean; onAlternar: () => void; onMudou: () => Promise<void>;
}) {
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [decidindoModo, setDecidindoModo] = useState<"veterinario" | "propria" | null>(null);
  const [veterinarioId, setVeterinarioId] = useState("");
  const [pessoas, setPessoas] = useState<any[] | null>(null);
  const [adiando, setAdiando] = useState(false);
  const [novaData, setNovaData] = useState(cron.data_evento);
  const [motivo, setMotivo] = useState("");

  const carregarPessoas = () => {
    if (pessoas) return;
    fetchPessoas().then(setPessoas).catch(() => setPessoas([]));
  };
  const veterinarios = (pessoas || []).filter((p) => p.ativo !== false && (p.tipos || []).some((t: string) => ["Veterinário", "Zootecnista"].includes(t)));

  async function decidirAnimal(animalId: number, incluir: boolean) {
    setOcupado(true); setErro(null);
    try {
      await marcarEventoRealizado(`${PREFIXO}animal_${animalId}`, undefined, undefined, { incluir });
      await onMudou();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(false); }
  }

  async function confirmarModo() {
    if (decidindoModo === "veterinario" && !veterinarioId) { setErro("Escolha o veterinário."); return; }
    setOcupado(true); setErro(null);
    try {
      await marcarEventoRealizado(`${PREFIXO}modo_${cron.id}`, undefined, undefined, {
        modo: decidindoModo!, veterinario_pessoa_id: decidindoModo === "veterinario" ? Number(veterinarioId) : undefined,
      });
      setDecidindoModo(null); setVeterinarioId("");
      await onMudou();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(false); }
  }

  async function confirmarAdiamento() {
    if (!novaData) { setErro("Informe a nova data."); return; }
    setOcupado(true); setErro(null);
    try {
      await marcarEventoRealizado(`${PREFIXO}modo_${cron.id}`, undefined, undefined, { nova_data: novaData, motivo: motivo || undefined });
      setAdiando(false); setMotivo("");
      await onMudou();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(false); }
  }

  async function aplicar() {
    if (!window.confirm(`Aplicar em todos os ${cron.animais_contagem.incluido} animal(is) incluído(s)?`)) return;
    setOcupado(true); setErro(null);
    try {
      await marcarEventoRealizado(`${PREFIXO}aplicar_${cron.id}`, undefined, undefined, {});
      await onMudou();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(false); }
  }

  const c = cron.animais_contagem;
  const sugeridos = cron.animais.filter((a) => a.status === "sugerido");

  return (
    <MobCard style={{ marginBottom: "0.6rem" }} onClick={() => { onAlternar(); if (!pessoas) carregarPessoas(); }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: "0.94rem" }}>{cron.evento_sanitario_nome}</div>
          <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>
            {cron.categoria_alvo || "Todos os animais"} · {formatDate(cron.data_evento)}
            {cron.data_original && cron.data_original !== cron.data_evento ? ` (adiado, era ${formatDate(cron.data_original)})` : ""}
          </div>
        </div>
        {expandido ? <ChevronDown size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} /> : <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.68rem", fontWeight: 700, padding: "0.2rem 0.55rem", borderRadius: 6, color: STATUS_COR[cron.status], background: "color-mix(in srgb, currentColor 12%, transparent)" }}>
          {STATUS_LABEL[cron.status] || cron.status}
        </span>
        <span style={{ fontSize: "0.74rem", color: "var(--mob-muted)" }}>
          {cron.veterinario_nome || (cron.modo_execucao === "propria" ? "Equipe própria" : "sem execução definida")}
        </span>
        <span style={{ fontSize: "0.72rem", color: "var(--mob-muted)", marginLeft: "auto" }}>
          {c.sugerido} sugerido · {c.incluido} incluído · {c.excluido} excluído · {c.aplicado} aplicado
        </span>
      </div>

      {expandido && (
        <div onClick={(e) => e.stopPropagation()} style={{ marginTop: "0.8rem", borderTop: "1px solid var(--mob-border)", paddingTop: "0.7rem" }}>
          {erro && <p style={{ color: "var(--mob-vermelho)", fontSize: "0.82rem", marginBottom: "0.6rem", fontWeight: 600 }}>{erro}</p>}

          {sugeridos.length > 0 && (
            <div style={{ marginBottom: "0.8rem" }}>
              <p style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--mob-muted)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: "0.4rem" }}>
                Aguardando decisão ({sugeridos.length})
              </p>
              {sugeridos.map((a) => (
                <div key={a.id} style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.4rem 0", borderTop: "1px solid var(--mob-border)" }}>
                  <span style={{ flex: 1, fontWeight: 700 }}>{a.numero_matriz}</span>
                  <button type="button" disabled={ocupado} onClick={() => decidirAnimal(a.id, true)}
                    style={{ fontSize: "0.76rem", fontWeight: 700, color: "var(--mob-verde-fg)", background: "var(--mob-verde)", border: "none", borderRadius: "var(--r-app)", padding: "0.35rem 0.7rem", cursor: "pointer" }}>
                    Incluir
                  </button>
                  <button type="button" disabled={ocupado} onClick={() => decidirAnimal(a.id, false)}
                    style={{ fontSize: "0.76rem", fontWeight: 700, color: "var(--mob-text)", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", borderRadius: "var(--r-app)", padding: "0.35rem 0.7rem", cursor: "pointer" }}>
                    Excluir
                  </button>
                </div>
              ))}
            </div>
          )}

          {(cron.status === "aberto" || cron.status === "agendado") && (
            <div style={{ marginBottom: "0.8rem" }}>
              <p style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--mob-muted)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: "0.4rem" }}>
                Quem vai aplicar
              </p>
              {decidindoModo === null ? (
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <button type="button" onClick={() => setDecidindoModo("veterinario")}
                    style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--mob-text)", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", borderRadius: "var(--r-app)", padding: "0.5rem 0.8rem", cursor: "pointer" }}>
                    Veterinário
                  </button>
                  <button type="button" disabled={ocupado} onClick={async () => {
                    setOcupado(true); setErro(null);
                    try {
                      await marcarEventoRealizado(`${PREFIXO}modo_${cron.id}`, undefined, undefined, { modo: "propria" });
                      await onMudou();
                    } catch (e: any) { setErro(e.message); }
                    finally { setOcupado(false); }
                  }}
                    style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--mob-text)", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", borderRadius: "var(--r-app)", padding: "0.5rem 0.8rem", cursor: "pointer" }}>
                    Equipe própria
                  </button>
                  <button type="button" onClick={() => setAdiando((v) => !v)}
                    style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--mob-dourado-2)", background: "none", border: "none", cursor: "pointer" }}>
                    Adiar
                  </button>
                </div>
              ) : (
                <div>
                  <select className="mob-input" value={veterinarioId} onChange={(e) => setVeterinarioId(e.target.value)} style={{ marginBottom: "0.5rem" }}>
                    <option value="">Selecione o veterinário…</option>
                    {veterinarios.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                  </select>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button type="button" disabled={ocupado} onClick={confirmarModo}
                      style={{ flex: 1, fontSize: "0.82rem", fontWeight: 700, color: "var(--mob-verde-fg)", background: "var(--mob-verde)", border: "none", borderRadius: "var(--r-app)", padding: "0.55rem", cursor: "pointer" }}>
                      {ocupado ? "…" : "Confirmar"}
                    </button>
                    <button type="button" onClick={() => { setDecidindoModo(null); setVeterinarioId(""); }}
                      style={{ flex: 1, fontSize: "0.82rem", fontWeight: 700, color: "var(--mob-text)", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", borderRadius: "var(--r-app)", padding: "0.55rem", cursor: "pointer" }}>
                      Cancelar
                    </button>
                  </div>
                </div>
              )}
              {adiando && (
                <div style={{ marginTop: "0.6rem" }}>
                  <input type="date" className="mob-input" value={novaData} onChange={(e) => setNovaData(e.target.value)} style={{ marginBottom: "0.5rem" }} />
                  <input className="mob-input" placeholder="Motivo (opcional)" value={motivo} onChange={(e) => setMotivo(e.target.value)} style={{ marginBottom: "0.5rem" }} />
                  <button type="button" disabled={ocupado} onClick={confirmarAdiamento}
                    style={{ width: "100%", fontSize: "0.82rem", fontWeight: 700, color: "var(--mob-verde-fg)", background: "var(--mob-verde)", border: "none", borderRadius: "var(--r-app)", padding: "0.55rem", cursor: "pointer" }}>
                    {ocupado ? "…" : "Adiar para esta data"}
                  </button>
                </div>
              )}
            </div>
          )}

          {cron.status === "agendado" && c.incluido > 0 && (
            <button type="button" disabled={ocupado} onClick={aplicar}
              style={{ width: "100%", fontSize: "0.85rem", fontWeight: 700, color: "var(--mob-verde-fg)", background: "var(--mob-verde)", border: "none", borderRadius: "var(--r-app)", padding: "0.6rem", cursor: "pointer" }}>
              {ocupado ? "Aplicando…" : `Aplicar em ${c.incluido} animal(is) incluído(s)`}
            </button>
          )}

          {cron.animais.filter((a) => a.status !== "sugerido").length > 0 && (
            <div style={{ marginTop: "0.8rem" }}>
              <p style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--mob-muted)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: "0.4rem" }}>
                Já decididos
              </p>
              {cron.animais.filter((a) => a.status !== "sugerido").map((a) => (
                <div key={a.id} style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.3rem 0" }}>
                  <span style={{ flex: 1, fontSize: "0.85rem" }}>{a.numero_matriz}</span>
                  <span style={{ fontSize: "0.7rem", fontWeight: 700, color: STATUS_ANIMAL_COR[a.status] }}>{STATUS_ANIMAL_LABEL[a.status]}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </MobCard>
  );
}
