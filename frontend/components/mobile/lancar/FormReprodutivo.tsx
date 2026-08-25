"use client";
// Sub-tela REPRODUTIVO: quatro lançamentos em pílulas — Inseminação,
// Diagnóstico, Parto e Protocolo IATF (D0). Usa os mesmos endpoints do
// desktop (/reproducao/*).
import { useEffect, useMemo, useState, type CSSProperties } from "react";
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
  type Animal, useCache, useEnvio, hoje, rotuloAnimal,
  BotoesEscolha, SeletorAnimal, GradeAcoes, MobPill, LinhaPills,
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

export function FormReprodutivo({ animais, animalFixado, restringirA }: { animais: Animal[]; animalFixado: string | null; restringirA?: Aba[] }) {
  const [aba, setAba] = useState<Aba | null>(null);

  if (!aba) {
    // `restringirA` (opcional): usado pelo Modo Curral para mostrar só
    // Inseminação/Parto — sem o prop (undefined), o comportamento é idêntico
    // ao de hoje, as 4 opções completas usadas por Lançar (LancarTela.tsx).
    const opcoes = [
      { id: "inseminacao", label: "Inseminação", icone: <Syringe size={28} />, cor: "var(--mob-azul)" },
      { id: "diagnostico", label: "Diagnóstico", icone: <Stethoscope size={28} />, cor: "var(--mob-verde)" },
      { id: "parto", label: "Parto", icone: <Baby size={28} />, cor: "var(--mob-roxo)" },
      { id: "iatf", label: "Protocolo IATF", icone: <CalendarClock size={28} />, cor: "var(--mob-laranja)" },
    ].filter((o) => !restringirA || restringirA.includes(o.id as Aba));
    return <GradeAcoes opcoes={opcoes} onEscolher={(id) => setAba(id as Aba)} />;
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
  const [matriz, setMatriz] = useState(animalFixado || "");
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
      () => setTouro(""),
    );
  }

  const touros = semen.dados?.touros || [];
  const opcoes = touros.filter((t) => t.tipo === categoria).map((t) => t.nome);
  const itensCatalogo: TouroPickerItem[] = catalogoTouros.map((t) => ({ naab: t.naab, nome: t.nome || t.naab, central: t.central, raca: t.raca, tpi: t.tpi }));
  return (
    <>
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
  const [matrizes, setMatrizes] = useState<string[]>(animalFixado ? [animalFixado] : []);
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
      if (vinculo === "animal") setMatrizes(animalFixado ? [animalFixado] : []);
    }
    setSalvando(false);
  }

  return (
    <>
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

// ── Parto → POST /reproducao/parto (ou /reproducao/encerramento-gestacao p/
// Aborto) ─────────────────────────────────────────────────────────────────
// Espelha o formulário do site (FormParto.tsx): tipo de parto (inclui
// Natimorto/Aborto), retenção de placenta, parto gemelar (2ª cria), e os
// blocos de colostragem/IgG da cria — recolhidos por padrão (toque para
// abrir), já que a maioria dos partos no curral não tem esses dados na hora.
//
// Após o parto ser salvo de verdade (online), sugere lote real para a MÃE
// (del_dias=0, acabou de parir) e para cada CRIA cadastrada (categoria
// Bezerra/Bezerro, data_nasc = data do parto) via sugestaoLoteEvento — mesma
// função do site. Um pop-up por vez (mãe primeiro, crias depois), nunca
// sobrepostos; só confirma se o usuário tocar em "Confirmar", e só mostra
// sucesso se criarMovimentacao realmente funcionar. Sugestão/alocação só
// roda com o lançamento enviado online de fato — se caiu na fila offline
// (sem internet), não há como saber ainda se foi aceito, então pula esse
// passo (fica só para quando sincronizar). Mesma regra vale para a
// colostragem: só é gravada (2º POST, /sanidade/colostragem) se a 1ª cria
// foi de fato criada E algum campo de colostro/IgG foi preenchido — mesma
// lógica de `registrarColostragem` do site.
type SugestaoLoteParto = { tipo: "mae" | "cria"; numero: string; codigo: string; rotulo: string; motivo: string };

const TIPOS_PARTO = ["Normal", "Distócico moderado", "Distócico severo", "Cesariana", "Natimorto", "Aborto"];
const LITROS_COLOSTRO = ["1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"];
const BRIX_COLOSTRO_OPCOES = Array.from({ length: 21 }, (_, i) => String(15 + i)); // 15%…35%
const BRIX_SORO_OPCOES = Array.from({ length: 13 }, (_, i) => (6 + i * 0.5).toFixed(1)); // 6,0%…12,0%

// Classificação simplificada (mesmos limiares do site — ver FormParto.tsx),
// só para dar um retorno imediato de qualidade no formulário compacto do app.
function classeColostro(brix: number): { txt: string; cor: string } {
  if (brix > 25) return { txt: "Ouro (excelente)", cor: "var(--mob-verde)" };
  if (brix >= 18) return { txt: "Prata (médio)", cor: "var(--mob-ambar)" };
  return { txt: "Bronze (ruim)", cor: "var(--mob-vermelho)" };
}
function classeSoro(brix: number): { txt: string; cor: string } {
  if (brix >= 8.4) return { txt: "Sucesso — bezerra protegida", cor: "var(--mob-verde)" };
  if (brix >= 8.1) return { txt: "Alerta — monitorar", cor: "var(--mob-ambar)" };
  return { txt: "Falha — ação urgente", cor: "var(--mob-vermelho)" };
}

function Parto({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, setAviso, erroValidacao } = useEnvio();
  const [matriz, setMatriz] = useState(animalFixado || "");
  const [data, setData] = useState(hoje());
  const [tipoParto, setTipoParto] = useState("");
  const [retencaoPlacenta, setRetencaoPlacenta] = useState(false);
  const [gemelar, setGemelar] = useState(false);
  const [gemelarSexo, setGemelarSexo] = useState("");
  const [criaSexo, setCriaSexo] = useState<"F" | "M" | "">("");
  const [criaNumero, setCriaNumero] = useState("");
  const [criaBaixada, setCriaBaixada] = useState(false);
  const [cria2Sexo, setCria2Sexo] = useState<"F" | "M" | "">("");
  const [cria2Numero, setCria2Numero] = useState("");
  const [cria2Baixada, setCria2Baixada] = useState(false);
  const [salvando, setSalvando] = useState(false);

  // Colostragem/IgG da 1ª cria — recolhido por padrão (progressive disclosure,
  // mesmo padrão do "Hormônios do protocolo" em ProtocoloIatf, abaixo).
  const [verColostro, setVerColostro] = useState(false);
  const [horaParto, setHoraParto] = useState("");
  const [horaColostro, setHoraColostro] = useState("");
  const [pesoNascer, setPesoNascer] = useState("");
  const [tomouColostro, setTomouColostro] = useState<"Sim" | "Não" | "">("");
  const [litrosColostro, setLitrosColostro] = useState("");
  const [brixColostro, setBrixColostro] = useState("");
  const [brixSoro, setBrixSoro] = useState("");
  const [proteinaSerica, setProteinaSerica] = useState("");
  const [apenasColostroPo, setApenasColostroPo] = useState(false);

  const ehAborto = tipoParto === "Aborto";
  const [abortoPendente, setAbortoPendente] = useState(false);
  const [salvandoAborto, setSalvandoAborto] = useState(false);

  // Natimorto: nasceu, mas não entra no rebanho — baixa automática (mesmo
  // comportamento do site); sexo continua sendo perguntado.
  useEffect(() => {
    if (tipoParto === "Natimorto") { setCriaBaixada(true); setCria2Baixada(true); }
  }, [tipoParto]);

  const clsColostro = brixColostro ? classeColostro(Number(brixColostro)) : null;
  const clsSoro = brixSoro ? classeSoro(Number(brixSoro)) : null;

  const [filaSugestoes, setFilaSugestoes] = useState<SugestaoLoteParto[]>([]);
  const [movendo, setMovendo] = useState(false);
  const [avisosLote, setAvisosLote] = useState<{ tipo: "ok" | "erro"; msg: string }[]>([]);

  function limparCampos() {
    setTipoParto(""); setRetencaoPlacenta(false); setGemelar(false); setGemelarSexo("");
    setCriaSexo(""); setCriaNumero(""); setCriaBaixada(false);
    setCria2Sexo(""); setCria2Numero(""); setCria2Baixada(false);
    setHoraParto(""); setHoraColostro(""); setPesoNascer("");
    setTomouColostro(""); setLitrosColostro(""); setBrixColostro("");
    setBrixSoro(""); setProteinaSerica(""); setApenasColostroPo(false);
    setVerColostro(false);
  }

  // Sugere lote da mãe (del_dias já calculado pelo backend) e enfileira a
  // pergunta se for diferente do lote atual — usado tanto pelo parto normal
  // quanto pelo aborto.
  async function sugerirLoteMae(delDias: number, motivo: string, fila: SugestaoLoteParto[]) {
    const matrizObj = animais.find((a) => a.numero === matriz);
    try {
      const { lote_sugerido } = await sugestaoLoteEvento({
        numero_matriz: matriz,
        categoria_abrev: matrizObj?.categoria_abrev || matrizObj?.categoria_completa || "",
        del_dias: delDias,
      });
      if (lote_sugerido && lote_sugerido.rotulo !== matrizObj?.grupo_primario) {
        fila.push({ tipo: "mae", numero: matriz, codigo: lote_sugerido.codigo, rotulo: lote_sugerido.rotulo, motivo });
      }
    } catch { /* sugestão é best-effort — não bloqueia o lançamento já salvo */ }
  }

  async function salvar() {
    if (!matriz) return erroValidacao("Selecione a matriz.");
    if (!data) return erroValidacao("Informe a data do parto.");
    if (ehAborto) {
      // Só ABRE a pergunta "deseja abrir lactação?" — a gravação (num POST
      // só, /reproducao/encerramento-gestacao) acontece em `concluirAborto`,
      // igual ao PopupAborto do site.
      setAbortoPendente(true);
      return;
    }
    if (!criaSexo) return erroValidacao("Toque no sexo da cria (F ou M).");

    const crias: { numero: string; sexo: string; nasceu_viva: boolean }[] = [
      { numero: criaNumero.trim(), sexo: criaSexo, nasceu_viva: !criaBaixada },
      ...(gemelar && cria2Sexo ? [{ numero: cria2Numero.trim(), sexo: cria2Sexo, nasceu_viva: !cria2Baixada }] : []),
    ];

    setSalvando(true);
    setAviso(null);
    setAvisosLote([]);
    setFilaSugestoes([]);
    try {
      const { enviado, resposta } = await enviarOuEnfileirar(
        "/reproducao/parto",
        {
          numero_matriz: matriz, data_parto: data, tipo_parto: tipoParto || undefined,
          crias, retencao_placenta: retencaoPlacenta || undefined, gemelar: gemelar || undefined,
          gemelar_sexo: gemelar ? (gemelarSexo || undefined) : undefined,
        },
        `Parto — matriz ${matriz} (cria ${criaSexo === "F" ? "fêmea" : "macho"})`,
      );
      setAviso(enviado
        ? { tipo: "ok", msg: "Lançamento salvo." }
        : { tipo: "offline", msg: "Sem internet — guardado, será enviado automaticamente ao conectar." });
      try { navigator.vibrate?.(enviado ? 20 : [15, 60, 15]); } catch { /* sem suporte — segue sem vibrar */ }

      if (enviado) {
        const criasCriadas: string[] = resposta?.crias_criadas || [];
        const fila: SugestaoLoteParto[] = [];
        await sugerirLoteMae(0, "Parto", fila);

        for (const c of criasCriadas) {
          const sexoCria = c === cria2Numero.trim() ? cria2Sexo : criaSexo;
          try {
            const { lote_sugerido } = await sugestaoLoteEvento({
              numero_matriz: c,
              categoria_abrev: sexoCria === "F" ? "Bezerra" : "Bezerro",
              data_nasc: data,
            });
            if (lote_sugerido) {
              fila.push({ tipo: "cria", numero: c, codigo: lote_sugerido.codigo, rotulo: lote_sugerido.rotulo, motivo: "Nascimento" });
            }
          } catch { /* idem */ }
        }
        setFilaSugestoes(fila);

        // Colostragem/IgG só descrevem a 1ª cria (mesmo formulário único do
        // site) — grava só se ela foi de fato criada e algum dado foi informado.
        const criaRegistrada = criasCriadas.includes(criaNumero.trim());
        const algumDadoColostro = tomouColostro || litrosColostro || brixColostro || brixSoro || proteinaSerica || horaParto || horaColostro || pesoNascer || apenasColostroPo;
        if (criaRegistrada && algumDadoColostro) {
          try {
            await enviarOuEnfileirar(
              "/sanidade/colostragem",
              {
                numero_animal: criaNumero.trim(),
                tomou_colostro: tomouColostro ? tomouColostro === "Sim" : undefined,
                litros_colostro: litrosColostro ? Number(litrosColostro) : undefined,
                brix_colostro: brixColostro ? Number(brixColostro) : undefined,
                data_colostro: brixColostro ? data : undefined,
                hora_parto: horaParto || undefined,
                hora_colostro: horaColostro || undefined,
                peso_nascer_kg: pesoNascer ? Number(pesoNascer) : undefined,
                brix_soro: brixSoro ? Number(brixSoro) : undefined,
                proteina_serica: proteinaSerica ? Number(proteinaSerica) : undefined,
                apenas_colostro_po: apenasColostroPo || undefined,
                data_teste_sangue: brixSoro ? data : undefined,
              },
              `Colostragem/IgG — brinco ${criaNumero.trim()}`,
            );
          } catch (e) {
            setAvisosLote((p) => [...p, { tipo: "erro", msg: `A colostragem não pôde ser gravada${e instanceof Error ? `: ${e.message}` : ""}.` }]);
          }
        }
      }

      limparCampos();
    } catch (e) {
      setAviso({ tipo: "erro", msg: e instanceof Error ? e.message : "Erro ao salvar." });
      try { navigator.vibrate?.([25, 60, 25, 60, 25]); } catch { /* sem suporte — segue sem vibrar */ }
    } finally {
      setSalvando(false);
    }
  }

  // Aborto: grava tudo num POST só (POST /reproducao/encerramento-gestacao)
  // — `Parto` com `ordem_parto` NULL, perda de prenhez no serviço vigente e,
  // se respondido "sim", a `Lactacao` com a data real do evento — igual ao
  // `concluirAborto` do site. Via enviarOuEnfileirar (não `encerrarGestacao`
  // de lib/api.ts) para não perder a fila offline.
  async function concluirAborto(abrirLact: boolean) {
    setSalvandoAborto(true);
    setAviso(null);
    setAvisosLote([]);
    setFilaSugestoes([]);
    try {
      const { enviado, resposta } = await enviarOuEnfileirar(
        "/reproducao/encerramento-gestacao",
        { numero_matriz: matriz, data, tipo: "aborto", abrir_lactacao: abrirLact, motivo: "aborto" },
        `Aborto — matriz ${matriz}`,
      );
      setAviso(enviado
        ? { tipo: "ok", msg: "Aborto registrado." }
        : { tipo: "offline", msg: "Sem internet — guardado, será enviado automaticamente ao conectar." });
      try { navigator.vibrate?.(enviado ? 20 : [15, 60, 15]); } catch { /* sem suporte — segue sem vibrar */ }

      if (enviado && resposta?.sugerir_lote) {
        const fila: SugestaoLoteParto[] = [];
        await sugerirLoteMae(resposta.del_dias ?? 0, "Aborto", fila);
        setFilaSugestoes(fila);
      }

      limparCampos();
    } catch (e) {
      setAviso({ tipo: "erro", msg: e instanceof Error ? e.message : "Erro ao salvar." });
      try { navigator.vibrate?.([25, 60, 25, 60, 25]); } catch { /* sem suporte — segue sem vibrar */ }
    } finally {
      setSalvandoAborto(false);
      setAbortoPendente(false);
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
  const checkboxStyle: CSSProperties = { display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.9rem", padding: "0.3rem 0" };

  return (
    <>
      <MobCampo label="Matriz (nº / nome)">
        <SeletorAnimal animais={animais} valor={matriz} onChange={setMatriz} placeholder="Buscar matriz…" />
      </MobCampo>
      <MobCampo label="Data do parto">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <MobCampo label="Tipo de parto">
        <select className="mob-input" value={tipoParto} onChange={(e) => setTipoParto(e.target.value)}>
          <option value="">Selecione…</option>
          {TIPOS_PARTO.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </MobCampo>

      {ehAborto ? (
        <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)", lineHeight: 1.4, marginBottom: "0.9rem" }}>
          Aborto não é um parto — nenhuma cria é cadastrada. Ao salvar, registra a perda de prenhez da matriz e
          pergunta se deseja abrir lactação.
        </p>
      ) : (
        <>
          <MobCampo label="Retenção de placenta">
            <label style={checkboxStyle}>
              <input type="checkbox" checked={retencaoPlacenta} onChange={(e) => setRetencaoPlacenta(e.target.checked)} /> Sim (gera item na Agenda)
            </label>
          </MobCampo>
          <MobCampo label="Parto gemelar (2 crias)">
            <label style={checkboxStyle}>
              <input type="checkbox" checked={gemelar} onChange={(e) => setGemelar(e.target.checked)} /> Sim
            </label>
          </MobCampo>
          {gemelar && (
            <MobCampo label="Sexos do parto gemelar">
              <select className="mob-input" value={gemelarSexo} onChange={(e) => setGemelarSexo(e.target.value)}>
                <option value="">Selecione… (ou deriva dos sexos)</option>
                <option value="FF">FF — duas fêmeas</option>
                <option value="FM">FM — fêmea e macho</option>
                <option value="MM">MM — dois machos</option>
              </select>
            </MobCampo>
          )}

          <MobCampo label="Sexo da cria">
            <BotoesEscolha
              opcoes={[{ valor: "F", label: "Fêmea" }, { valor: "M", label: "Macho" }]}
              valor={criaSexo} onChange={setCriaSexo}
            />
          </MobCampo>
          <MobCampo label="Número da cria (opcional — vazio = baixa automática)">
            <input className="mob-input" value={criaNumero} onChange={(e) => setCriaNumero(e.target.value)} placeholder="ex.: 4521" />
          </MobCampo>
          <MobCampo label="Cria baixada? (não entra no rebanho)">
            <select className="mob-input" value={criaBaixada ? "Sim" : "Não"} disabled={tipoParto === "Natimorto"} onChange={(e) => setCriaBaixada(e.target.value === "Sim")}>
              <option>Não</option><option>Sim</option>
            </select>
            {tipoParto === "Natimorto" && <p style={{ fontSize: "0.72rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>Automático — natimorto.</p>}
          </MobCampo>

          {gemelar && (
            <>
              <div className="mob-secao" style={{ fontSize: "0.85rem" }}>2ª cria</div>
              <MobCampo label="Sexo da 2ª cria">
                <BotoesEscolha
                  opcoes={[{ valor: "F", label: "Fêmea" }, { valor: "M", label: "Macho" }]}
                  valor={cria2Sexo} onChange={setCria2Sexo}
                />
              </MobCampo>
              <MobCampo label="Número da 2ª cria">
                <input className="mob-input" value={cria2Numero} onChange={(e) => setCria2Numero(e.target.value)} placeholder="ex.: 4522" />
              </MobCampo>
              <MobCampo label="2ª cria baixada?">
                <select className="mob-input" value={cria2Baixada ? "Sim" : "Não"} disabled={tipoParto === "Natimorto"} onChange={(e) => setCria2Baixada(e.target.value === "Sim")}>
                  <option>Não</option><option>Sim</option>
                </select>
              </MobCampo>
            </>
          )}

          <button type="button" className="mob-btn-2" onClick={() => setVerColostro((v) => !v)} style={{ justifyContent: "space-between", marginBottom: "0.9rem" }}>
            <span>Colostragem e IgG da cria (opcional)</span>
            <span aria-hidden style={{ fontWeight: 800 }}>{verColostro ? "−" : "+"}</span>
          </button>
          {verColostro && (
            <div style={{ marginBottom: "0.4rem" }}>
              <div className="mob-secao" style={{ fontSize: "0.8rem" }}>Colostragem</div>
              <MobCampo label="Hora do parto"><input type="time" className="mob-input" value={horaParto} onChange={(e) => setHoraParto(e.target.value)} /></MobCampo>
              <MobCampo label="Hora do colostro"><input type="time" className="mob-input" value={horaColostro} onChange={(e) => setHoraColostro(e.target.value)} /></MobCampo>
              <MobCampo label="Peso ao nascer (kg)">
                <input type="number" step="0.1" inputMode="decimal" className="mob-input" value={pesoNascer} onChange={(e) => setPesoNascer(e.target.value)} placeholder="ex.: 38" />
              </MobCampo>
              <MobCampo label="Tomou colostro?">
                <BotoesEscolha opcoes={[{ valor: "Sim", label: "Sim" }, { valor: "Não", label: "Não" }]} valor={tomouColostro} onChange={setTomouColostro} />
              </MobCampo>
              <MobCampo label="Quantidade de colostro (litros)">
                <select className="mob-input" value={litrosColostro} onChange={(e) => setLitrosColostro(e.target.value)}>
                  <option value="">Selecione…</option>
                  {LITROS_COLOSTRO.map((l) => <option key={l} value={l}>{l} L</option>)}
                </select>
              </MobCampo>
              <MobCampo label="Brix do colostro (%)">
                <select className="mob-input" value={brixColostro} onChange={(e) => setBrixColostro(e.target.value)}>
                  <option value="">Selecione…</option>
                  {BRIX_COLOSTRO_OPCOES.map((b) => <option key={b} value={b}>{b}%</option>)}
                </select>
                {clsColostro && <p style={{ fontSize: "0.78rem", marginTop: "0.3rem", color: clsColostro.cor, fontWeight: 700 }}>{clsColostro.txt}</p>}
              </MobCampo>

              <div className="mob-secao" style={{ fontSize: "0.8rem" }}>Exame de sangue (IgG)</div>
              <MobCampo label="Brix do soro (%)">
                <select className="mob-input" value={brixSoro} onChange={(e) => setBrixSoro(e.target.value)}>
                  <option value="">Selecione…</option>
                  {BRIX_SORO_OPCOES.map((v) => <option key={v} value={v}>{v.replace(".", ",")}%</option>)}
                </select>
                {clsSoro && <p style={{ fontSize: "0.78rem", marginTop: "0.3rem", color: clsSoro.cor, fontWeight: 700 }}>{clsSoro.txt}</p>}
              </MobCampo>
              <MobCampo label="Proteína sérica (g/dL)">
                <input type="number" step="0.1" inputMode="decimal" className="mob-input" value={proteinaSerica} onChange={(e) => setProteinaSerica(e.target.value)} placeholder="ex.: 6,0" />
              </MobCampo>
              <label style={checkboxStyle}>
                <input type="checkbox" checked={apenasColostroPo} onChange={(e) => setApenasColostroPo(e.target.checked)} /> Só colostro em pó (sem colostro materno)
              </label>
            </div>
          )}
        </>
      )}

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

      {abortoPendente && (
        <MobConfirmModal
          titulo="Perda de prenhez (aborto)"
          onCancelar={() => concluirAborto(false)}
          onConfirmar={() => concluirAborto(true)}
          confirmando={salvandoAborto}
          textoCancelar="Não, só aborto"
          textoConfirmar="Sim, abrir lactação"
        >
          A matriz <strong>{matriz}</strong> voltará ao status vazio, em observação. Deseja abrir lactação para ela?
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
  const [matrizes, setMatrizes] = useState<string[]>(animalFixado ? [animalFixado] : []);
  const [dataD0, setDataD0] = useState(hoje());
  const [verHormonios, setVerHormonios] = useState(false);

  function adicionar(numero: string) {
    setMatrizes((atual) => (atual.includes(numero) ? atual : [...atual, numero]));
  }
  function remover(numero: string) {
    setMatrizes((atual) => atual.filter((n) => n !== numero));
  }

  function salvar() {
    if (matrizes.length === 0) return erroValidacao("Selecione ao menos uma matriz.");
    if (!dataD0) return erroValidacao("Informe a data do D0.");
    enviar(
      "/reproducao/protocolo-iatf",
      { animais: matrizes, data_d0: dataD0 },
      `Protocolo IATF D0 — ${matrizes.length} vaca(s)`,
      () => setMatrizes([]),
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
