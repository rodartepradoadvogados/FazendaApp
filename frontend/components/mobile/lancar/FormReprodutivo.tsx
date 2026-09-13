"use client";
// Sub-tela REPRODUTIVO: quatro lançamentos em pílulas — Inseminação,
// Diagnóstico, Parto e Protocolo IATF (D0). Usa os mesmos endpoints do
// desktop (/reproducao/*).
import { useEffect, useMemo, useState } from "react";
import { Syringe, Stethoscope, Baby, CalendarClock } from "lucide-react";
import { MobCampo, MobAviso, MobVoltar, MobConfirmModal } from "@/components/mobile/ui";
import {
  fetchSemenDisponivel, fetchTouros, fetchAgendaVeterinario, sugestaoLoteEvento, criarMovimentacao,
  LISTAS_AGENDA_VETERINARIO, type SemenDisponivel, type Touro, type AgendaVetResposta,
} from "@/lib/api";
import { enviarOuEnfileirar, fetchComCache } from "@/lib/offline";
import { TouroPicker, type TouroPickerItem } from "@/components/TouroPicker";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import {
  type Animal, useCache, useEnvio, useRascunho, hoje, rotuloAnimal,
  BotoesEscolha, SeletorAnimal, GradeAcoes, MobPill, LinhaPills, RascunhoAviso,
} from "./comum";

type Aba = "inseminacao" | "diagnostico" | "parto" | "iatf";

const TITULOS_ABA: Record<Aba, string> = {
  inseminacao: "Inseminação", diagnostico: "Diagnóstico", parto: "Parto", iatf: "Protocolo IATF",
};

// Cronograma do protocolo IATF — mesmos hormônios do backend
// (fazenda/api/routers/reproducao.py → PASSOS_PROTOCOLO_IATF). O D0 é o que
// está sendo aplicado agora; as demais etapas entram na agenda.
const ETAPAS_IATF: { dia: number; hormonios: string }[] = [
  { dia: 0, hormonios: "Implante de progesterona + Benzoato de estradiol + Acetato de buserelina" },
  { dia: 7, hormonios: "Cloprostenol" },
  { dia: 9, hormonios: "Retirar implante + Cipionato de estradiol + Cloprostenol" },
  { dia: 11, hormonios: "Inseminação (IATF)" },
];

