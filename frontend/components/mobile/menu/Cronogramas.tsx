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
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Stethoscope } from "lucide-react";
import { MobVoltar, MobCard, MobCampo, MobConfirmModal } from "@/components/mobile/ui";
import {
  fetchCronogramasSanitarios, marcarEventoRealizado, fetchPessoas, fetchEventosSanitarios, fetchMedicamentos, formatDate,
} from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";
import { MobPill, LinhaPills, unidadesCompativeis } from "@/components/mobile/lancar/comum";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import { VIAS_APLICACAO } from "@/lib/constants";

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

// Produto/dose/unidade padrão cadastrado no evento sanitário (Configurações >
// Cadastro > Sanidade > Eventos) — só serve de SUGESTÃO inicial no modal de
// "Aplicar em incluídos"; o usuário sempre pode trocar antes de confirmar
// (ver CronogramaCard). Casado por nome porque o cronograma (aqui) não
// carrega evento_sanitario_id — nome é único por fazenda (uq no cadastro).
type PadraoEvento = { produto_padrao: string | null; dose_padrao: number | null; unidade_padrao: string | null };

export default function Cronogramas({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando, erro, recarregar } = useCarregar<Cronograma[]>(
    "menu_cronogramas_sanitarios", () => fetchCronogramasSanitarios()
  );
  const [filtro, setFiltro] = useState<"ativos" | "todos">("ativos");
  const [aberto, setAberto] = useState<number | null>(null);
  // Padrões por evento (nome → produto/dose/unidade cadastrados) — carregado
  // uma vez, só para sugerir valores iniciais no modal de aplicação de cada
  // card (nunca bloqueia a tela se falhar).
  const [padroesPorNome, setPadroesPorNome] = useState<Record<string, PadraoEvento>>({});
  useEffect(() => {
    fetchEventosSanitarios()
      .then((evs: any[]) => {
        const mapa: Record<string, PadraoEvento> = {};
        (evs || []).forEach((e) => {
          mapa[e.nome] = { produto_padrao: e.produto_padrao ?? null, dose_padrao: e.dose_padrao ?? null, unidade_padrao: e.unidade_padrao ?? null };
        });
        setPadroesPorNome(mapa);
      })
      .catch(() => {});
  }, []);

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
            onMudou={recarregar} padraoEvento={padroesPorNome[c.evento_sanitario_nome]} />
        ))
      )}
    </div>
  );
}

