"use client";
// Sub-tela: Histórico de tratamentos e vacinas (Menu › Sanidade).
//
// Espec de Sanidade aprovada pelo dono (out/2026):
//  - UMA lista com o curativo (aplicação avulsa e protocolo) e as vacinas/
//    exames do preventivo novo (o que o dia de vacinação grava), etiqueta
//    Curativo / Preventivo — antes só o curativo aparecia;
//  - filtros iguais aos de Menu › Produção, no SERVIDOR (GET
//    /sanidade/aplicacoes com `tipo`): período (padrão 60 dias; invertido
//    avisa e não consulta), rebanho / lote(s) (lote do animal NA DATA da
//    aplicação) / animal(is) por número exato, tipo e doença (quando houver);
//    lista agrupada por lote quando a pessoa escolhe lote(s);
//  - Excel/PDF com os filtros no cabeçalho e resumo por lote e tipo;
//  - responsável, observação e carência quando houver;
//  - "Marcar cura" nos curativos para QUALQUER usuário (POST …/cura);
//    editar/excluir continuam só para administrador.
import { useMemo, useState } from "react";
import { Pencil, Trash2, Check, X } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import {
  fetchSanidade, editarAplicacaoSanidade, excluirAplicacaoSanidade, ehAdmin, formatDate, fetchMedicamentos,
  fetchDoencas, marcarCuraAplicacao,
} from "@/lib/api";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import { useCarregar, AvisoCopia, Carregando, Vazio, ErroCarga } from "@/components/mobile/menu/comum";
import {
  AvisoCopiaOutroFiltro, ListaPorLote, LoteNaData, OpcoesFiltro, PainelFiltros, agruparPorLote, textoLote, useFiltrosProducao,
} from "@/components/mobile/menu/FiltrosProducao";
import { useCache } from "@/components/mobile/lancar/comum";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";
import { VIAS_APLICACAO } from "@/lib/constants";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";

const CHAVE = "menu_aplicacoes_sanidade";

type Tipo = "todos" | "curativo" | "preventivo";

type Carencia = {
  leite_dias: number | null; carne_dias: number | null; proibido_lactacao: boolean; texto: string;
  liberacao_leite: string | null; liberacao_carne: string | null;
} | null;

export type Aplic = {
  id: number; chave: string; tipo_historico: "curativo" | "preventivo" | string;
  numero: string; produto: string; categoria: string | null;
  dose: number | null; unidade: string | null; via: string | null;
  responsavel: string | null; obs: string | null; data: string | null;
  natureza: string | null; usuario_nome?: string | null; carencia?: Carencia;
  doenca_id?: number | null; doenca?: string | null; curada?: boolean | null;
  lote_na_data?: string | null; lote_fonte?: string | null;
};

const ROTULO_TIPO: Record<Tipo, string> = { todos: "Todos", curativo: "Curativo", preventivo: "Preventivo" };

const UNIDADES = ["ml", "L", "unidade", "dose", "kg", "saca 30kg", "saca 60kg"];

const inp: React.CSSProperties = {
  width: "100%", background: "var(--mob-surface-2)", color: "var(--mob-text)",
  border: "1px solid var(--mob-border)", borderRadius: "var(--r-app)", padding: "0.55rem 0.7rem", fontSize: "0.9rem",
};
const rotulo: React.CSSProperties = { display: "block", fontSize: "0.74rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.2rem" };
const btnAcao: React.CSSProperties = {
  flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: "0.4rem", fontSize: "0.85rem", fontWeight: 700,
  color: "var(--mob-text)", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", borderRadius: "var(--r-app)",
  padding: "0.55rem", minHeight: 44, cursor: "pointer",
};

const COLUNAS_EXPORT: ColunaExport[] = [
  { header: "Data", key: "data_br", width: 12 },
  { header: "Animal", key: "numero", width: 10 },
  { header: "Tipo", key: "tipo_txt", width: 12 },
  { header: "Produto / vacina", key: "produto", width: 28 },
  { header: "Categoria", key: "categoria", width: 14 },
  { header: "Dose", key: "dose_txt", width: 10 },
  { header: "Via", key: "via", width: 10 },
  { header: "Lote na data", key: "lote_txt", width: 22 },
  { header: "Doença", key: "doenca", width: 16 },
  { header: "Responsável", key: "responsavel", width: 16 },
  { header: "Carência", key: "carencia_txt", width: 26 },
  { header: "Cura", key: "cura_txt", width: 10 },
  { header: "Observação", key: "obs", width: 30 },
];
const COLUNAS_RESUMO: ColunaExport[] = [
  { header: "Lote", key: "lote", width: 24 },
  { header: "Tipo", key: "tipo", width: 12 },
  { header: "Aplicações", key: "aplicacoes", width: 12, numerico: true },
  { header: "Animais", key: "animais", width: 10, numerico: true },
];

