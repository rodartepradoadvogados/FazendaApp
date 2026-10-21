"use client";
// Sub-tela SANIDADE: espelha a estrutura do site — duas modalidades,
// Curativa (aplicação avulsa de remédio ou protocolo sanitário) e Preventiva
// (vacina/exame — lançamento simples do módulo novo, em implantação — e BST).
// Endpoints: POST /sanidade/aplicacoes | POST /sanidade/protocolos/lancamentos |
// GET /agenda/ (BST).
import { useEffect, useMemo, useState } from "react";
import { Syringe, ClipboardList, Bandage, ShieldCheck, Droplets } from "lucide-react";
import { MobCampo, MobAviso, MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchEstoqueAtivos, fetchProtocolosSanitarios, fetchMedicamentos, fetchPrincipiosAtivos, fetchDoencas, fetchAgenda, formatDate, fetchIndicacoesDoenca, type OpcaoIndicacaoDoenca } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";
import { EstoquePicker } from "@/components/EstoquePicker";
import EmConstrucao from "@/components/sanitario/EmConstrucao";
import { VIAS_APLICACAO } from "@/lib/constants";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import {
  type Animal, type EstoqueItem, useCache, useEnvio, useRascunho, hoje,
  MobPill, LinhaPills, SeletorAnimal, unidadesCompativeis, GradeAcoes, RascunhoAviso,
} from "./comum";

type Protocolo = { id: number; nome: string; eh_mastite?: boolean };
const CLASSIF_MASTITE = ["clinica", "subclinica", "ambiental"];

// Estoque zerado/baixo do produto selecionado — mesma regra do site (saldo
// <= 0 ou abaixo do mínimo cadastrado; `/estoque/` já devolve `abaixo_minimo`
// pronto, ver app/estoque/page.tsx, então só reaproveitamos o campo).
function itemEstoqueBaixo(estoque: EstoqueItem[], produto: string): { baixo: boolean; zerado: boolean } {
  const item = estoque.find((e) => e.nome === produto) as (EstoqueItem & { abaixo_minimo?: boolean | null }) | undefined;
  if (!item) return { baixo: false, zerado: false };
  const zerado = (item.quantidade ?? 0) <= 0;
  return { baixo: zerado || item.abaixo_minimo === true, zerado };
}

type Modalidade = "curativa" | "preventiva";
type TipoCurativa = "aplicacao" | "protocolo";
// "vacina" é o ponto de encaixe do lançamento simples de vacina/exame do
// Sanitário Preventivo v2 (o preventivo antigo saiu); BST segue como sempre.
type TipoPreventiva = "vacina" | "bst";

const TITULOS_PREV: Record<TipoPreventiva, string> = {
  vacina: "Vacina ou exame", bst: "BST",
};

export function FormSanidade({ animais, animalFixado }: {
  animais: Animal[]; animalFixado: string | null;
}) {
  const estoque = useCache<EstoqueItem[]>("estoque_itens", () => fetchEstoqueAtivos().then((d) => d.itens as EstoqueItem[]), []);

  const [modalidade, setModalidade] = useState<Modalidade | null>(null);
  const [tipo, setTipo] = useState<TipoCurativa | null>(null);
  const [tipoPrev, setTipoPrev] = useState<TipoPreventiva | null>(null);

  if (!modalidade) {
    return (
      <GradeAcoes
        opcoes={[
          { id: "curativa", label: "Curativa", icone: <Bandage size={28} />, cor: "var(--mob-vermelho)" },
          { id: "preventiva", label: "Preventiva", icone: <ShieldCheck size={28} />, cor: "var(--mob-verde)" },
        ]}
        onEscolher={(id) => setModalidade(id as Modalidade)}
      />
    );
  }

  if (modalidade === "preventiva") {
    if (!tipoPrev) {
      return (
        <>
          <MobVoltar titulo="Preventiva" onVoltar={() => setModalidade(null)} />
          <GradeAcoes
            opcoes={[
              { id: "vacina", label: "Vacina ou exame", icone: <Syringe size={28} />, cor: "var(--mob-azul)" },
              { id: "bst", label: "BST", icone: <Droplets size={28} />, cor: "var(--mob-amarelo)" },
            ]}
            onEscolher={(id) => setTipoPrev(id as TipoPreventiva)}
          />
        </>
      );
    }
    return (
      <>
        <MobVoltar titulo={TITULOS_PREV[tipoPrev]} onVoltar={() => setTipoPrev(null)} />
        {tipoPrev === "vacina" && <EmConstrucao compacto titulo="Vacina ou exame (lançamento simples)" />}
        {tipoPrev === "bst" && <PreventivoBst />}
      </>
    );
  }

  // ── Curativa ────────────────────────────────────────────────────────────────
  if (!tipo) {
    return (
      <>
        <MobVoltar titulo="Curativa" onVoltar={() => setModalidade(null)} />
        <GradeAcoes
          opcoes={[
            { id: "aplicacao", label: "Aplicação de remédio", icone: <Syringe size={28} />, cor: "var(--mob-azul)" },
            { id: "protocolo", label: "Protocolo sanitário", icone: <ClipboardList size={28} />, cor: "var(--mob-roxo)" },
          ]}
          onEscolher={(id) => setTipo(id as TipoCurativa)}
        />
      </>
    );
  }

  return (
    <>
      <MobVoltar titulo={tipo === "aplicacao" ? "Aplicação de remédio" : "Protocolo sanitário"} onVoltar={() => setTipo(null)} />
      <CurativaForm tipo={tipo} animais={animais} animalFixado={animalFixado} estoque={estoque.dados} />
    </>
  );
}

