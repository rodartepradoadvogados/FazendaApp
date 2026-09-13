"use client";
// Sub-tela SANIDADE: espelha a estrutura do site — duas modalidades,
// Curativa (aplicação avulsa de remédio ou protocolo sanitário) e Preventiva
// (aplicação de vacina/exame/tratamento, calendário sanitário e BST).
// Endpoints: POST /sanidade/aplicacoes | POST /sanidade/protocolos/lancamentos |
// POST /sanidade/calendario/cadastrar-preventivo | POST /sanidade/calendario |
// GET /agenda/ (BST).
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Syringe, ClipboardList, Bandage, ShieldCheck, CalendarClock, Droplets } from "lucide-react";
import { MobCampo, MobAviso, MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchEstoque, fetchProtocolosSanitarios, fetchMedicamentos, fetchPrincipiosAtivos, fetchDoencas, fetchEventosSanitarios, fetchAgenda, fetchCategoriasManejo, fetchPessoas, fetchRelatorioEventosVida, formatDate, fetchIndicacoesDoenca, type OpcaoIndicacaoDoenca } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";
import { EstoquePicker } from "@/components/EstoquePicker";
import { VIAS_APLICACAO } from "@/lib/constants";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import {
  type Animal, type EstoqueItem, useCache, useEnvio, useRascunho, hoje,
  MobPill, LinhaPills, SeletorAnimal, unidadesCompativeis, GradeAcoes, RascunhoAviso,
} from "./comum";

type Protocolo = { id: number; nome: string; eh_mastite?: boolean };
type EventoPrev = {
  id: number; nome: string; categoria_preventiva: string | null;
  produto_padrao?: string | null; dose_padrao?: number | null; unidade_padrao?: string | null;
  // Presentes só quando o evento é agendado por evento de vida (gatilho) —
  // decide se a modalidade "Na janela" aparece (ver PreventivoAplicacao).
  tipo_agendamento?: string; gatilho?: string | null;
  veterinario_padrao_pessoa_id?: number | null;
};
const CLASSIF_MASTITE = ["clinica", "subclinica", "ambiental"];
// Separador usado para guardar mais de uma categoria-alvo no mesmo campo de
// texto único do banco — mesmo padrão do site (ver SEP_CATEGORIAS em app/lancamentos/page.tsx).
const SEP_CATEGORIAS = ", ";

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
type TipoPreventiva = "aplicacao" | "calendario" | "bst";

const TITULOS_PREV: Record<TipoPreventiva, string> = {
  aplicacao: "Aplicação preventiva", calendario: "Calendário sanitário", bst: "BST",
};

