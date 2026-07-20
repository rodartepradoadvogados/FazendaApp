"use client";
// Sub-tela REPRODUTIVO: quatro lançamentos em pílulas — Inseminação,
// Diagnóstico, Parto e Protocolo IATF (D0). Usa os mesmos endpoints do
// desktop (/reproducao/*).
import { useEffect, useMemo, useState } from "react";
import { Syringe, Stethoscope, Baby, CalendarClock } from "lucide-react";
import { MobCampo, MobAviso, MobVoltar } from "@/components/mobile/ui";
import { fetchEstoqueSemen, fetchTouros, fetchAgendaVeterinario, LISTAS_AGENDA_VETERINARIO, type Touro, type AgendaVetResposta } from "@/lib/api";
import { enviarOuEnfileirar, fetchComCache } from "@/lib/offline";
import { TouroPicker, type TouroPickerItem } from "@/components/TouroPicker";
import {
  type Animal, type Semen, useCache, useEnvio, hoje, rotuloAnimal,
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
function Inseminacao({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const semen = useCache<Semen[]>("semen", () => fetchEstoqueSemen(), []);
  const [matriz, setMatriz] = useState(animalFixado || "");
  const [data, setData] = useState(hoje());
  const [categoria, setCategoria] = useState<"convencional" | "sexado">("convencional");
  const [touro, setTouro] = useState("");
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [catalogoTouros, setCatalogoTouros] = useState<Touro[]>([]);

  function salvar() {
    if (!matriz) return erroValidacao("Selecione a matriz.");
    if (!data) return erroValidacao("Informe a data da inseminação.");
    enviar(
      "/reproducao/servico",
      { numero_matriz: matriz, data_servico: data, tipo_servico: "IA", reprodutor: touro || undefined, tipo_semen: categoria },
      `Inseminação — matriz ${matriz}${touro ? ` (${touro})` : ""}`,
      () => setTouro(""),
    );
  }

  const opcoes = semen.dados.filter((s) => (s.tipo || "convencional") === categoria).map((s) => s.touro_nome).filter(Boolean);
  const itensCatalogo: TouroPickerItem[] = catalogoTouros.map((t) => ({ naab: t.naab, nome: t.nome || t.naab, central: t.central, raca: t.raca, tpi: t.tpi }));
  return (
    <>
      <MobCampo label="Matriz (nº / nome)">
        <SeletorAnimal animais={animais} valor={matriz} onChange={setMatriz} placeholder="Buscar matriz…" />
      </MobCampo>
      <MobCampo label="Data da inseminação">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <MobCampo label="Sêmen sexado ou convencional?">
        <BotoesEscolha
          opcoes={[{ valor: "convencional", label: "Convencional" }, { valor: "sexado", label: "Sexado" }]}
          valor={categoria} onChange={(v) => { setCategoria(v); setTouro(""); }}
        />
      </MobCampo>
      <MobCampo label="Touro / sêmen (opcional)">
        {!incluirSemEstoque ? (
          <select className="mob-input" value={touro} onChange={(e) => setTouro(e.target.value)}>
            <option value="">Selecione o sêmen…</option>
            {opcoes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        ) : (
          <TouroPicker className="mob-input" itens={itensCatalogo} value={touro} placeholder="Buscar touro no catálogo NAAB..."
            onChangeTexto={setTouro} onSelecionar={(t) => setTouro(t.nome)} />
        )}
        {!incluirSemEstoque && !opcoes.length && <p style={{ fontSize: "0.72rem", color: "var(--mob-laranja)", marginTop: 2 }}>Nenhum sêmen {categoria} em estoque.</p>}
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
  const servidas = useMemo(() => animais.filter((a) => a.sit_rep === "Ins." || a.sit_rep === "Ges."), [animais]);

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
              }} title={a ? rotuloAnimal(a) : undefined}>
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
function Parto({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const [matriz, setMatriz] = useState(animalFixado || "");
  const [data, setData] = useState(hoje());
  const [sexo, setSexo] = useState<"F" | "M" | "">("");
  const [brincoCria, setBrincoCria] = useState("");

  function salvar() {
    if (!matriz) return erroValidacao("Selecione a matriz.");
    if (!data) return erroValidacao("Informe a data do parto.");
    if (!sexo) return erroValidacao("Toque no sexo da cria (F ou M).");
    const brinco = brincoCria.trim();
    // Cria a ficha da cria só se o brinco foi informado; sem brinco, registra o
    // parto e guarda o sexo na observação (o backend exige número para a cria).
    const corpo = brinco
      ? { numero_matriz: matriz, data_parto: data, crias: [{ numero: brinco, sexo, nasceu_viva: true }] }
      : { numero_matriz: matriz, data_parto: data, crias: [], observacao: `Cria ${sexo === "F" ? "fêmea" : "macho"} (sem brinco informado)` };
    enviar(
      "/reproducao/parto",
      corpo,
      `Parto — matriz ${matriz} (cria ${sexo === "F" ? "fêmea" : "macho"})`,
      () => { setSexo(""); setBrincoCria(""); },
    );
  }

  return (
    <>
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
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}

// ── Protocolo IATF (D0) → POST /reproducao/protocolo-iatf ────────────────────
// Lança o D0 do protocolo para uma ou mais matrizes. As etapas seguintes
// (D7/D9/D11) entram na agenda pelo backend. O protocolo hormonal é fixo no
// backend — aqui exibimos os hormônios de cada dia para conferência.
function ProtocoloIatf({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
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
      { animais: matrizes, data_d0: dataD0, protocolo: "Protocolo IATF" },
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
              }} title={a ? rotuloAnimal(a) : undefined}>
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
                  padding: "0.7rem 0.8rem", borderRadius: 12,
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