function CronogramaCard({ cron, expandido, onAlternar, onMudou, padraoEvento }: {
  cron: Cronograma; expandido: boolean; onAlternar: () => void; onMudou: () => Promise<void>; padraoEvento?: PadraoEvento;
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
  const responsaveisNomes = (pessoas || []).filter((p) => p.ativo !== false).map((p) => p.nome as string).sort((a, b) => a.localeCompare(b, "pt-BR"));

  // Modal "Aplicar em incluídos" — medicamento/vacina + dose + unidade,
  // todos editáveis (bug relatado: antes o botão mandava a aplicação direto
  // sem produto/dose/unidade nenhum, e o backend recusava com 400 "Informe o
  // medicamento, a dose e a unidade..." quando o evento não tinha padrão
  // cadastrado — ver fazenda/api/routers/sanidade.py::cadastrar_preventivo).
  const [aplicando, setAplicando] = useState(false);
  const [produtosCatalogo, setProdutosCatalogo] = useState<EstoqueItemPicker[] | null>(null);
  const [produtoAplicar, setProdutoAplicar] = useState("");
  const [doseAplicar, setDoseAplicar] = useState("");
  const [unidadeAplicar, setUnidadeAplicar] = useState("");
  const [unidadeTocada, setUnidadeTocada] = useState(false);
  const [viaAplicar, setViaAplicar] = useState("");
  const [responsavelAplicar, setResponsavelAplicar] = useState("");
  const [obsAplicar, setObsAplicar] = useState("");

  const compativeisAplicar = useMemo(
    () => unidadesCompativeis((produtosCatalogo || []).find((p) => p.nome === produtoAplicar)?.unidade),
    [produtosCatalogo, produtoAplicar],
  );

  // Sugere a unidade só depois que o catálogo do estoque chega (evita
  // "adivinhar" com a lista genérica e travar depois quando o produto real
  // não aceitar aquela unidade) — e só enquanto o usuário não tiver trocado
  // a unidade manualmente. Mesmo critério do lançamento avulso (FormSanidade
  // escolherProduto): usa o padrão do evento quando ele é compatível com o
  // estoque do produto escolhido; senão, a 1ª unidade compatível.
  useEffect(() => {
    if (!aplicando || unidadeTocada || !produtoAplicar) return;
    const sugestao = produtoAplicar === padraoEvento?.produto_padrao && padraoEvento?.unidade_padrao && compativeisAplicar.includes(padraoEvento.unidade_padrao)
      ? padraoEvento.unidade_padrao
      : (compativeisAplicar[0] || "");
    setUnidadeAplicar(sugestao);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aplicando, produtoAplicar, compativeisAplicar, unidadeTocada]);

  function escolherProdutoAplicar(nome: string) {
    setProdutoAplicar(nome);
    setUnidadeTocada(false); // produto novo → deixa o efeito acima sugerir de novo
  }

  function abrirAplicar() {
    carregarPessoas();
    if (!produtosCatalogo) {
      fetchMedicamentos({ incluir_sem_estoque: true }).then(setProdutosCatalogo).catch(() => setProdutosCatalogo([]));
    }
    setProdutoAplicar(padraoEvento?.produto_padrao || "");
    setDoseAplicar(padraoEvento?.dose_padrao != null ? String(padraoEvento.dose_padrao) : "");
    setUnidadeAplicar("");
    setUnidadeTocada(false);
    setViaAplicar("");
    setResponsavelAplicar(cron.veterinario_nome || "");
    setObsAplicar("");
    setErro(null);
    setAplicando(true);
  }

  async function confirmarAplicar() {
    if (!produtoAplicar) { setErro("Selecione o medicamento/vacina."); return; }
    if (!(Number(doseAplicar) > 0)) { setErro("Informe a dose."); return; }
    if (!unidadeAplicar) { setErro("Selecione a unidade."); return; }
    setOcupado(true); setErro(null);
    try {
      await marcarEventoRealizado(`${PREFIXO}aplicar_${cron.id}`, undefined, undefined, {
        produto: produtoAplicar, dose: Number(doseAplicar), unidade: unidadeAplicar,
        via: viaAplicar || undefined, responsavel: responsavelAplicar || undefined, observacao: obsAplicar || undefined,
      });
      setAplicando(false);
      await onMudou();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(false); }
  }

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
            <button type="button" disabled={ocupado} onClick={abrirAplicar}
              style={{ width: "100%", fontSize: "0.85rem", fontWeight: 700, color: "var(--mob-verde-fg)", background: "var(--mob-verde)", border: "none", borderRadius: "var(--r-app)", padding: "0.6rem", cursor: "pointer" }}>
              Aplicar em {c.incluido} animal(is) incluído(s)
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

      {aplicando && (
        <MobConfirmModal
          titulo={`Aplicar ${cron.evento_sanitario_nome}`}
          onConfirmar={confirmarAplicar}
          onCancelar={() => setAplicando(false)}
          confirmando={ocupado}
          textoConfirmar={ocupado ? "Aplicando…" : "Confirmar aplicação"}
        >
          <div onClick={(e) => e.stopPropagation()}>
            <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginBottom: "0.8rem" }}>
              Em {c.incluido} animal(is) incluído(s). Escolha o medicamento/vacina, a dose e a unidade aplicados.
            </p>
            {erro && <p style={{ color: "var(--mob-vermelho)", fontSize: "0.82rem", marginBottom: "0.6rem", fontWeight: 600 }}>{erro}</p>}
            <MobCampo label="Medicamento / vacina">
              <EstoquePicker itens={produtosCatalogo || []} value={produtoAplicar} onChange={escolherProdutoAplicar}
                placeholder="Selecione o produto…" incluirNaoEstocaveis />
            </MobCampo>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
              <MobCampo label="Dose">
                <input type="number" inputMode="decimal" className="mob-input" value={doseAplicar}
                  onChange={(e) => setDoseAplicar(e.target.value)} placeholder="0" />
              </MobCampo>
              <MobCampo label="Unidade">
                <select className="mob-input" value={unidadeAplicar}
                  onChange={(e) => { setUnidadeAplicar(e.target.value); setUnidadeTocada(true); }}>
                  {!unidadeAplicar && <option value="">—</option>}
                  {compativeisAplicar.map((u) => <option key={u} value={u}>{u}</option>)}
                </select>
              </MobCampo>
            </div>
            <MobCampo label="Via de aplicação (opcional)">
              <select className="mob-input" value={viaAplicar} onChange={(e) => setViaAplicar(e.target.value)}>
                <option value="">Selecione…</option>
                {VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </MobCampo>
            <MobCampo label="Responsável (opcional)">
              <select className="mob-input" value={responsavelAplicar} onChange={(e) => setResponsavelAplicar(e.target.value)}>
                <option value="">Selecione…</option>
                {!responsaveisNomes.includes(responsavelAplicar) && responsavelAplicar && (
                  <option value={responsavelAplicar}>{responsavelAplicar}</option>
                )}
                {responsaveisNomes.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </MobCampo>
            <MobCampo label="Observação (opcional)">
              <input className="mob-input" value={obsAplicar} onChange={(e) => setObsAplicar(e.target.value)} />
            </MobCampo>
          </div>
        </MobConfirmModal>
      )}
    </MobCard>
  );
}
