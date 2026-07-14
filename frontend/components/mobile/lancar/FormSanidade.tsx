"use client";
// Sub-tela SANIDADE: espelha a estrutura do site — duas modalidades,
// Curativa (aplicação avulsa de remédio ou protocolo sanitário) e Preventiva
// (aplicação de vacina/exame/tratamento, calendário sanitário e BST).
// Endpoints: POST /sanidade/aplicacoes | POST /sanidade/protocolos/lancamentos |
// POST /sanidade/calendario/cadastrar-preventivo | POST /sanidade/calendario |
// GET /agenda/ (BST).
import { useEffect, useMemo, useState } from "react";
import { Syringe, ClipboardList, Bandage, ShieldCheck, CalendarClock, Droplets } from "lucide-react";
import { MobCampo, MobAviso, MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchEstoque, fetchProtocolosSanitarios, fetchMedicamentos, fetchPrincipiosAtivos, fetchDoencas, fetchEventosSanitarios, fetchAgenda, formatDate } from "@/lib/api";
import { RESPONSAVEIS, VIAS_APLICACAO } from "@/lib/constants";
import {
  type Animal, type EstoqueItem, useCache, useEnvio, hoje,
  MobPill, LinhaPills, SeletorAnimal, unidadesCompativeis, GradeAcoes,
} from "./comum";

type Protocolo = { id: number; nome: string; eh_mastite?: boolean };
type EventoPrev = { id: number; nome: string; categoria_preventiva: string | null };
const CLASSIF_MASTITE = ["clinica", "subclinica", "ambiental"];

type Modalidade = "curativa" | "preventiva";
type TipoCurativa = "aplicacao" | "protocolo";
type TipoPreventiva = "aplicacao" | "calendario" | "bst";

const TITULOS_PREV: Record<TipoPreventiva, string> = {
  aplicacao: "Aplicação preventiva", calendario: "Calendário sanitário", bst: "BST",
};