export function FormSanidade({ animais, animalFixado, deepLinkEventoId }: {
  animais: Animal[]; animalFixado: string | null;
  /** Vindo de "Ver quem está na janela" (Menu > Calendário Sanitário) — pula
   *  direto para Preventiva > Aplicação, evento e modo "Na janela" já
   *  escolhidos, em vez de obrigar o usuário a repetir os 2 toques
   *  (Preventiva > Aplicação) e escolher o evento de novo. */
  deepLinkEventoId?: string | null;
}) {
  const estoque = useCache<EstoqueItem[]>("estoque_itens", () => fetchEstoque().then((d) => d.itens as EstoqueItem[]), []);

  const [modalidade, setModalidade] = useState<Modalidade | null>(deepLinkEventoId ? "preventiva" : null);
  const [tipo, setTipo] = useState<TipoCurativa | null>(null);
  const [tipoPrev, setTipoPrev] = useState<TipoPreventiva | null>(deepLinkEventoId ? "aplicacao" : null);

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
              { id: "aplicacao", label: "Aplicação", icone: <Syringe size={28} />, cor: "var(--mob-azul)" },
              { id: "calendario", label: "Calendário sanitário", icone: <CalendarClock size={28} />, cor: "var(--mob-laranja)" },
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
        {tipoPrev === "aplicacao" && (
          <PreventivoAplicacao
            animais={animais} animalFixado={animalFixado} estoque={estoque.dados}
            eventoIdInicial={deepLinkEventoId || undefined}
            modoInicial={deepLinkEventoId ? "janela" : undefined}
          />
        )}
        {tipoPrev === "calendario" && <PreventivoCalendario estoque={estoque.dados} />}
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

// ── Preventiva > Aplicação — POST /sanidade/calendario/cadastrar-preventivo ──
function PreventivoAplicacao({ animais, animalFixado, estoque, eventoIdInicial, modoInicial }: {
  animais: Animal[]; animalFixado: string | null; estoque: EstoqueItem[];
  /** Deep-link vindo de "Ver quem está na janela" (Calendário Sanitário). */
  eventoIdInicial?: string; modoInicial?: "janela";
}) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const [eventos, setEventos] = useState<EventoPrev[]>([]);
  const [eventoId, setEventoId] = useState(eventoIdInicial || "");
  const [data, setData] = useState(hoje());
  const [hora, setHora] = useState("");
  const [freqValor, setFreqValor] = useState("1");
  const [freqUnidade, setFreqUnidade] = useState("meses");
  const [veterinario, setVeterinario] = useState("");
  const rascunhoAlvo = useRascunho<{ modo: "animal" | "lote" | "janela"; animal: string; lote: string }>(
    "sanidade_preventiva_alvo", { modo: modoInicial || "animal", animal: animalFixado || "", lote: "" },
  );
  const { modo, animal, lote } = rascunhoAlvo.valor;
  const atualizarAlvo = (patch: Partial<{ modo: "animal" | "lote" | "janela"; animal: string; lote: string }>) =>
    rascunhoAlvo.setValor((atual) => ({ ...atual, ...patch }));
  const setModo = (v: "animal" | "lote" | "janela") => atualizarAlvo({ modo: v });
  const setAnimal = (v: string) => atualizarAlvo({ animal: v });
  const setLote = (v: string) => atualizarAlvo({ lote: v });
  // O deep-link "Ver quem está na janela" (Calendário Sanitário) precisa
  // vencer um rascunho salvo de uma visita anterior — senão o usuário cai
  // de novo no modo/alvo antigo em vez do evento que acabou de escolher.
  useEffect(() => {
    if (modoInicial === "janela") setModo("janela");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modoInicial]);
  // Medicamento aplicado — sempre pedido para vacina/tratamento (não para
  // exame); pré-preenche com o padrão do evento, mas o usuário pode trocar.
  const [produto, setProduto] = useState("");
  const [dose, setDose] = useState("");
  const [unidade, setUnidade] = useState("");

  // "Na janela" (pedido do usuário, 10/09/2026) — mesmo painel do site:
  // lista quem está na janela de aplicação DESTE evento, marca por padrão
  // quem já entrou nela, deixa ajustar a seleção, e pede o veterinário (por
  // Pessoa cadastrada, não texto livre) na hora de agendar.
  const [pessoas, setPessoas] = useState<any[]>([]);
  const [veterinarioId, setVeterinarioId] = useState("");
  const [janela, setJanela] = useState<{ animais: { numero_matriz: string; nome: string | null; situacao_janela?: string; dias_para_fechar_janela?: number | null }[] } | null>(null);
  const [carregandoJanela, setCarregandoJanela] = useState(false);
  const [erroJanela, setErroJanela] = useState<string | null>(null);
  const [selJanela, setSelJanela] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchComCache<EventoPrev[]>("sanidade_eventos_sanitarios_ativos", () => fetchEventosSanitarios().then((d: any[]) => d.filter((e) => e.ativo)))
      .then(({ dados }) => setEventos(dados || []));
  }, []);
  useEffect(() => { fetchPessoas().then(setPessoas).catch(() => setPessoas([])); }, []);
  const veterinarios = useMemo(
    () => pessoas.filter((p) => p.ativo !== false && (p.tipos || []).some((t: string) => ["Veterinário", "Zootecnista"].includes(t)))
      .sort((a, b) => (a.nome || "").localeCompare(b.nome || "")),
    [pessoas]
  );

  const evento = eventos.find((e) => String(e.id) === eventoId);
  const ehExame = evento?.categoria_preventiva === "exame";
  // Só evento agendado por gatilho (evento de vida) tem janela de aplicação —
  // mesmo critério do relatório que alimenta este painel.
  const elegivelJanela = evento?.tipo_agendamento === "evento" && !!evento?.gatilho;
  const compativeis = useMemo(() => unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade), [estoque, produto]);

  useEffect(() => {
    const nomePadrao = evento?.produto_padrao || "";
    const comp = unidadesCompativeis(nomePadrao ? estoque.find((e) => e.nome === nomePadrao)?.unidade : undefined);
    setProduto(nomePadrao);
    setDose(evento?.dose_padrao != null ? String(evento.dose_padrao) : "");
    setUnidade(evento?.unidade_padrao && comp.includes(evento.unidade_padrao) ? evento.unidade_padrao : (comp[0] || ""));
    if (evento?.veterinario_padrao_pessoa_id) setVeterinarioId(String(evento.veterinario_padrao_pessoa_id));
    // `eventos` entra nas deps (além de `eventoId`) por causa do deep-link
    // ("Ver quem está na janela"): `eventoId` já chega pronto ANTES da lista
    // de eventos terminar de carregar, e sem reagir à chegada de `eventos`
    // este efeito rodaria uma vez com `evento` ainda undefined e nunca mais —
    // produto/dose/veterinário do deep-link ficariam vazios para sempre.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventoId, eventos]);

  // Volta pro modo "animal" se o evento escolhido não tem gatilho (não faz
  // sentido oferecer "Na janela" pra evento agendado por época) — mesmo
  // motivo de `eventos` entrar nas deps acima.
  useEffect(() => {
    if (!eventos.length) return;
    if (modo === "janela" && !elegivelJanela) setModo("animal");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventoId, eventos]);

  useEffect(() => {
    if (modo !== "janela" || !eventoId) { setJanela(null); return; }
    let vivo = true;
    setCarregandoJanela(true); setErroJanela(null);
    fetchRelatorioEventosVida({ eventoSanitarioId: Number(eventoId) })
      .then((r: any) => {
        if (!vivo) return;
        setJanela(r);
        setSelJanela(new Set((r.animais || []).filter((a: any) => !a.situacao_janela || a.situacao_janela === "na_janela").map((a: any) => a.numero_matriz)));
      })
      .catch((e) => { if (vivo) setErroJanela(e.message); })
      .finally(() => { if (vivo) setCarregandoJanela(false); });
    return () => { vivo = false; };
  }, [modo, eventoId]);

  function escolherProduto(nome: string) {
    setProduto(nome);
    const comp = unidadesCompativeis(estoque.find((e) => e.nome === nome)?.unidade);
    setUnidade((u) => (comp.includes(u) ? u : (comp[0] || "")));
  }

  const lotes = useMemo(() => {
    const set = new Set<string>();
    animais.forEach((a) => { if (a.grupo_primario) set.add(a.grupo_primario); });
    return Array.from(set).sort();
  }, [animais]);

  const toggleJanela = (n: string) => setSelJanela((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const todosMarcadosJanela = !!janela?.animais.length && janela.animais.every((a) => selJanela.has(a.numero_matriz));
  const alternarTodosJanela = () => setSelJanela(todosMarcadosJanela ? new Set() : new Set((janela?.animais || []).map((a) => a.numero_matriz)));

  const alvoAnimais = () => modo === "animal" ? (animal ? [animal] : [])
    : modo === "lote" ? animais.filter((a) => a.grupo_primario === lote).map((a) => a.numero)
    : Array.from(selJanela);

  function salvar() {
    const alvo = alvoAnimais();
    if (!eventoId) return erroValidacao("Selecione o evento preventivo.");
    if (!data) return erroValidacao("Informe a data de referência.");
    if (!alvo.length) return erroValidacao(modo === "animal" ? "Selecione o animal." : modo === "lote" ? "Selecione o lote." : "Selecione ao menos um animal na janela.");
    if (!ehExame) {
      if (!produto) return erroValidacao("Selecione o medicamento aplicado.");
      if (!(Number(dose) > 0)) return erroValidacao("Informe a dose.");
      if (!unidade) return erroValidacao("Selecione a unidade.");
    }
    const vetJanela = veterinarios.find((p) => String(p.id) === veterinarioId);
    enviar(
      "/sanidade/calendario/cadastrar-preventivo",
      {
        evento_sanitario_id: Number(eventoId), categoria_alvo: modo === "lote" ? lote : undefined, data_evento: data,
        // "Na janela" não cria regra recorrente de época — o evento já é
        // regido pelo próprio gatilho/janela cadastrados.
        frequencia_valor: modo === "janela" ? 0 : (Number(freqValor) || 1), frequencia_unidade: freqUnidade,
        animais: alvo, aplicar: !ehExame,
        veterinario: modo === "janela" ? (vetJanela?.nome || undefined) : (veterinario || undefined),
        observacao: modo === "janela" && hora ? `Horário: ${hora}` : undefined,
        produto: ehExame ? undefined : produto, dose: ehExame ? undefined : Number(dose), unidade: ehExame ? undefined : unidade,
      },
      `Preventivo ${evento?.nome || ""} — ${modo === "animal" ? `animal ${animal}` : modo === "lote" ? `lote ${lote}` : `${alvo.length} na janela`}`,
      () => { setEventoId(""); setVeterinario(""); setVeterinarioId(""); setSelJanela(new Set()); setHora(""); },
    );
  }

  return (
    <>
      <RascunhoAviso mostrar={rascunhoAlvo.salvo} />
      <MobCampo label="Evento preventivo">
        <select className="mob-input" value={eventoId} onChange={(e) => setEventoId(e.target.value)}>
          <option value="">Selecione…</option>
          {eventos.map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}</option>)}
        </select>
      </MobCampo>
      <MobCampo label="Data de referência">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      {modo !== "janela" && (
        <MobCampo label="Repetir a cada">
          <div style={{ display: "flex", gap: "0.6rem" }}>
            <input type="number" inputMode="numeric" className="mob-input" style={{ flex: 1 }} value={freqValor} onChange={(e) => setFreqValor(e.target.value)} />
            <select className="mob-input" style={{ flex: 1 }} value={freqUnidade} onChange={(e) => setFreqUnidade(e.target.value)}>
              <option value="dias">dia(s)</option>
              <option value="meses">mês(es)</option>
              <option value="anos">ano(s)</option>
            </select>
          </div>
        </MobCampo>
      )}
      {ehExame ? (
        modo !== "janela" && (
          <MobCampo label="Veterinário (exame)">
            <input className="mob-input" value={veterinario} onChange={(e) => setVeterinario(e.target.value)} placeholder="ex.: Dr. Carlos" />
          </MobCampo>
        )
      ) : (
        <>
          <MobCampo label="Medicamento aplicado">
            <EstoquePicker itens={estoque} value={produto} onChange={escolherProduto} placeholder="Selecione o produto…" incluirNaoEstocaveis />
          </MobCampo>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
            <MobCampo label="Dose">
              <input type="number" inputMode="decimal" className="mob-input" value={dose} onChange={(e) => setDose(e.target.value)} placeholder="0" />
            </MobCampo>
            <MobCampo label="Unidade">
              <select className="mob-input" value={unidade} onChange={(e) => setUnidade(e.target.value)}>
                {!unidade && <option value="">—</option>}
                {compativeis.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </MobCampo>
          </div>
        </>
      )}

      <LinhaPills>
        <MobPill ativa={modo === "animal"} onClick={() => setModo("animal")}>Animal</MobPill>
        <MobPill ativa={modo === "lote"} onClick={() => setModo("lote")}>Lote</MobPill>
        {elegivelJanela && <MobPill ativa={modo === "janela"} onClick={() => setModo("janela")}>Na janela</MobPill>}
      </LinhaPills>
      {modo === "animal" && (
        <MobCampo label="Animal (nº / nome)">
          <SeletorAnimal animais={animais} valor={animal} onChange={setAnimal} placeholder="Buscar animal…" />
        </MobCampo>
      )}
      {modo === "lote" && (
        <MobCampo label="Lote">
          <select className="mob-input" value={lote} onChange={(e) => setLote(e.target.value)}>
            <option value="">Selecione o lote…</option>
            {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </MobCampo>
      )}
      {modo === "janela" && (
        <>
          {carregandoJanela && <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Carregando quem está na janela…</p>}
          {erroJanela && <MobAviso tipo="erro">{erroJanela}</MobAviso>}
          {janela && (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <span style={{ fontSize: "0.82rem", fontWeight: 700 }}>{selJanela.size} de {janela.animais.length} selecionado(s)</span>
                <button type="button" onClick={alternarTodosJanela}
                  style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--mob-dourado-2)", background: "none", border: "none", cursor: "pointer" }}>
                  {todosMarcadosJanela ? "Desmarcar todos" : "Marcar todos"}
                </button>
              </div>
              <div style={{ display: "grid", gap: "0.4rem", maxHeight: "40vh", overflowY: "auto", marginBottom: "0.8rem" }}>
                {janela.animais.map((a) => (
                  <label key={a.numero_matriz} className="mob-card" style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.6rem 0.8rem", cursor: "pointer" }}>
                    <input type="checkbox" checked={selJanela.has(a.numero_matriz)} onChange={() => toggleJanela(a.numero_matriz)} />
                    <span style={{ flex: 1 }}>
                      <strong>{a.numero_matriz}</strong>{a.nome ? ` · ${a.nome}` : ""}
                    </span>
                    {a.situacao_janela === "na_janela" && a.dias_para_fechar_janela != null && (
                      <span style={{ fontSize: "0.7rem", color: "var(--mob-dourado-2)" }}>fecha em {a.dias_para_fechar_janela}d</span>
                    )}
                  </label>
                ))}
                {!janela.animais.length && <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum animal encontrado.</p>}
              </div>
              <MobCampo label="Veterinário">
                <select className="mob-input" value={veterinarioId} onChange={(e) => setVeterinarioId(e.target.value)}>
                  <option value="">Opcional</option>
                  {veterinarios.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select>
              </MobCampo>
              <MobCampo label="Hora (opcional)">
                <input type="time" className="mob-input" value={hora} onChange={(e) => setHora(e.target.value)} />
              </MobCampo>
            </>
          )}
        </>
      )}

      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}

// ── Preventiva > Calendário sanitário — POST /sanidade/calendario ───────────
type DraftCalendarioSanitario = {
  eventoId: string; categoriaAlvoSel: string[]; produto: string; dosagem: string; unidade: string;
};

function PreventivoCalendario({ estoque }: { estoque: EstoqueItem[] }) {
  const router = useRouter();
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const [eventos, setEventos] = useState<EventoPrev[]>([]);
  const [categoriasVida, setCategoriasVida] = useState<string[]>([]);
  // Rascunho — evento + categoria-alvo + medicamento escolhidos, o mais
  // trabalhoso de reconstituir se o app for interrompido (docs/agents/
  // design-implementation.md §5, acabamento-de-campo.html).
  const rascunho = useRascunho<DraftCalendarioSanitario>("sanidade_calendario", {
    eventoId: "", categoriaAlvoSel: [], produto: "", dosagem: "", unidade: "",
  });
  const { eventoId, categoriaAlvoSel, produto, dosagem, unidade } = rascunho.valor;
  const atualizar = (patch: Partial<DraftCalendarioSanitario>) => rascunho.setValor((atual) => ({ ...atual, ...patch }));
  const setEventoId = (v: string) => atualizar({ eventoId: v });
  const setCategoriaAlvoSel = (v: string[]) => atualizar({ categoriaAlvoSel: v });
  const setProduto = (v: string) => atualizar({ produto: v });
  const setDosagem = (v: string) => atualizar({ dosagem: v });
  const setUnidade = (v: string) => atualizar({ unidade: v });
  const [veterinario, setVeterinario] = useState("");
  const [freqValor, setFreqValor] = useState("1");
  const [freqUnidade, setFreqUnidade] = useState("meses");
  const [data, setData] = useState(hoje());
  const [obs, setObs] = useState("");
  // Cronograma sanitário: em vez de cobrar aplicação na hora, o animal que
  // bate o critério entra numa lista de espera até agendar com o
  // veterinário ou confirmar aplicação própria (ver Agenda).
  const [usaCronograma, setUsaCronograma] = useState(false);
  // true só depois de um envio ONLINE bem-sucedido com o flag marcado — é
  // quando o 1º ciclo do cronograma já foi de fato criado no servidor (se
  // ficou na fila offline, o ciclo só nasce ao sincronizar, então não
  // adianta linkar ainda).
  const [cronogramaCriado, setCronogramaCriado] = useState(false);

  useEffect(() => {
    fetchComCache<EventoPrev[]>("sanidade_eventos_sanitarios_ativos", () => fetchEventosSanitarios().then((d: any[]) => d.filter((e) => e.ativo)))
      .then(({ dados }) => setEventos(dados || []));
  }, []);
  useEffect(() => {
    fetchComCache<string[]>("sanidade_categorias_manejo_ativas", () => fetchCategoriasManejo().then((d) => d.filter((c) => c.ativo).map((c) => c.nome)))
      .then(({ dados }) => setCategoriasVida(dados || []));
  }, []);
  const evento = eventos.find((e) => String(e.id) === eventoId);
  const ehExame = evento?.categoria_preventiva === "exame";
  const compativeis = useMemo(() => unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade), [estoque, produto]);

  function salvar() {
    if (!eventoId) return erroValidacao("Selecione o evento sanitário.");
    if (!data) return erroValidacao("Informe a data do evento.");
    const usouCronograma = usaCronograma;
    enviar(
      "/sanidade/calendario",
      {
        evento_sanitario_id: Number(eventoId), categoria_alvo: categoriaAlvoSel.length ? categoriaAlvoSel.join(SEP_CATEGORIAS) : undefined,
        produto: ehExame ? undefined : (produto || undefined), dosagem: ehExame ? undefined : (dosagem || undefined),
        unidade: ehExame ? undefined : (unidade || undefined), veterinario: veterinario || undefined,
        frequencia_valor: Number(freqValor) || 1, frequencia_unidade: freqUnidade, data_evento: data, observacao: obs || undefined,
        usa_cronograma: usaCronograma,
      },
      `Regra do calendário — ${evento?.nome || ""}`,
      () => {
        rascunho.limpar(); setVeterinario(""); setObs(""); setUsaCronograma(false);
        setCronogramaCriado(usouCronograma);
      },
    );
  }

  return (
    <>
      <RascunhoAviso mostrar={rascunho.salvo} />
      <MobCampo label="Evento sanitário">
        <select className="mob-input" value={eventoId} onChange={(e) => setEventoId(e.target.value)}>
          <option value="">Selecione…</option>
          {eventos.map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}</option>)}
        </select>
      </MobCampo>
      <MobCampo label="Categoria alvo (opcional)">
        <select className="mob-input" multiple value={categoriaAlvoSel}
          onChange={(e) => setCategoriaAlvoSel(Array.from(e.target.selectedOptions).map((o) => o.value))}
          style={{ height: "auto", minHeight: "6rem" }}>
          {categoriasVida.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </MobCampo>
      {ehExame ? (
        <MobCampo label="Veterinário (exame)">
          <input className="mob-input" value={veterinario} onChange={(e) => setVeterinario(e.target.value)} placeholder="ex.: Dr. Carlos" />
        </MobCampo>
      ) : (
        <>
          <MobCampo label="Produto">
            <EstoquePicker itens={estoque} value={produto} onChange={setProduto} incluirNaoEstocaveis />
          </MobCampo>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
            <MobCampo label="Dosagem">
              <input className="mob-input" value={dosagem} onChange={(e) => setDosagem(e.target.value)} placeholder="ex.: 2 mL a 5 mL" />
            </MobCampo>
            <MobCampo label="Unidade">
              <select className="mob-input" value={unidade} onChange={(e) => setUnidade(e.target.value)}>
                <option value="">—</option>
                {compativeis.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </MobCampo>
          </div>
        </>
      )}
      <MobCampo label="Repetir a cada">
        <div style={{ display: "flex", gap: "0.6rem" }}>
          <input type="number" inputMode="numeric" className="mob-input" style={{ flex: 1 }} value={freqValor} onChange={(e) => setFreqValor(e.target.value)} />
          <select className="mob-input" style={{ flex: 1 }} value={freqUnidade} onChange={(e) => setFreqUnidade(e.target.value)}>
            <option value="dias">dia(s)</option>
            <option value="meses">mês(es)</option>
            <option value="anos">ano(s)</option>
          </select>
        </div>
      </MobCampo>
      <MobCampo label="Data do evento (referência)">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <MobCampo label="Observação">
        <input className="mob-input" value={obs} onChange={(e) => setObs(e.target.value)} />
      </MobCampo>
      <label style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", margin: "0.2rem 0 0.9rem", fontSize: "0.82rem" }}>
        <input type="checkbox" checked={usaCronograma} onChange={(e) => setUsaCronograma(e.target.checked)} style={{ marginTop: "0.15rem" }} />
        <span>
          <strong>Usar cronograma sanitário</strong>
          <br />
          <span style={{ color: "var(--mob-muted)", fontSize: "0.76rem" }}>
            Em vez de cobrar aplicação na hora, o animal entra numa lista de espera até agendar com o veterinário ou confirmar aplicação própria.
          </span>
        </span>
      </label>
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
      {aviso?.tipo === "ok" && cronogramaCriado && (
        <button
          type="button" className="mob-btn"
          style={{ marginTop: "0.5rem", background: "var(--mob-vinho)" }}
          onClick={() => router.push("/app/menu#calendario-sanitario")}
        >
          Ver em Calendário Sanitário →
        </button>
      )}
    </>
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