// ── Curativa: aplicação avulsa OU protocolo sanitário ────────────────────────
// Exportado para a tela Lançar > Protocolos usar o MESMO formulário de
// protocolo sanitário (tipo="protocolo") — ver FormProtocolos.
export function CurativaForm({ tipo, animais, animalFixado, estoque }: { tipo: TipoCurativa; animais: Animal[]; animalFixado: string | null; estoque: EstoqueItem[] }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const protocolos = useCache<Protocolo[]>("protocolos_sanitarios", () => fetchProtocolosSanitarios() as Promise<Protocolo[]>, []);

  // Rascunho do alvo (animal/lote escolhido) — o passo mais trabalhoso, não
  // se perde numa interrupção (docs/agents/design-implementation.md §5,
  // acabamento-de-campo.html).
  const rascunhoAlvo = useRascunho<{ modo: "animal" | "lote"; animal: string; lote: string }>(
    "sanidade_curativa_alvo", { modo: "animal", animal: animalFixado || "", lote: "" },
  );
  const { modo, animal, lote } = rascunhoAlvo.valor;
  const atualizarAlvo = (patch: Partial<{ modo: "animal" | "lote"; animal: string; lote: string }>) =>
    rascunhoAlvo.setValor((atual) => ({ ...atual, ...patch }));
  const setModo = (v: "animal" | "lote") => atualizarAlvo({ modo: v });
  const setAnimal = (v: string) => atualizarAlvo({ animal: v });
  const setLote = (v: string) => atualizarAlvo({ lote: v });
  const [data, setData] = useState(hoje());
  const [produto, setProduto] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [unidade, setUnidade] = useState("");
  const [via, setVia] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [aplicado, setAplicado] = useState(true);
  // Filtrar o medicamento por doença / princípio ativo (abre só os que casam).
  const [filtrarPor, setFiltrarPor] = useState<"todos" | "principio_ativo" | "doenca">("todos");
  const [criterio, setCriterio] = useState("");
  const [principiosNomes, setPrincipiosNomes] = useState<string[]>([]);
  // Guarda id junto do nome (não só o nome) porque o substituto inteligente
  // (indicações por doença) precisa do id da doença, não do texto.
  const [doencas, setDoencas] = useState<{ id: number; nome: string }[]>([]);
  const [medicamentosFiltrados, setMedicamentosFiltrados] = useState<string[] | null>(null);
  useEffect(() => {
    fetchComCache<string[]>("sanidade_principios_ativos_nomes", () => fetchPrincipiosAtivos().then((d: any[]) => d.map((p) => p.nome)))
      .then(({ dados }) => setPrincipiosNomes(dados || []));
    fetchComCache<{ id: number; nome: string }[]>("sanidade_doencas_lista", () => fetchDoencas().then((d: any[]) => d.map((x) => ({ id: x.id, nome: x.nome }))))
      .then(({ dados }) => setDoencas(dados || []));
  }, []);
  useEffect(() => {
    if (filtrarPor === "todos" || !criterio) { setMedicamentosFiltrados(null); return; }
    const filtro = filtrarPor === "principio_ativo" ? { principio_ativo: criterio } : { doenca: criterio };
    fetchMedicamentos(filtro).then((m: any[]) => setMedicamentosFiltrados(m.map((x) => x.nome))).catch(() => setMedicamentosFiltrados([]));
  }, [filtrarPor, criterio]);
  const doencasNomes = useMemo(() => doencas.map((d) => d.nome), [doencas]);

  // Substituto inteligente: filtrando por doença + produto escolhido com
  // estoque baixo/zerado → busca as alternativas indicadas pra doença.
  const [indicacoes, setIndicacoes] = useState<OpcaoIndicacaoDoenca[] | null>(null);
  const { baixo: produtoEstoqueBaixo, zerado: produtoEstoqueZerado } = itemEstoqueBaixo(estoque, produto);
  useEffect(() => {
    if (filtrarPor !== "doenca" || !criterio || !produto || !produtoEstoqueBaixo) { setIndicacoes(null); return; }
    const doencaId = doencas.find((d) => d.nome === criterio)?.id;
    if (!doencaId) { setIndicacoes(null); return; }
    let vivo = true;
    fetchIndicacoesDoenca(doencaId)
      .then((r) => { if (vivo) setIndicacoes(r.opcoes.length ? r.opcoes : null); })
      .catch(() => { if (vivo) setIndicacoes(null); });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtrarPor, criterio, produto, produtoEstoqueBaixo, doencas]);
  // Protocolo sanitário
  const [protocoloId, setProtocoloId] = useState("");
  const [classifMastite, setClassifMastite] = useState("");
  const [obs, setObs] = useState("");

  // Lotes = grupos primários distintos dos animais (mesma base do desktop).
  const lotes = useMemo(() => {
    const set = new Set<string>();
    animais.forEach((a) => { if (a.grupo_primario) set.add(a.grupo_primario); });
    return Array.from(set).sort();
  }, [animais]);

  const itensProduto = useMemo(() => {
    if (!medicamentosFiltrados) return estoque;
    const nomes = new Set(medicamentosFiltrados);
    return estoque.filter((e) => nomes.has(e.nome));
  }, [estoque, medicamentosFiltrados]);
  const compativeis = useMemo(() => unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade), [estoque, produto]);
  const protoSel = protocolos.dados.find((p) => String(p.id) === protocoloId);

  function escolherProduto(nome: string) {
    setProduto(nome);
    const comp = unidadesCompativeis(estoque.find((e) => e.nome === nome)?.unidade);
    setUnidade(comp[0] || "");
  }

  const alvoAnimais = () => modo === "animal"
    ? (animal ? [animal] : [])
    : animais.filter((a) => a.grupo_primario === lote).map((a) => a.numero);

  function salvar() {
    const alvo = alvoAnimais();
    if (!alvo.length) return erroValidacao(modo === "animal" ? "Selecione o animal." : "Selecione o lote.");

    if (tipo === "protocolo") {
      if (!protocoloId) return erroValidacao("Selecione o protocolo.");
      if (protoSel?.eh_mastite && alvo.length > 1) return erroValidacao("Protocolo de mastite: lance um animal por vez.");
      if (protoSel?.eh_mastite && !classifMastite) return erroValidacao("Informe a classificação da mastite.");
      enviar(
        "/sanidade/protocolos/lancamentos",
        {
          protocolo_id: Number(protocoloId), numeros_matriz: alvo, data_inicio: data,
          responsavel: responsavel || undefined, observacao: obs || undefined,
          classificacao_mastite: protoSel?.eh_mastite ? classifMastite : undefined,
        },
        `Protocolo ${protoSel?.nome || ""} — ${modo === "animal" ? `animal ${animal}` : `lote ${lote}`}`,
        () => { setProtocoloId(""); setClassifMastite(""); setObs(""); },
      );
      return;
    }

    if (!produto) return erroValidacao("Selecione o produto.");
    if (!(Number(quantidade) > 0)) return erroValidacao("Informe a quantidade.");
    if (!unidade) return erroValidacao("Selecione a unidade.");
    const aplicadoEfetivo = aplicado && data <= hoje();
    enviar(
      "/sanidade/aplicacoes",
      {
        data_aplicacao: data, animais: alvo, responsavel: responsavel || undefined, aplicado: aplicadoEfetivo,
        itens: [{ produto, quantidade: Number(quantidade), unidade, via: via || undefined }],
      },
      `Aplicação ${produto} — ${modo === "animal" ? `animal ${animal}` : `lote ${lote}`}`,
      () => { setProduto(""); setQuantidade(""); setUnidade(""); setVia(""); },
    );
  }

  return (
    <>
      <RascunhoAviso mostrar={rascunhoAlvo.salvo} />
      <LinhaPills>
        <MobPill ativa={modo === "animal"} onClick={() => setModo("animal")}>Animal</MobPill>
        <MobPill ativa={modo === "lote"} onClick={() => setModo("lote")}>Lote</MobPill>
      </LinhaPills>

      {modo === "animal" ? (
        <MobCampo label="Animal (nº / nome)">
          <SeletorAnimal animais={animais} valor={animal} onChange={setAnimal} placeholder="Buscar animal…" />
        </MobCampo>
      ) : (
        <MobCampo label="Lote">
          <select className="mob-input" value={lote} onChange={(e) => setLote(e.target.value)}>
            <option value="">Selecione o lote…</option>
            {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </MobCampo>
      )}

      <MobCampo label="Data">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>

      {tipo === "protocolo" ? (
        <>
          <MobCampo label="Protocolo sanitário">
            <select className="mob-input" value={protocoloId} onChange={(e) => setProtocoloId(e.target.value)}>
              <option value="">Selecione o protocolo…</option>
              {protocolos.dados.map((p) => <option key={p.id} value={p.id}>{p.nome}{p.eh_mastite ? " (mastite)" : ""}</option>)}
            </select>
          </MobCampo>
          {protoSel?.eh_mastite && (
            <MobCampo label="Classificação da mastite">
              <select className="mob-input" value={classifMastite} onChange={(e) => setClassifMastite(e.target.value)}>
                <option value="">Selecione…</option>
                {CLASSIF_MASTITE.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </MobCampo>
          )}
          <MobCampo label="Observação">
            <input className="mob-input" value={obs} onChange={(e) => setObs(e.target.value)} />
          </MobCampo>
        </>
      ) : (
        <>
          <MobCampo label="Filtrar medicamento por">
            <select className="mob-input" value={filtrarPor} onChange={(e) => { setFiltrarPor(e.target.value as typeof filtrarPor); setCriterio(""); setProduto(""); }}>
              <option value="todos">Todos os medicamentos</option>
              <option value="principio_ativo">Princípio ativo</option>
              <option value="doenca">Doença</option>
            </select>
          </MobCampo>
          {filtrarPor !== "todos" && (
            <MobCampo label={filtrarPor === "principio_ativo" ? "Princípio ativo" : "Doença"}>
              <select className="mob-input" value={criterio} onChange={(e) => { setCriterio(e.target.value); setProduto(""); }}>
                <option value="">Selecione…</option>
                {(filtrarPor === "principio_ativo" ? principiosNomes : doencasNomes).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </MobCampo>
          )}
          <MobCampo label="Produto / medicamento">
            <EstoquePicker itens={itensProduto} value={produto} onChange={escolherProduto} placeholder="Selecione o produto…"
              disabled={filtrarPor !== "todos" && !criterio} incluirNaoEstocaveis />
          </MobCampo>
          {indicacoes && (
            <SubstitutoBanner indicacoes={indicacoes} zerado={produtoEstoqueZerado} produto={produto} doenca={criterio} onUsar={escolherProduto} />
          )}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
            <MobCampo label="Quantidade (dose)">
              <input type="number" inputMode="decimal" className="mob-input" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} placeholder="0" />
            </MobCampo>
            <MobCampo label="Unidade">
              <select className="mob-input" value={unidade} onChange={(e) => setUnidade(e.target.value)}>
                {!unidade && <option value="">—</option>}
                {compativeis.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </MobCampo>
          </div>
          <MobCampo label="Via de aplicação">
            <select className="mob-input" value={via} onChange={(e) => setVia(e.target.value)}>
              <option value="">Selecione…</option>
              {VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </MobCampo>
        </>
      )}

      <MobCampo label="Responsável">
        <select className="mob-input" value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
          <option value="">Selecione…</option>
          {nomesResponsaveis.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </MobCampo>
      {tipo === "aplicacao" && (
        <MobCampo label="Já foi aplicado?">
          {data > hoje() ? (
            <p style={{ fontSize: "0.82rem", color: "var(--mob-ambar)" }}>Data futura — será <strong>programado na Agenda</strong> (não baixa estoque).</p>
          ) : (
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <MobPill ativa={aplicado} onClick={() => setAplicado(true)}>Sim (aplicar agora)</MobPill>
              <MobPill ativa={!aplicado} onClick={() => setAplicado(false)}>Não (programar)</MobPill>
            </div>
          )}
        </MobCampo>
      )}
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}

// Aviso de substituto inteligente: produto escolhido está com estoque
// baixo/zerado e a doença filtrada tem outras opções indicadas — mesma regra
// do site, layout mobile (Mob*). "Disponível agora" troca o produto do form
// com um toque; "Precisa comprar" é só informativo.
function SubstitutoBanner({ indicacoes, zerado, produto, doenca, onUsar }: {
  indicacoes: OpcaoIndicacaoDoenca[]; zerado: boolean; produto: string; doenca: string; onUsar: (nome: string) => void;
}) {
  const disponiveis = indicacoes.filter((o) => o.status_estoque === "ok");
  const precisaComprar = indicacoes.filter((o) => o.status_estoque !== "ok");
  return (
    <MobCard style={{ marginBottom: "0.9rem", border: "1px solid var(--mob-ambar)" }}>
      <div style={{ fontSize: "0.84rem", fontWeight: 700, color: "var(--mob-ambar)", marginBottom: "0.7rem" }}>
        {`Estoque ${zerado ? "zerado" : "baixo"} de "${produto}" — substitutos indicados para ${doenca}:`}
      </div>
      {disponiveis.length > 0 && (
        <div style={{ marginBottom: precisaComprar.length ? "0.8rem" : 0 }}>
          <div style={{ fontSize: "0.76rem", fontWeight: 700, color: "var(--mob-verde)", marginBottom: "0.4rem" }}>Disponível agora</div>
          {disponiveis.map((o) => (
            <div key={o.principio_ativo_id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem", padding: "0.4rem 0", borderTop: "1px solid var(--mob-border)" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: "0.88rem" }}>{o.nome}</div>
                {o.marcas.length > 0 && <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)" }}>{o.marcas.join(", ")}</div>}
              </div>
              <button type="button" onClick={() => onUsar(o.marcas[0] || o.nome)}
                style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--mob-verde-fg)", background: "var(--mob-verde)", border: "none", borderRadius: "var(--r-app)", padding: "0.4rem 0.75rem", cursor: "pointer", flexShrink: 0 }}>
                Usar
              </button>
            </div>
          ))}
        </div>
      )}
      {precisaComprar.length > 0 && (
        <div>
          <div style={{ fontSize: "0.76rem", fontWeight: 700, color: "var(--mob-ambar)", marginBottom: "0.4rem" }}>Precisa comprar</div>
          {precisaComprar.map((o) => (
            <div key={o.principio_ativo_id} style={{ padding: "0.4rem 0", borderTop: "1px solid var(--mob-border)" }}>
              <div style={{ fontWeight: 700, fontSize: "0.88rem" }}>{o.nome}</div>
              {o.marcas.length > 0 && <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)" }}>{o.marcas.join(", ")}</div>}
            </div>
          ))}
        </div>
      )}
    </MobCard>
  );
}

// ── Preventiva > BST — só leitura, GET /agenda/ ──────────────────────────────
function PreventivoBst() {
  const agenda = useCache<any>("agenda_bst_lancar", () => fetchAgenda(), null);
  const dados = agenda.dados;
  const aptos = dados?.bst_elegiveis || [];
  const nuncaAplicados = dados?.bst_nunca_aplicados || [];
  const excl = dados?.bst_excluidos || [];

  function Lista({ titulo, lista, cor }: { titulo: string; lista: any[]; cor: string }) {
    return (
      <div style={{ marginBottom: "1.1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontWeight: 700, fontSize: "0.9rem", color: cor, marginBottom: "0.5rem" }}>
          <Droplets size={16} /> {titulo} ({lista.length})
        </div>
        {!lista.length ? (
          <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhuma vaca.</p>
        ) : (
          lista.map((b: any) => (
            <MobCard key={b.numero_matriz} style={{ marginBottom: "0.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontWeight: 700, display: "flex", alignItems: "center", gap: "0.35rem" }}>
                  {b.requer_reanalise && (
                    <span title="Retirada do BST — revisar antes de incluir de novo" style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--mob-ambar)" }} />
                  )}
                  {b.numero_matriz}
                </span>
                <span style={{ color: "var(--mob-muted)", fontSize: "0.82rem" }}>Lote {b.grupo || "—"}</span>
              </div>
              <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>
                DEL atual: {b.del_atual ?? "—"} · DEL projetado: {b.del_projetado ?? "—"}
                {b.requer_reanalise ? ` · ${b.motivo_exclusao || "Revisar"}` : ""}
              </div>
            </MobCard>
          ))
        )}
      </div>
    );
  }

  return (
    <>
      <p style={{ fontSize: "0.85rem", color: "var(--mob-muted)", marginBottom: "0.9rem" }}>
        BST (somatotropina bovina) — vacas aptas e excluídas do dia. Próxima visita BST:{" "}
        <strong>{dados?.proxima_visita_bst ? formatDate(dados.proxima_visita_bst) : "—"}</strong>.
      </p>
      <Lista titulo="Aptas" lista={aptos} cor="var(--mob-verde)" />
      <Lista titulo="Incluir no próximo BST" lista={nuncaAplicados} cor="var(--mob-azul)" />
      <Lista titulo="Excluídas" lista={excl} cor="var(--mob-ambar)" />
    </>
  );
}