export function FormSanidade({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const estoque = useCache<EstoqueItem[]>("estoque_itens", () => fetchEstoque().then((d) => d.itens as EstoqueItem[]), []);

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
        {tipoPrev === "aplicacao" && <PreventivoAplicacao animais={animais} animalFixado={animalFixado} />}
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
function CurativaForm({ tipo, animais, animalFixado, estoque }: { tipo: TipoCurativa; animais: Animal[]; animalFixado: string | null; estoque: EstoqueItem[] }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const protocolos = useCache<Protocolo[]>("protocolos_sanitarios", () => fetchProtocolosSanitarios() as Promise<Protocolo[]>, []);

  const [modo, setModo] = useState<"animal" | "lote">("animal");
  const [animal, setAnimal] = useState(animalFixado || "");
  const [lote, setLote] = useState("");
  const [data, setData] = useState(hoje());
  const [produto, setProduto] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [unidade, setUnidade] = useState("");
  const [via, setVia] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [aplicado, setAplicado] = useState(true);
  // Filtrar o medicamento por doença / princípio ativo (abre só os que casam).
  const [filtrarPor, setFiltrarPor] = useState<"todos" | "principio_ativo" | "doenca">("todos");
  const [criterio, setCriterio] = useState("");
  const [principiosNomes, setPrincipiosNomes] = useState<string[]>([]);
  const [doencasNomes, setDoencasNomes] = useState<string[]>([]);
  const [medicamentosFiltrados, setMedicamentosFiltrados] = useState<string[] | null>(null);
  useEffect(() => {
    fetchPrincipiosAtivos().then((d: any[]) => setPrincipiosNomes(d.map((p) => p.nome))).catch(() => {});
    fetchDoencas().then((d: any[]) => setDoencasNomes(d.map((x) => x.nome))).catch(() => {});
  }, []);
  useEffect(() => {
    if (filtrarPor === "todos" || !criterio) { setMedicamentosFiltrados(null); return; }
    const filtro = filtrarPor === "principio_ativo" ? { principio_ativo: criterio } : { doenca: criterio };
    fetchMedicamentos(filtro).then((m: any[]) => setMedicamentosFiltrados(m.map((x) => x.nome))).catch(() => setMedicamentosFiltrados([]));
  }, [filtrarPor, criterio]);
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

  const produtos = useMemo(() => {
    const base = medicamentosFiltrados ?? estoque.map((e) => e.nome);
    return [...base].sort();
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
            <select className="mob-input" value={produto} onChange={(e) => escolherProduto(e.target.value)} disabled={filtrarPor !== "todos" && !criterio}>
              <option value="">Selecione o produto…</option>
              {produtos.map((nome) => {
                const est = estoque.find((e) => e.nome === nome);
                return <option key={nome} value={nome}>{nome}{est?.quantidade != null ? ` (${est.quantidade} ${est.unidade || ""})` : ""}</option>;
              })}
            </select>
          </MobCampo>
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
          {RESPONSAVEIS.map((r) => <option key={r} value={r}>{r}</option>)}
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

// ── Preventiva > Aplicação — POST /sanidade/calendario/cadastrar-preventivo ──
function PreventivoAplicacao({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const [eventos, setEventos] = useState<EventoPrev[]>([]);
  const [eventoId, setEventoId] = useState("");
  const [data, setData] = useState(hoje());
  const [freqValor, setFreqValor] = useState("1");
  const [freqUnidade, setFreqUnidade] = useState("meses");
  const [veterinario, setVeterinario] = useState("");
  const [modo, setModo] = useState<"animal" | "lote">("animal");
  const [animal, setAnimal] = useState(animalFixado || "");
  const [lote, setLote] = useState("");

  useEffect(() => { fetchEventosSanitarios().then((d: any[]) => setEventos(d.filter((e) => e.ativo))).catch(() => {}); }, []);

  const evento = eventos.find((e) => String(e.id) === eventoId);
  const ehExame = evento?.categoria_preventiva === "exame";

  const lotes = useMemo(() => {
    const set = new Set<string>();
    animais.forEach((a) => { if (a.grupo_primario) set.add(a.grupo_primario); });
    return Array.from(set).sort();
  }, [animais]);

  const alvoAnimais = () => modo === "animal" ? (animal ? [animal] : []) : animais.filter((a) => a.grupo_primario === lote).map((a) => a.numero);

  function salvar() {
    const alvo = alvoAnimais();
    if (!eventoId) return erroValidacao("Selecione o evento preventivo.");
    if (!data) return erroValidacao("Informe a data de referência.");
    if (!alvo.length) return erroValidacao(modo === "animal" ? "Selecione o animal." : "Selecione o lote.");
    enviar(
      "/sanidade/calendario/cadastrar-preventivo",
      {
        evento_sanitario_id: Number(eventoId), categoria_alvo: modo === "lote" ? lote : undefined, data_evento: data,
        frequencia_valor: Number(freqValor) || 1, frequencia_unidade: freqUnidade,
        animais: alvo, aplicar: !ehExame, veterinario: veterinario || undefined,
      },
      `Preventivo ${evento?.nome || ""} — ${modo === "animal" ? `animal ${animal}` : `lote ${lote}`}`,
      () => { setEventoId(""); setVeterinario(""); },
    );
  }

  return (
    <>
      <MobCampo label="Evento preventivo">
        <select className="mob-input" value={eventoId} onChange={(e) => setEventoId(e.target.value)}>
          <option value="">Selecione…</option>
          {eventos.map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}</option>)}
        </select>
      </MobCampo>
      <MobCampo label="Data de referência">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
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
      {ehExame && (
        <MobCampo label="Veterinário (exame)">
          <input className="mob-input" value={veterinario} onChange={(e) => setVeterinario(e.target.value)} placeholder="ex.: Dr. Carlos" />
        </MobCampo>
      )}

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

      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}

// ── Preventiva > Calendário sanitário — POST /sanidade/calendario ───────────
function PreventivoCalendario({ estoque }: { estoque: EstoqueItem[] }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const [eventos, setEventos] = useState<EventoPrev[]>([]);
  const [eventoId, setEventoId] = useState("");
  const [categoriaAlvo, setCategoriaAlvo] = useState("");
  const [produto, setProduto] = useState("");
  const [dosagem, setDosagem] = useState("");
  const [unidade, setUnidade] = useState("");
  const [veterinario, setVeterinario] = useState("");
  const [freqValor, setFreqValor] = useState("1");
  const [freqUnidade, setFreqUnidade] = useState("meses");
  const [data, setData] = useState(hoje());
  const [obs, setObs] = useState("");

  useEffect(() => { fetchEventosSanitarios().then((d: any[]) => setEventos(d.filter((e) => e.ativo))).catch(() => {}); }, []);
  const evento = eventos.find((e) => String(e.id) === eventoId);
  const ehExame = evento?.categoria_preventiva === "exame";
  const compativeis = useMemo(() => unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade), [estoque, produto]);

  function salvar() {
    if (!eventoId) return erroValidacao("Selecione o evento sanitário.");
    if (!data) return erroValidacao("Informe a data do evento.");
    enviar(
      "/sanidade/calendario",
      {
        evento_sanitario_id: Number(eventoId), categoria_alvo: categoriaAlvo || undefined,
        produto: ehExame ? undefined : (produto || undefined), dosagem: ehExame ? undefined : (dosagem || undefined),
        unidade: ehExame ? undefined : (unidade || undefined), veterinario: veterinario || undefined,
        frequencia_valor: Number(freqValor) || 1, frequencia_unidade: freqUnidade, data_evento: data, observacao: obs || undefined,
      },
      `Regra do calendário — ${evento?.nome || ""}`,
      () => { setEventoId(""); setCategoriaAlvo(""); setProduto(""); setDosagem(""); setUnidade(""); setVeterinario(""); setObs(""); },
    );
  }

  return (
    <>
      <MobCampo label="Evento sanitário">
        <select className="mob-input" value={eventoId} onChange={(e) => setEventoId(e.target.value)}>
          <option value="">Selecione…</option>
          {eventos.map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}</option>)}
        </select>
      </MobCampo>
      <MobCampo label="Categoria alvo (opcional)">
        <input className="mob-input" value={categoriaAlvo} onChange={(e) => setCategoriaAlvo(e.target.value)} placeholder="ex.: Bezerras (3 a 8 meses)" />
      </MobCampo>
      {ehExame ? (
        <MobCampo label="Veterinário (exame)">
          <input className="mob-input" value={veterinario} onChange={(e) => setVeterinario(e.target.value)} placeholder="ex.: Dr. Carlos" />
        </MobCampo>
      ) : (
        <>
          <MobCampo label="Produto">
            <input className="mob-input" list="produtos-calendario-mob" value={produto} onChange={(e) => setProduto(e.target.value)} placeholder="ex.: VACINA RB 51 - FR 25 DS" />
            <datalist id="produtos-calendario-mob">{estoque.map((e) => <option key={e.nome} value={e.nome} />)}</datalist>
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
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
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
                <span style={{ fontWeight: 700 }}>{b.numero_matriz}</span>
                <span style={{ color: "var(--mob-muted)", fontSize: "0.82rem" }}>Lote {b.grupo || "—"}</span>
              </div>
              <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>DEL: {b.del_dias ?? "—"}</div>
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
      <Lista titulo="Nunca aplicadas" lista={nuncaAplicados} cor="var(--mob-azul)" />
      <Lista titulo="Excluídas" lista={excl} cor="var(--mob-ambar)" />
    </>
  );
}