const textoTipo = (t: string) => (t === "preventivo" ? "Preventivo" : "Curativo");
const textoCura = (c: boolean | null | undefined) => (c === true ? "Curado" : c === false ? "Não curado" : "");
/** Carência só quando há prazo/proibição de verdade (nunca "não informada" em cada linha). */
const temCarencia = (c: Carencia | undefined) => !!c && (c.leite_dias != null || c.carne_dias != null || c.proibido_lactacao);

/** Resumo do Excel/PDF: nº de aplicações e de animais por lote (na data) e tipo. */
export function resumoPorLoteTipo(regs: Aplic[]) {
  return agruparPorLote(regs, (r) => r.lote_na_data, (r) => r.numero).flatMap((b) => {
    const tipos = [...new Set(b.linhas.map((r) => textoTipo(r.tipo_historico)))].sort();
    return tipos.map((t) => {
      const ls = b.linhas.filter((r) => textoTipo(r.tipo_historico) === t);
      return { lote: b.lote, tipo: t, aplicacoes: ls.length, animais: new Set(ls.map((r) => r.numero)).size };
    });
  });
}

export default function AplicacoesSanidade({ onVoltar }: { onVoltar: () => void }) {
  const admin = ehAdmin();
  const f = useFiltrosProducao();
  const [tipo, setTipo] = useState<Tipo>("todos");
  const [doencaId, setDoencaId] = useState("");
  const { dados: doencasCad } = useCache<{ id: number; nome: string; ativo?: boolean }[]>("menu_remedios_doencas", () => fetchDoencas(), []);
  const doencas = (Array.isArray(doencasCad) ? doencasCad : []).filter((d) => d.ativo !== false);
  const usaDoenca = tipo !== "preventivo" && doencas.length > 0;
  const doencaAplicada = usaDoenca && doencaId ? doencaId : "";
  const filtros = { ...f.params, tipo, doencas: doencaAplicada ? [doencaAplicada] : undefined };
  const nomeDoenca = doencas.find((d) => String(d.id) === doencaAplicada)?.nome;
  const rotuloFiltros = [
    ...f.partesRotulo,
    `Tipo: ${ROTULO_TIPO[tipo]}`,
    ...(usaDoenca ? [`Doença: ${nomeDoenca || "todas"}`] : []),
  ].join(" · ");
  const pronto = f.periodoValido && f.escopoPronto;
  const { dados, doCache, carregando, mensagemErro, copiaDeOutroFiltro, recarregar } = useCarregar<{ aplicacoes: Aplic[] }>(
    CHAVE, () => fetchSanidade(filtros),
    { assinatura: JSON.stringify(filtros), habilitado: pronto, rotulo: rotuloFiltros },
  );

  const [editId, setEditId] = useState<number | null>(null);
  const [vals, setVals] = useState({ data: "", produto: "", dose: "", unidade: "", via: "", responsavel: "", obs: "" });
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  // Cura marcada nesta sessão (a lista recarrega por trás; offline segue a cópia).
  const [curas, setCuras] = useState<Record<number, boolean>>({});
  // Produtos só são buscados quando o administrador abre a edição.
  const [produtosCatalogo, setProdutosCatalogo] = useState<EstoqueItemPicker[] | null>(null);

  // Cópia offline salva por uma versão anterior (sem `chave`/`tipo_historico`):
  // vale a natureza; o BST/indução (Sanidade "preventivo", chave "c…") fica de
  // fora, como no servidor — "Preventivo" aqui é só vacina/exame ("p…").
  const regs = useMemo(() => [...(dados?.aplicacoes ?? [])]
    .map((a) => ({ ...a, chave: a.chave || `c${a.id}`, tipo_historico: a.tipo_historico || a.natureza || "curativo" }))
    .filter((a) => a.tipo_historico !== "preventivo" || a.chave.startsWith("p"))
    .sort((a, b) => ((a.data || "") < (b.data || "") ? 1 : (a.data || "") > (b.data || "") ? -1 : 0)), [dados]);
  const animais = useMemo(() => new Set(regs.map((r) => r.numero)).size, [regs]);
  const linhasExport = useMemo(() => regs.map((r) => ({
    ...r, data_br: r.data ? formatDate(r.data) : "", tipo_txt: textoTipo(r.tipo_historico),
    dose_txt: r.dose != null ? `${String(r.dose).replace(".", ",")}${r.unidade ? ` ${r.unidade}` : ""}` : "",
    lote_txt: textoLote(r.lote_na_data, r.lote_fonte), carencia_txt: temCarencia(r.carencia) ? r.carencia!.texto : "",
    cura_txt: textoCura(curas[r.id] ?? r.curada),
  })), [regs, curas]);
  const resumo = useMemo(() => resumoPorLoteTipo(regs), [regs]);

  const iniciar = (a: Aplic) => {
    setEditId(a.id);
    setVals({
      data: a.data ?? "", produto: a.produto ?? "", dose: a.dose == null ? "" : String(a.dose),
      unidade: a.unidade ?? "", via: a.via ?? "", responsavel: a.responsavel ?? "", obs: a.obs ?? "",
    });
    setErro(null);
    if (produtosCatalogo === null) {
      fetchMedicamentos({ incluir_sem_estoque: true }).then((m: EstoqueItemPicker[]) => setProdutosCatalogo(m)).catch(() => setProdutosCatalogo([]));
    }
  };

  const salvar = async (a: Aplic) => {
    setOcupado(a.chave); setErro(null);
    try {
      await editarAplicacaoSanidade(a.id, {
        data_aplicacao: vals.data || undefined,
        produto: vals.produto.trim() || undefined,
        dose: vals.dose.trim() === "" ? null : Number(vals.dose),
        unidade: vals.unidade || null,
        via: vals.via.trim() || null,
        responsavel: vals.responsavel.trim() || null,
        obs: vals.obs.trim() || null,
      });
      setEditId(null);
      await recarregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Erro ao salvar."); }
    finally { setOcupado(null); }
  };

  const excluir = async (a: Aplic) => {
    if (!window.confirm(`Excluir a aplicação de "${a.produto}" no animal ${a.numero}? Não dá para desfazer.`)) return;
    setOcupado(a.chave); setErro(null);
    try {
      await excluirAplicacaoSanidade(a.id);
      await recarregar();
    } catch (e) { setErro(e instanceof Error ? e.message : "Erro ao excluir."); }
    finally { setOcupado(null); }
  };

  const curar = async (a: Aplic, curada: boolean) => {
    setOcupado(a.chave); setErro(null); setMsg(null);
    try {
      await marcarCuraAplicacao(a.id, curada);
      setCuras((c) => ({ ...c, [a.id]: curada }));
      setMsg(`Animal ${a.numero}: marcado como ${curada ? "curado" : "não curado"}.`);
      recarregar();
    } catch (e) {
      const semSinal = typeof navigator !== "undefined" && !navigator.onLine;
      setErro(semSinal ? "Sem sinal: a cura não foi marcada. Tente de novo com sinal." : (e instanceof Error ? e.message : "Erro ao marcar cura."));
    } finally { setOcupado(null); }
  };

  return (
    <div>
      <MobVoltar titulo="Histórico de tratamentos e vacinas" subtitulo="Curativos, vacinas e exames" onVoltar={onVoltar} />
      <AvisoCopia chave={CHAVE} mostrar={doCache} />

      <PainelFiltros f={f}>
        <OpcoesFiltro rotulo="Tipo" valor={tipo} onChange={setTipo}
          opcoes={(Object.keys(ROTULO_TIPO) as Tipo[]).map((t) => ({ v: t, l: ROTULO_TIPO[t] }))} />
        {usaDoenca && (
          <div style={{ marginBottom: "0.7rem" }}>
            <label htmlFor="hist-doenca" style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.3rem" }}>
              Doença (do protocolo aplicado)
            </label>
            <select id="hist-doenca" className="mob-input" value={doencaId} onChange={(e) => setDoencaId(e.target.value)}>
              <option value="">Todas</option>
              {doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
            </select>
          </div>
        )}
      </PainelFiltros>

      {pronto && mensagemErro && <ErroCarga mensagem={`Não foi possível atualizar: ${mensagemErro}`} onTentar={recarregar} />}
      {pronto && copiaDeOutroFiltro && <AvisoCopiaOutroFiltro rotulo={dados?._rotuloFiltros} />}
      {erro && <ErroCarga mensagem={erro} />}
      {msg && <p role="status" style={{ color: "var(--mob-verde)", fontSize: "0.85rem", fontWeight: 700, margin: "0 0 0.6rem" }}>{msg}</p>}

      {!pronto ? null : carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : regs.length === 0 ? (
        <Vazio>Nenhuma aplicação no período/filtro.</Vazio>
      ) : (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem", marginBottom: "0.6rem" }}>
            <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", margin: 0 }}>
              {regs.length} {regs.length !== 1 ? "aplicações" : "aplicação"} · {animais} {animais !== 1 ? "animais" : "animal"}
            </p>
            <ExportarBotoes titulo="Histórico de tratamentos e vacinas" colunas={COLUNAS_EXPORT} linhas={linhasExport}
              nomeArquivoBase="historico-tratamentos-vacinas" filtros={rotuloFiltros}
              resumo={{ titulo: "Resumo por lote (lote na data da aplicação) e tipo", colunas: COLUNAS_RESUMO, linhas: resumo }} />
          </div>
          <ListaPorLote
            agrupar={f.agrupar} linhas={regs} loteDe={(r) => r.lote_na_data} numeroDe={(r) => r.numero}
            detalheBloco={(b) => <>{b.linhas.length} {b.linhas.length !== 1 ? "aplicações" : "aplicação"}</>}
            render={(a, i) => {
              const editando = admin && editId === a.id && a.tipo_historico !== "preventivo";
              const curativo = a.tipo_historico !== "preventivo";
              const cura = curas[a.id] ?? a.curada;
              return (
                <MobCard key={a.chave} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.6rem" }}>
                  {!editando ? (
                    <>
                      <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem" }}>
                        <span style={{ fontWeight: 800, fontSize: "1.05rem" }}>Nº {a.numero}</span>
                        <span style={{
                          fontSize: "0.7rem", fontWeight: 800, padding: "0.1rem 0.5rem", borderRadius: 999, letterSpacing: "0.02em",
                          border: `1px solid ${curativo ? "var(--mob-border)" : "var(--mob-verde)"}`,
                          color: curativo ? "var(--mob-text)" : "var(--mob-verde)",
                        }}>{textoTipo(a.tipo_historico)}</span>
                        <span style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginLeft: "auto" }}>{a.data ? formatDate(a.data) : "sem data"}</span>
                      </div>
                      <div style={{ fontSize: "0.92rem", fontWeight: 600, marginTop: "0.25rem" }}>{a.produto}</div>
                      <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>
                        {a.categoria || "Outros"}
                        {a.dose != null ? ` · ${String(a.dose).replace(".", ",")}${a.unidade ? " " + a.unidade : ""}` : ""}
                        {a.via ? ` · ${a.via}` : ""}
                        {a.doenca ? ` · ${a.doenca}` : ""}
                      </div>
                      <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
                        <LoteNaData lote={a.lote_na_data} fonte={a.lote_fonte} />
                        {a.responsavel ? ` · Responsável: ${a.responsavel}` : ""}
                      </div>
                      {temCarencia(a.carencia) && (
                        <div style={{ fontSize: "0.8rem", color: "var(--mob-ambar)", fontWeight: 700, marginTop: "0.2rem" }}>
                          {a.carencia!.texto}
                          {a.carencia!.liberacao_leite ? ` · leite liberado em ${formatDate(a.carencia!.liberacao_leite)}` : ""}
                        </div>
                      )}
                      {a.obs && <div style={{ fontSize: "0.8rem", color: "var(--mob-text)", marginTop: "0.2rem" }}>{a.obs}</div>}
                      {curativo && (
                        <div style={{ marginTop: "0.6rem" }}>
                          {cura != null && (
                            <p style={{ fontSize: "0.8rem", fontWeight: 700, margin: "0 0 0.35rem", color: cura ? "var(--mob-verde)" : "var(--mob-vermelho)" }}>
                              {cura ? "Curado" : "Não curado"}
                            </p>
                          )}
                          <div role="group" aria-label={`Marcar cura do animal ${a.numero}`} style={{ display: "flex", gap: "0.5rem" }}>
                            <button type="button" style={btnAcao} disabled={ocupado === a.chave} aria-pressed={cura === true}
                              onClick={() => curar(a, true)}><Check size={15} aria-hidden="true" /> {cura === true ? "Curado" : "Marcar curado"}</button>
                            <button type="button" style={btnAcao} disabled={ocupado === a.chave} aria-pressed={cura === false}
                              onClick={() => curar(a, false)}><X size={15} aria-hidden="true" /> Não curou</button>
                          </div>
                        </div>
                      )}
                      {admin && curativo && (
                        <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
                          <button type="button" onClick={() => iniciar(a)} style={btnAcao}>
                            <Pencil size={15} aria-hidden="true" /> Editar
                          </button>
                          <button type="button" disabled={ocupado === a.chave} onClick={() => excluir(a)}
                            style={{ ...btnAcao, color: "var(--mob-vermelho)", background: "transparent", border: "1px solid var(--mob-vermelho)" }}>
                            <Trash2 size={15} aria-hidden="true" /> Excluir
                          </button>
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <div style={{ fontWeight: 800, fontSize: "1rem", marginBottom: "0.6rem" }}>Animal {a.numero}</div>
                      <div style={{ marginBottom: "0.6rem" }}><label style={rotulo}>Data</label>
                        <input type="date" style={inp} value={vals.data} onChange={(e) => setVals((s) => ({ ...s, data: e.target.value }))} /></div>
                      <div style={{ marginBottom: "0.6rem" }}><label style={rotulo}>Produto</label>
                        <EstoquePicker itens={produtosCatalogo || []} value={vals.produto} onChange={(v) => setVals((s) => ({ ...s, produto: v }))}
                          placeholder="Selecione…" incluirNaoEstocaveis /></div>
                      <div style={{ display: "flex", gap: "0.6rem", marginBottom: "0.6rem" }}>
                        <div style={{ flex: 1 }}><label style={rotulo}>Dose</label>
                          <input type="number" inputMode="decimal" style={inp} value={vals.dose} onChange={(e) => setVals((s) => ({ ...s, dose: e.target.value }))} /></div>
                        <div style={{ flex: 1 }}><label style={rotulo}>Unidade</label>
                          <select style={inp} value={vals.unidade} onChange={(e) => setVals((s) => ({ ...s, unidade: e.target.value }))}>
                            <option value="">—</option>
                            {!UNIDADES.includes(vals.unidade) && vals.unidade && <option value={vals.unidade}>{vals.unidade}</option>}
                            {UNIDADES.map((u) => <option key={u} value={u}>{u}</option>)}
                          </select></div>
                      </div>
                      <div style={{ marginBottom: "0.6rem" }}><label style={rotulo}>Via</label>
                        <select style={inp} value={vals.via} onChange={(e) => setVals((s) => ({ ...s, via: e.target.value }))}>
                          <option value="">—</option>
                          {!VIAS_APLICACAO.includes(vals.via) && vals.via && <option value={vals.via}>{vals.via}</option>}
                          {VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
                        </select></div>
                      <div style={{ marginBottom: "0.6rem" }}><label style={rotulo}>Responsável</label>
                        <select style={inp} value={vals.responsavel} onChange={(e) => setVals((s) => ({ ...s, responsavel: e.target.value }))}>
                          <option value="">—</option>
                          {!nomesResponsaveis.includes(vals.responsavel) && vals.responsavel && <option value={vals.responsavel}>{vals.responsavel}</option>}
                          {nomesResponsaveis.map((r) => <option key={r} value={r}>{r}</option>)}
                        </select></div>
                      <div style={{ marginBottom: "0.2rem" }}><label style={rotulo}>Observação</label>
                        <input style={inp} value={vals.obs} onChange={(e) => setVals((s) => ({ ...s, obs: e.target.value }))} /></div>
                      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.7rem" }}>
                        <button type="button" disabled={ocupado === a.chave} onClick={() => salvar(a)}
                          style={{ ...btnAcao, color: "var(--mob-verde-fg)", background: "var(--mob-verde)", border: "none" }}>
                          <Check size={16} aria-hidden="true" /> {ocupado === a.chave ? "…" : "Salvar"}
                        </button>
                        <button type="button" disabled={ocupado === a.chave} onClick={() => setEditId(null)} style={btnAcao}>
                          <X size={16} aria-hidden="true" /> Cancelar
                        </button>
                      </div>
                    </>
                  )}
                </MobCard>
              );
            }}
          />
        </>
      )}
    </div>
  );
}
