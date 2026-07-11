"use client";
// Sub-tela PRODUÇÃO (LEITE): controle leiteiro individual — animal, data e o
// leite de cada ordenha. Endpoint do desktop: POST /producao/controles.
import { useState } from "react";
import { MobCampo, MobAviso } from "@/components/mobile/ui";
import { type Animal, useEnvio, hoje, SeletorAnimal } from "./comum";

export function FormProducao({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const [animal, setAnimal] = useState(animalFixado || "");
  const [data, setData] = useState(hoje());
  const [o1, setO1] = useState("");
  const [o2, setO2] = useState("");
  const [o3, setO3] = useState("");

  const total = (Number(o1) || 0) + (Number(o2) || 0) + (Number(o3) || 0);

  function salvar() {
    if (!animal) return erroValidacao("Selecione o animal.");
    if (total <= 0) return erroValidacao("Informe o leite de ao menos uma ordenha.");
    // 3ª ordenha é opcional: só entra se preenchida.
    const ordenhas = [Number(o1) || 0, Number(o2) || 0];
    if (o3.trim() !== "") ordenhas.push(Number(o3) || 0);
    enviar(
      "/producao/controles",
      { data_controle: data, entradas: [{ numero_matriz: animal, ordenhas }] },
      `Controle leiteiro — vaca ${animal} (${total.toFixed(1)} kg)`,
      () => { setO1(""); setO2(""); setO3(""); },
    );
  }

  return (
    <>
      <MobCampo label="Vaca (nº / nome)">
        <SeletorAnimal animais={animais} valor={animal} onChange={setAnimal} placeholder="Buscar vaca…" />
      </MobCampo>
      <MobCampo label="Data do controle">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
        <MobCampo label="1ª ordenha (kg)">
          <input type="number" inputMode="decimal" className="mob-input" value={o1} onChange={(e) => setO1(e.target.value)} placeholder="kg" />
        </MobCampo>
        <MobCampo label="2ª ordenha (kg)">
          <input type="number" inputMode="decimal" className="mob-input" value={o2} onChange={(e) => setO2(e.target.value)} placeholder="kg" />
        </MobCampo>
      </div>
      <MobCampo label="3ª ordenha (kg, opcional)">
        <input type="number" inputMode="decimal" className="mob-input" value={o3} onChange={(e) => setO3(e.target.value)} placeholder="kg" />
      </MobCampo>
      <p style={{ margin: "0 0 0.9rem", fontSize: "0.9rem", fontWeight: 700, color: "var(--mob-verde)" }}>
        Total do dia: {total.toFixed(1)} kg
      </p>
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}
