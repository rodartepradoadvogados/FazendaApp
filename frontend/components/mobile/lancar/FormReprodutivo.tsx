"use client";
// Sub-tela REPRODUTIVO: três lançamentos em pílulas — Inseminação,
// Diagnóstico e Parto. Usa os mesmos endpoints do desktop (/reproducao/*).
import { useState } from "react";
import { MobCampo, MobAviso } from "@/components/mobile/ui";
import { fetchEstoqueSemen } from "@/lib/api";
import {
  type Animal, type Semen, useCache, useEnvio, hoje,
  MobPill, LinhaPills, BotoesEscolha, SeletorAnimal,
} from "./comum";

type Aba = "inseminacao" | "diagnostico" | "parto";

export function FormReprodutivo({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const [aba, setAba] = useState<Aba>("inseminacao");
  return (
    <>
      <LinhaPills>
        <MobPill ativa={aba === "inseminacao"} onClick={() => setAba("inseminacao")}>Inseminação</MobPill>
        <MobPill ativa={aba === "diagnostico"} onClick={() => setAba("diagnostico")}>Diagnóstico</MobPill>
        <MobPill ativa={aba === "parto"} onClick={() => setAba("parto")}>Parto</MobPill>
      </LinhaPills>
      {aba === "inseminacao" && <Inseminacao animais={animais} animalFixado={animalFixado} />}
      {aba === "diagnostico" && <Diagnostico animais={animais} animalFixado={animalFixado} />}
      {aba === "parto" && <Parto animais={animais} animalFixado={animalFixado} />}
    </>
  );
}

// ── Inseminação → POST /reproducao/servico ───────────────────────────────────
function Inseminacao({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const semen = useCache<Semen[]>("semen", () => fetchEstoqueSemen(), []);
  const [matriz, setMatriz] = useState(animalFixado || "");
  const [data, setData] = useState(hoje());
  const [touro, setTouro] = useState("");

  function salvar() {
    if (!matriz) return erroValidacao("Selecione a matriz.");
    if (!data) return erroValidacao("Informe a data da inseminação.");
    enviar(
      "/reproducao/servico",
      { numero_matriz: matriz, data_servico: data, tipo_servico: "IA", reprodutor: touro || undefined },
      `Inseminação — matriz ${matriz}${touro ? ` (${touro})` : ""}`,
      () => setTouro(""),
    );
  }

  const opcoes = semen.dados.map((s) => s.touro_nome).filter(Boolean);
  return (
    <>
      <MobCampo label="Matriz (nº / nome)">
        <SeletorAnimal animais={animais} valor={matriz} onChange={setMatriz} placeholder="Buscar matriz…" />
      </MobCampo>
      <MobCampo label="Data da inseminação">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <MobCampo label="Touro / sêmen (opcional)">
        <select className="mob-input" value={touro} onChange={(e) => setTouro(e.target.value)}>
          <option value="">Selecione o sêmen…</option>
          {opcoes.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </MobCampo>
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}

// ── Diagnóstico → POST /reproducao/diagnostico ───────────────────────────────
// Positivo/Negativo em dois botões. Positivo grava "retoque": no manejo da
// fazenda o 1º toque positivo agenda a reconfirmação (2º exame) na data certa
// — mesmo comportamento do lançamento pelo site. Negativo grava "negativo".
function Diagnostico({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const [matriz, setMatriz] = useState(animalFixado || "");
  const [data, setData] = useState(hoje());
  const [resultado, setResultado] = useState<"positivo" | "negativo" | "">("");

  function salvar() {
    if (!matriz) return erroValidacao("Selecione a matriz.");
    if (!data) return erroValidacao("Informe a data do diagnóstico.");
    if (!resultado) return erroValidacao("Toque em Positivo ou Negativo.");
    const resultadoApi = resultado === "positivo" ? "retoque" : "negativo";
    enviar(
      "/reproducao/diagnostico",
      { numero_matriz: matriz, data_diagnostico: data, resultado: resultadoApi },
      `Diagnóstico ${resultado} — matriz ${matriz}`,
      () => setResultado(""),
    );
  }

  return (
    <>
      <MobCampo label="Matriz (nº / nome)">
        <SeletorAnimal animais={animais} valor={matriz} onChange={setMatriz} placeholder="Buscar matriz…" />
      </MobCampo>
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
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
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