export function FormReprodutivo({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const [aba, setAba] = useState<Aba | null>(null);

  if (!aba) {
    return (
      <GradeAcoes
        opcoes={[
          { id: "inseminacao", label: "Inseminação", icone: <Syringe size={28} />, cor: "var(--mob-azul)" },
          { id: "diagnostico", label: "Diagnóstico", icone: <Stethoscope size={28} />, cor: "var(--mob-verde)" },
          { id: "parto", label: "Parto", icone: <Baby size={28} />, cor: "var(--mob-roxo)" },
          { id: "iatf", label: "Protocolo IATF", icone: <CalendarClock size={28} />, cor: "var(--mob-laranja)" },
        ]}
        onEscolher={(id) => setAba(id as Aba)}
      />
    );
  }

  return (
    <>
      <MobVoltar titulo={TITULOS_ABA[aba]} onVoltar={() => setAba(null)} />
      {aba === "inseminacao" && <Inseminacao animais={animais} animalFixado={animalFixado} />}
      {aba === "diagnostico" && <Diagnostico animais={animais} animalFixado={animalFixado} />}
      {aba === "parto" && <Parto animais={animais} animalFixado={animalFixado} />}
      {aba === "iatf" && <ProtocoloIatf animais={animais} animalFixado={animalFixado} />}
    </>
  );
}

// ── Inseminação → POST /reproducao/servico ───────────────────────────────────
// Categoria "fazenda" = cobertura por touro da fazenda (monta natural, sem
// sêmen estocado) — mesmo conceito do site (FormInseminacao.tsx). Precisa de
// tratamento à parte porque muda o que é enviado como tipo_servico: sem essa
// opção, toda cobertura lançada pelo app virava "IA" e debitava dose de sêmen
// que nunca foi usada de verdade (ver reproducao.py::registrar_servico).
function Inseminacao({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const semen = useCache<SemenDisponivel | null>("semen_disponivel", () => fetchSemenDisponivel(), null);
  // Rascunho da matriz escolhida — o passo mais trabalhoso (buscar/tocar o
  // animal certo); se o app for interrompido no meio, não se perde ao voltar
  // (docs/agents/design-implementation.md §5, acabamento-de-campo.html).
  const rascunho = useRascunho<string>("inseminacao_matriz", animalFixado || "");
  const matriz = rascunho.valor;
  const setMatriz = rascunho.setValor;
  const [data, setData] = useState(hoje());
  const [categoria, setCategoria] = useState<"convencional" | "sexado" | "fazenda">("convencional");
  const [touro, setTouro] = useState("");
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [catalogoTouros, setCatalogoTouros] = useState<Touro[]>([]);
  const ehFazenda = categoria === "fazenda";

  function salvar() {
    if (!matriz) return erroValidacao("Selecione a matriz.");
    if (!data) return erroValidacao("Informe a data da inseminação.");
    enviar(
      "/reproducao/servico",
      {
        numero_matriz: matriz, data_servico: data,
        tipo_servico: ehFazenda ? "Monta natural" : "IA",
        reprodutor: touro || undefined,
        tipo_semen: ehFazenda ? undefined : categoria,
      },
      `${ehFazenda ? "Monta natural" : "Inseminação"} — matriz ${matriz}${touro ? ` (${touro})` : ""}`,
      () => { setTouro(""); rascunho.limpar(); },
    );
  }

  const touros = semen.dados?.touros || [];
  const opcoes = touros.filter((t) => t.tipo === categoria).map((t) => t.nome);
  const itensCatalogo: TouroPickerItem[] = catalogoTouros.map((t) => ({ naab: t.naab, nome: t.nome || t.naab, central: t.central, raca: t.raca, tpi: t.tpi }));
  return (
    <>
      <RascunhoAviso mostrar={rascunho.salvo} />
      <MobCampo label="Matriz (nº / nome)">
        <SeletorAnimal animais={animais} valor={matriz} onChange={setMatriz} placeholder="Buscar matriz…" />
      </MobCampo>
      <MobCampo label="Data da inseminação/cobertura">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <MobCampo label="Categoria do touro / sêmen">
        <BotoesEscolha
          opcoes={[
            { valor: "convencional", label: "Convencional" }, { valor: "sexado", label: "Sexado" },
            { valor: "fazenda", label: "Touro da fazenda" },
          ]}
          valor={categoria} onChange={(v) => { setCategoria(v); setTouro(""); setIncluirSemEstoque(false); }}
        />
        {ehFazenda && <p style={{ fontSize: "0.72rem", color: "var(--mob-muted)", marginTop: "0.4rem" }}>Touro da fazenda — registrado como <strong>monta natural</strong>, sem debitar dose de sêmen.</p>}
      </MobCampo>
      <MobCampo label={ehFazenda ? "Touro (monta natural)" : "Touro / sêmen (opcional)"}>
        {!incluirSemEstoque || ehFazenda ? (
          <select className="mob-input" value={touro} onChange={(e) => setTouro(e.target.value)}>
            <option value="">{ehFazenda ? "Selecione o touro…" : "Selecione o sêmen…"}</option>
            {opcoes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        ) : (
          <TouroPicker className="mob-input" itens={itensCatalogo} value={touro} placeholder="Buscar touro no catálogo NAAB..."
            onChangeTexto={setTouro} onSelecionar={(t) => setTouro(t.nome)} />
        )}
        {!opcoes.length && <p style={{ fontSize: "0.72rem", color: "var(--mob-laranja)", marginTop: 2 }}>{ehFazenda ? "Nenhum touro da fazenda cadastrado." : `Nenhum sêmen ${categoria} em estoque.`}</p>}
        {!ehFazenda && (
          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginTop: "0.4rem", fontSize: "0.76rem", color: "var(--mob-muted)" }}>
            <input type="checkbox" checked={incluirSemEstoque}
              onChange={(e) => {
                setIncluirSemEstoque(e.target.checked);
                setTouro("");
                if (e.target.checked && !catalogoTouros.length) {
                  fetchComCache<Touro[]>("touros_naab", () => fetchTouros()).then(({ dados }) => { if (dados) setCatalogoTouros(dados); });
                }
              }} />
            Incluir touros sem estoque (catálogo NAAB)
          </label>
        )}
      </MobCampo>
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}

// ── Diagnóstico → POST /reproducao/diagnostico (1 chamada por matriz) ───────
// Positivo/Negativo em dois botões. Positivo grava "retoque": no manejo da
// fazenda o 1º toque positivo agenda a reconfirmação (2º exame) na data certa
// — mesmo comportamento do lançamento pelo site. Negativo grava "negativo".
// Seleção por animal (avulso, pode escolher vários), lote(s) ou pela própria
// Agenda do veterinário — mesmas 3 formas do site, para ajudar a organizar o
// manejo no curral.
function Diagnostico({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, setAviso, enviando, erroValidacao } = useEnvio();
  const { porNumero, rotuloDe } = useEstadosReprodutivos();
  // Servidas (inseminadas ou prenhes a reconfirmar) — estado ao vivo. Enquanto
  // ele não chegou (ou a requisição falhou) cai no texto do CSV: melhor um
  // filtro desatualizado do que um formulário sem nenhum animal.
  const servidas = useMemo(() => {
    if (!porNumero.size) return animais.filter((a) => a.sit_rep === "Ins." || a.sit_rep === "Ges.");
    return animais.filter((a) => {
      const estado = porNumero.get(a.numero)?.estado;
      return estado === "inseminada" || estado === "gestante";
    });
  }, [animais, porNumero]);

  const [vinculo, setVinculo] = useState<"animal" | "lote" | "agenda">("animal");
  // Rascunho da lista de matrizes — construir essa lista (buscar/tocar cada
  // animal, ou marcar lote/categoria) é o passo mais trabalhoso daqui; se o
  // app for interrompido, não se perde ao voltar
  // (docs/agents/design-implementation.md §5, acabamento-de-campo.html).
  const rascunho = useRascunho<string[]>("diagnostico_matrizes", animalFixado ? [animalFixado] : []);
  const matrizes = rascunho.valor;
  const setMatrizes = rascunho.setValor;
  function adicionar(numero: string) {
    setMatrizes((atual) => (atual.includes(numero) ? atual : [...atual, numero]));
  }
  function remover(numero: string) {
    setMatrizes((atual) => atual.filter((n) => n !== numero));
  }

  // Lote(s): pílulas com os lotes das servidas — ao (des)marcar, resseeda a
  // lista de matrizes com a união dos animais dos lotes marcados (removível
  // depois, animal a animal, nas pílulas abaixo).
  const [lotesSelecionados, setLotesSelecionados] = useState<string[]>([]);
  const lotesServidas = useMemo(
    () => Array.from(new Set(servidas.map((a) => a.grupo_primario).filter((g): g is string => !!g))).sort(),
    [servidas]
  );
  const numerosDoLote = useMemo(() => {
    const s = new Set(lotesSelecionados);
    return servidas.filter((a) => a.grupo_primario && s.has(a.grupo_primario)).map((a) => a.numero);
  }, [servidas, lotesSelecionados]);
  useEffect(() => {
    if (vinculo === "lote") setMatrizes(numerosDoLote);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numerosDoLote.join("|")]);

  // Agenda do veterinário: busca sob demanda e resseeda a lista de matrizes
  // com a união das categorias marcadas — mesma classificação do roteiro do dia.
  const [agendaVet, setAgendaVet] = useState<AgendaVetResposta | null>(null);
  const [agendaCarregando, setAgendaCarregando] = useState(false);
  const [categoriasAgenda, setCategoriasAgenda] = useState<string[]>([]);
  useEffect(() => {
    if (vinculo === "agenda" && !agendaVet && !agendaCarregando) {
      setAgendaCarregando(true);
      fetchComCache<AgendaVetResposta>("reproducao_agenda_vet_diagnostico", () => fetchAgendaVeterinario())
        .then(({ dados }) => { if (dados) setAgendaVet(dados); })
        .finally(() => setAgendaCarregando(false));
    }
  }, [vinculo, agendaVet, agendaCarregando]);
  const numerosDaAgenda = useMemo(() => {
    if (!agendaVet) return [] as string[];
    const s = new Set<string>();
    categoriasAgenda.forEach((cat) => (agendaVet.listas[cat] || []).forEach((item) => s.add(item.numero_matriz)));
    return Array.from(s);
  }, [agendaVet, categoriasAgenda]);
  useEffect(() => {
    if (vinculo === "agenda") setMatrizes(numerosDaAgenda);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numerosDaAgenda.join("|")]);

  function trocarVinculo(v: "animal" | "lote" | "agenda") {
    setVinculo(v);
    setMatrizes(v === "animal" ? (animalFixado ? [animalFixado] : []) : []);
    setLotesSelecionados([]);
    setCategoriasAgenda([]);
  }

  const [data, setData] = useState(hoje());
  const [resultado, setResultado] = useState<"positivo" | "negativo" | "">("");
  const [salvando, setSalvando] = useState(false);

  async function salvar() {
    if (matrizes.length === 0) return erroValidacao("Selecione ao menos uma matriz.");
    if (!data) return erroValidacao("Informe a data do diagnóstico.");
    if (!resultado) return erroValidacao("Toque em Positivo ou Negativo.");
    const resultadoApi = resultado === "positivo" ? "retoque" : "negativo";
    setSalvando(true);
    setAviso(null);
    let salvos = 0;
    const falhados: string[] = [];
    for (const numero of matrizes) {
      try {
        const { enviado } = await enviarOuEnfileirar(
          "/reproducao/diagnostico",
          { numero_matriz: numero, data_diagnostico: data, resultado: resultadoApi },
          `Diagnóstico ${resultado} — matriz ${numero}`,
        );
        if (enviado) salvos++;
      } catch {
        falhados.push(numero);
      }
    }
    if (falhados.length) {
      setMatrizes(falhados);
      setAviso({ tipo: "erro", msg: salvos ? `Salvos: ${salvos}. Falharam: ${falhados.join(", ")} — tente novamente só esses.` : `Nenhum diagnóstico salvo. Falharam: ${falhados.join(", ")}.` });
    } else {
      setAviso({ tipo: "ok", msg: `Diagnóstico salvo para ${salvos} matriz(es).` });
      setResultado("");
      if (vinculo === "animal") rascunho.limpar();
    }
    setSalvando(false);
  }

  return (
    <>
      <RascunhoAviso mostrar={rascunho.salvo} />
      <MobCampo label="Seleção">
        <BotoesEscolha
          opcoes={[
            { valor: "animal", label: "Animal(is)" },
            { valor: "lote", label: "Lote(s)" },
            { valor: "agenda", label: "Agenda do vet." },
          ]}
          valor={vinculo} onChange={trocarVinculo}
        />
      </MobCampo>

      {vinculo === "animal" && (
        <MobCampo label="Matriz(es) (nº / nome) — pode escolher várias">
          <SeletorAnimal animais={animais} valor="" onChange={adicionar} placeholder="Buscar matriz e tocar para adicionar…" />
        </MobCampo>
      )}

      {vinculo === "lote" && (
        <MobCampo label="Lote(s) — servidas de cada lote marcado">
          <LinhaPills>
            {lotesServidas.map((l) => (
              <MobPill key={l} ativa={lotesSelecionados.includes(l)}
                onClick={() => setLotesSelecionados((p) => p.includes(l) ? p.filter((x) => x !== l) : [...p, l])}>
                {l}
              </MobPill>
            ))}
            {!lotesServidas.length && <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum lote com matriz servida.</p>}
          </LinhaPills>
        </MobCampo>
      )}

      {vinculo === "agenda" && (
        <MobCampo label="Categoria(s) da Agenda do veterinário">
          {agendaCarregando && <p style={{ fontSize: "0.85rem", color: "var(--mob-muted)" }}>Carregando agenda…</p>}
          {agendaVet && (
            <LinhaPills>
              {LISTAS_AGENDA_VETERINARIO.filter((l) => (agendaVet.totais[l.chave] || 0) > 0).map((l) => (
                <MobPill key={l.chave} ativa={categoriasAgenda.includes(l.chave)}
                  onClick={() => setCategoriasAgenda((p) => p.includes(l.chave) ? p.filter((x) => x !== l.chave) : [...p, l.chave])}>
                  {l.rotulo} ({agendaVet.totais[l.chave]})
                </MobPill>
              ))}
            </LinhaPills>
          )}
        </MobCampo>
      )}

      {matrizes.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "0.9rem" }}>
          {matrizes.map((n) => {
            const a = animais.find((x) => x.numero === n);
            return (
              <span key={n} style={{
                display: "inline-flex", alignItems: "center", gap: "0.4rem",
                padding: "0.4rem 0.5rem 0.4rem 0.7rem", borderRadius: 999,
                background: "var(--mob-vinho)", color: "#FFFFFF", fontSize: "0.85rem", fontWeight: 700,
              }} title={a ? rotuloAnimal(a, rotuloDe) : undefined}>
                {n}
                <button type="button" onClick={() => remover(n)} aria-label={`Remover ${n}`}
                  style={{ width: 32, height: 32, margin: "-4px -6px -4px 0", borderRadius: "50%", border: "none", cursor: "pointer", background: "rgba(255,255,255,0.2)", color: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1rem", lineHeight: 1, flexShrink: 0 }}>
                  ×
                </button>
              </span>
            );
          })}
        </div>
      )}

      <MobCampo label="Data do diagnóstico">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <MobCampo label="Resultado">
        <BotoesEscolha
          opcoes={[
            { valor: "positivo", label: "Positivo", cor: "var(--mob-verde)" },
            { valor: "negativo", label: "Negativo", cor: "var(--mob-vermelho)" },
          ]}
          valor={resultado} onChange={setResultado}
        />
      </MobCampo>
      <button className="mob-btn" onClick={salvar} disabled={salvando || enviando}>
        {salvando ? "Salvando…" : `Salvar${matrizes.length ? ` (${matrizes.length})` : ""}`}
      </button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}

// ── Parto → POST /reproducao/parto ───────────────────────────────────────────
// Após o parto ser salvo de verdade (online), sugere lote real para a MÃE
// (del_dias=0, acabou de parir) e para a CRIA (categoria Bezerra/Bezerro,
// data_nasc = data do parto) via sugestaoLoteEvento — mesma função do site,
// que está sendo reescrito em paralelo para pedir confirmação nos dois casos
// (hoje a cria era movida sem perguntar). Aqui replicamos: um pop-up por vez
// (mãe primeiro, cria depois), nunca sobrepostos; só confirma se o usuário
// tocar em "Confirmar", e só mostra sucesso se criarMovimentacao realmente
// funcionar. Sugestão/alocação só roda com o parto enviado online de fato —
// se caiu na fila offline (sem internet), não há como saber ainda se o parto
// vai ser aceito, então pula esse passo (fica só para quando sincronizar).
type SugestaoLoteParto = { tipo: "mae" | "cria"; numero: string; codigo: string; rotulo: string; motivo: string };

function Parto({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, setAviso, erroValidacao } = useEnvio();
  // Rascunho da matriz — mesma razão dos demais formulários (docs/agents/
  // design-implementation.md §5, acabamento-de-campo.html).
  const rascunho = useRascunho<string>("parto_matriz", animalFixado || "");
  const matriz = rascunho.valor;
  const setMatriz = rascunho.setValor;
  const [data, setData] = useState(hoje());
  const [sexo, setSexo] = useState<"F" | "M" | "">("");
  const [brincoCria, setBrincoCria] = useState("");
  const [salvando, setSalvando] = useState(false);

  const [filaSugestoes, setFilaSugestoes] = useState<SugestaoLoteParto[]>([]);
  const [movendo, setMovendo] = useState(false);
  const [avisosLote, setAvisosLote] = useState<{ tipo: "ok" | "erro"; msg: string }[]>([]);

  async function salvar() {
    if (!matriz) return erroValidacao("Selecione a matriz.");
    if (!data) return erroValidacao("Informe a data do parto.");
    if (!sexo) return erroValidacao("Toque no sexo da cria (F ou M).");
    const brinco = brincoCria.trim();
    // Cria a ficha da cria só se o brinco foi informado; sem brinco, registra o
    // parto e guarda o sexo na observação (o backend exige número para a cria).
    const corpo = brinco
      ? { numero_matriz: matriz, data_parto: data, crias: [{ numero: brinco, sexo, nasceu_viva: true }] }
      : { numero_matriz: matriz, data_parto: data, crias: [], observacao: `Cria ${sexo === "F" ? "fêmea" : "macho"} (sem brinco informado)` };

    setSalvando(true);
    setAviso(null);
    setAvisosLote([]);
    setFilaSugestoes([]);
    try {
      const { enviado } = await enviarOuEnfileirar(
        "/reproducao/parto", corpo,
        `Parto — matriz ${matriz} (cria ${sexo === "F" ? "fêmea" : "macho"})`,
      );
      setAviso(enviado
        ? { tipo: "ok", msg: "Lançamento salvo." }
        : { tipo: "offline", msg: "Sem internet — guardado, será enviado automaticamente ao conectar." });
      try { navigator.vibrate?.(enviado ? 20 : [15, 60, 15]); } catch { /* sem suporte — segue sem vibrar */ }

      if (enviado) {
        const fila: SugestaoLoteParto[] = [];
        const matrizObj = animais.find((a) => a.numero === matriz);
        try {
          const { lote_sugerido } = await sugestaoLoteEvento({
            numero_matriz: matriz,
            categoria_abrev: matrizObj?.categoria_abrev || matrizObj?.categoria_completa || "",
            del_dias: 0,
          });
          // Só pergunta se o lote sugerido for DIFERENTE do lote atual da mãe
          // — já está lá, não há nada para confirmar.
          if (lote_sugerido && lote_sugerido.rotulo !== matrizObj?.grupo_primario) {
            fila.push({ tipo: "mae", numero: matriz, codigo: lote_sugerido.codigo, rotulo: lote_sugerido.rotulo, motivo: "Parto" });
          }
        } catch { /* sugestão é best-effort — não bloqueia o parto já salvo */ }

        if (brinco) {
          try {
            const { lote_sugerido } = await sugestaoLoteEvento({
              numero_matriz: brinco,
              categoria_abrev: sexo === "F" ? "Bezerra" : "Bezerro",
              data_nasc: data,
            });
            if (lote_sugerido) {
              fila.push({ tipo: "cria", numero: brinco, codigo: lote_sugerido.codigo, rotulo: lote_sugerido.rotulo, motivo: "Nascimento" });
            }
          } catch { /* idem */ }
        }
        setFilaSugestoes(fila);
      }

      setSexo(""); setBrincoCria("");
    } catch (e) {
      setAviso({ tipo: "erro", msg: e instanceof Error ? e.message : "Erro ao salvar." });
      try { navigator.vibrate?.([25, 60, 25, 60, 25]); } catch { /* sem suporte — segue sem vibrar */ }
    } finally {
      setSalvando(false);
    }
  }

  async function confirmarSugestaoAtual() {
    const item = filaSugestoes[0];
    if (!item) return;
    setMovendo(true);
    try {
      await criarMovimentacao({ data_movimento: data, motivo: item.motivo, lote_destino_codigo: item.codigo, animais: [item.numero], origem: "sugestao_confirmada" });
      setAvisosLote((p) => [...p, { tipo: "ok", msg: `${item.numero} movido para o lote ${item.rotulo}.` }]);
    } catch (e) {
      // Erro real na movimentação — não finge sucesso, mostra o problema.
      setAvisosLote((p) => [...p, { tipo: "erro", msg: `Não foi possível mover ${item.numero} para o lote ${item.rotulo}${e instanceof Error ? `: ${e.message}` : ""}.` }]);
    } finally {
      setMovendo(false);
      setFilaSugestoes((f) => f.slice(1));
    }
  }
  function cancelarSugestaoAtual() {
    setFilaSugestoes((f) => f.slice(1));
  }

  const sugestaoAtual = filaSugestoes[0];

  return (
    <>
      <RascunhoAviso mostrar={rascunho.salvo} />
      <MobCampo label="Matriz (nº / nome)">
        <SeletorAnimal animais={animais} valor={matriz} onChange={setMatriz} placeholder="Buscar matriz…" />
      </MobCampo>
      <MobCampo label="Data do parto">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <MobCampo label="Sexo da cria">
        <BotoesEscolha
          opcoes={[{ valor: "F", label: "Fêmea" }, { valor: "M", label: "Macho" }]}
          valor={sexo} onChange={setSexo}
        />
      </MobCampo>
      <MobCampo label="Brinco da cria (opcional)">
        <input className="mob-input" value={brincoCria} onChange={(e) => setBrincoCria(e.target.value)} placeholder="ex.: 4521" />
      </MobCampo>
      <button className="mob-btn" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
      {avisosLote.map((a, i) => <MobAviso key={i} tipo={a.tipo}>{a.msg}</MobAviso>)}

      {sugestaoAtual && (
        <MobConfirmModal
          titulo={sugestaoAtual.tipo === "mae" ? "Mover a mãe de lote?" : "Alocar a cria em um lote?"}
          onCancelar={cancelarSugestaoAtual}
          onConfirmar={confirmarSugestaoAtual}
          confirmando={movendo}
        >
          {sugestaoAtual.tipo === "mae"
            ? <>A matriz <strong>{sugestaoAtual.numero}</strong> pariu agora — mover para o lote <strong>{sugestaoAtual.rotulo}</strong>?</>
            : <>A cria <strong>{sugestaoAtual.numero}</strong> ainda não tem lote — alocar no lote <strong>{sugestaoAtual.rotulo}</strong>?</>}
        </MobConfirmModal>
      )}
    </>
  );
}

// ── Protocolo IATF (D0) → POST /reproducao/protocolo-iatf ────────────────────
// Lança o D0 do protocolo para uma ou mais matrizes. As etapas seguintes
// (D7/D9/D11) entram na agenda pelo backend. O protocolo hormonal é fixo no
// backend — aqui exibimos os hormônios de cada dia para conferência.
// Exportado para a tela Lançar > Protocolos usar o MESMO formulário — dois
// caminhos até o mesmo lançamento, uma só implementação (ver FormProtocolos).
export function ProtocoloIatf({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const { rotuloDe } = useEstadosReprodutivos();
  // Rascunho persistido — se o app for interrompido no meio (a vaca se move,
  // toca o telefone), as matrizes já escolhidas não se perdem ao voltar
  // (docs/agents/design-implementation.md §5, acabamento-de-campo.html).
  const rascunho = useRascunho<string[]>("iatf_matrizes", animalFixado ? [animalFixado] : []);
  const matrizes = rascunho.valor;
  const [dataD0, setDataD0] = useState(hoje());
  const [verHormonios, setVerHormonios] = useState(false);

  function adicionar(numero: string) {
    if (!matrizes.includes(numero)) rascunho.setValor([...matrizes, numero]);
  }
  function remover(numero: string) {
    rascunho.setValor(matrizes.filter((n) => n !== numero));
  }

  function salvar() {
    if (matrizes.length === 0) return erroValidacao("Selecione ao menos uma matriz.");
    if (!dataD0) return erroValidacao("Informe a data do D0.");
    enviar(
      "/reproducao/protocolo-iatf",
      { animais: matrizes, data_d0: dataD0 },
      `Protocolo IATF D0 — ${matrizes.length} vaca(s)`,
      () => rascunho.limpar(),
      { ok: "Protocolo IATF (D0) lançado — as etapas entram na agenda." },
    );
  }

  // Data prevista de cada etapa = D0 + dias (só para conferência visual).
  function dataEtapa(dias: number): string {
    if (!dataD0) return "";
    const d = new Date(`${dataD0}T00:00:00`);
    d.setDate(d.getDate() + dias);
    return d.toLocaleDateString("pt-BR");
  }

  return (
    <>
      <MobCampo label="Matrizes (nº / nome) — pode escolher várias">
        <SeletorAnimal animais={animais} valor="" onChange={adicionar} placeholder="Buscar matriz e tocar para adicionar…" />
      </MobCampo>

      <RascunhoAviso mostrar={rascunho.salvo} />

      {matrizes.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "0.9rem" }}>
          {matrizes.map((n) => {
            const a = animais.find((x) => x.numero === n);
            return (
              <span key={n} style={{
                display: "inline-flex", alignItems: "center", gap: "0.4rem",
                padding: "0.4rem 0.5rem 0.4rem 0.7rem", borderRadius: 999,
                background: "var(--mob-vinho)", color: "#FFFFFF", fontSize: "0.85rem", fontWeight: 700,
              }} title={a ? rotuloAnimal(a, rotuloDe) : undefined}>
                {n}
                <button type="button" onClick={() => remover(n)} aria-label={`Remover ${n}`}
                  style={{ width: 32, height: 32, margin: "-4px -6px -4px 0", borderRadius: "50%", border: "none", cursor: "pointer", background: "rgba(255,255,255,0.2)", color: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1rem", lineHeight: 1, flexShrink: 0 }}>
                  ×
                </button>
              </span>
            );
          })}
        </div>
      )}

      <MobCampo label="Data do D0">
        <input type="date" className="mob-input" value={dataD0} onChange={(e) => setDataD0(e.target.value)} />
      </MobCampo>

      <div style={{ marginBottom: "0.9rem" }}>
        <button type="button" className="mob-btn-2" onClick={() => setVerHormonios((v) => !v)}
          style={{ justifyContent: "space-between" }}>
          <span>Hormônios do protocolo (D0/D7/D9/D11)</span>
          <span aria-hidden style={{ fontWeight: 800 }}>{verHormonios ? "−" : "+"}</span>
        </button>
        {verHormonios && (
          <div style={{ marginTop: "0.5rem", display: "grid", gap: "0.5rem" }}>
            {ETAPAS_IATF.map((e) => {
              const ehD0 = e.dia === 0;
              return (
                <div key={e.dia} style={{
                  padding: "0.7rem 0.8rem", borderRadius: "var(--r-app)",
                  border: `1px solid ${ehD0 ? "var(--mob-vinho)" : "var(--mob-border)"}`,
                  background: ehD0 ? "color-mix(in srgb, var(--mob-vinho) 8%, transparent)" : "var(--mob-surface)",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.5rem", marginBottom: "0.2rem" }}>
                    <strong style={{ fontSize: "0.9rem" }}>
                      D{e.dia}{ehD0 ? " · aplicando agora" : ""}
                    </strong>
                    {dataEtapa(e.dia) && <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)" }}>{dataEtapa(e.dia)}</span>}
                  </div>
                  <span style={{ fontSize: "0.85rem", color: "var(--mob-text)", lineHeight: 1.4 }}>{e.hormonios}</span>
                </div>
              );
            })}
            <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", lineHeight: 1.4, margin: "0.1rem 0 0" }}>
              Protocolo padrão da fazenda. As etapas D7/D9/D11 entram automaticamente na agenda.
            </p>
          </div>
        )}
      </div>

      <button className="mob-btn" onClick={salvar} disabled={enviando}>
        {enviando ? "Salvando…" : `Lançar D0${matrizes.length ? ` (${matrizes.length})` : ""}`}
      </button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}
