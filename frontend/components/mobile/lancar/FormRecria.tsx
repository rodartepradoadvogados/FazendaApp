"use client";
// Sub-tela RECRIA (Lançar): registrar um caso de doença em bezerra/novilha —
// mesmo lançamento do site (Recria > Registrar caso), offline-first.
// Endpoint: POST /recria/ocorrencias.
import { useEffect, useState } from "react";
import { MobCampo, MobAviso } from "@/components/mobile/ui";
import { fetchDoencas } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";
import { type Animal, useEnvio, hoje, SeletorAnimal } from "./comum";

export function FormRecria({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const [doencas, setDoencas] = useState<string[]>([]);
  const [animal, setAnimal] = useState(animalFixado || "");
  const [doenca, setDoenca] = useState("");
  const [data, setData] = useState(hoje());
  const [obs, setObs] = useState("");

  useEffect(() => {
    fetchComCache<string[]>("recria_doencas_nomes", () => fetchDoencas().then((d: any[]) => d.map((x) => x.nome)))
      .then(({ dados }) => setDoencas(dados || []));
  }, []);

  function salvar() {
    if (!animal.trim()) return erroValidacao("Selecione o animal.");
    if (!doenca) return erroValidacao("Selecione a doença.");
    enviar(
      "/recria/ocorrencias",
      { numero_matriz: animal.trim(), doenca, data_ocorrencia: data, observacao: obs.trim() || undefined },
      `Caso de ${doenca} — animal ${animal}`,
      () => { setDoenca(""); setObs(""); },
    );
  }

  return (
    <>
      <MobCampo label="Animal (nº / nome)">
        <SeletorAnimal animais={animais} valor={animal} onChange={setAnimal} placeholder="Buscar bezerra/novilha…" />
      </MobCampo>
      <MobCampo label="Doença">
        <select className="mob-input" value={doenca} onChange={(e) => setDoenca(e.target.value)}>
          <option value="">Selecione…</option>
          {doencas.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </MobCampo>
      <MobCampo label="Data do caso">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <MobCampo label="Observação (opcional)">
        <input className="mob-input" value={obs} onChange={(e) => setObs(e.target.value)} />
      </MobCampo>
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}
