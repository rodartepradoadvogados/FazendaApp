"use client";
// Sub-tela PRODUÇÃO (LEITE): controle leiteiro por vaca (individual) ou por
// lote (pesagem de todas as vacas do lote de uma vez, salvando tudo junto),
// mais Pesagem corporal e BST — reaproveitando os mesmos componentes ricos
// do site (FormPesagemCorporal, PainelLancarBst) dentro do envoltório
// ".mob-form-embutido", igual ao já feito em Financeiro (compra/venda de
// animal, folha de pagamento).
// Endpoint do desktop: POST /producao/controles (já aceita lista de entradas).
import { useEffect, useMemo, useState } from "react";
import { MobCampo, MobAviso } from "@/components/mobile/ui";
import { BotoesEscolha, LinhaPills, MobPill, type Animal, useEnvio, hoje, SeletorAnimal } from "./comum";
import { FormPesagemCorporal } from "@/components/FormPesagemCorporal";
import { PainelLancarBst } from "@/components/PainelLancarBst";
import { fetchAgenda } from "@/lib/api";

export function FormProducao({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const [sub, setSub] = useState<"controle" | "pesagem" | "bst">("controle");
  const [agenda, setAgenda] = useState<any>(null);
  const carregarAgenda = () => { fetchAgenda().then(setAgenda).catch(() => {}); };
  useEffect(() => { if (sub === "bst" && !agenda) carregarAgenda(); }, [sub]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <LinhaPills>
        <MobPill ativa={sub === "controle"} onClick={() => setSub("controle")}>Controle leiteiro</MobPill>
        <MobPill ativa={sub === "pesagem"} onClick={() => setSub("pesagem")}>Pesagem corporal</MobPill>
        <MobPill ativa={sub === "bst"} onClick={() => setSub("bst")}>BST</MobPill>
      </LinhaPills>
      {sub === "controle" && <ControleLeiteiro animais={animais} animalFixado={animalFixado} />}
      {sub === "pesagem" && (
        <div className="mob-form-embutido">
          <FormPesagemCorporal animais={animais as any} lotes={lotesDe(animais)} />
        </div>
      )}
      {sub === "bst" && (
        <div className="mob-form-embutido">
          {agenda ? <PainelLancarBst agenda={agenda} onAtualizado={carregarAgenda} /> : <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem" }}>Carregando…</p>}
        </div>
      )}
    </>
  );
}

function lotesDe(animais: Animal[]): string[] {
  return Array.from(new Set(animais.map((a) => a.grupo_primario).filter((g): g is string => !!g))).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

function ControleLeiteiro({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const [modo, setModo] = useState<"vaca" | "lote">("vaca");
  const [animal, setAnimal] = useState(animalFixado || "");
  const [lote, setLote] = useState("");
  const [data, setData] = useState(hoje());
  const [o1, setO1] = useState("");
  const [o2, setO2] = useState("");
  const [o3, setO3] = useState("");
  const [porVaca, setPorVaca] = useState<Record<string, [string, string, string]>>({});

  const total = (Number(o1) || 0) + (Number(o2) || 0) + (Number(o3) || 0);

  const lotes = useMemo(
    () => Array.from(new Set(animais.map((a) => a.grupo_primario).filter((g): g is string => !!g))).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
    [animais],
  );
  const vacasDoLote = useMemo(() => (lote ? animais.filter((a) => a.grupo_primario === lote) : []), [animais, lote]);
  const setOrdVaca = (numero: string, idx: 0 | 1 | 2, valor: string) =>
    setPorVaca((p) => { const arr: [string, string, string] = [...(p[numero] || ["", "", ""])]; arr[idx] = valor; return { ...p, [numero]: arr }; });
  const totalVaca = (numero: string) => (porVaca[numero] || ["", "", ""]).reduce((s, v) => s + (Number(v) || 0), 0);
  const totalLote = vacasDoLote.reduce((s, a) => s + totalVaca(a.numero), 0);

  function salvar() {
    if (modo === "vaca") {
      if (!animal) return erroValidacao("Selecione o animal.");
      if (total <= 0) return erroValidacao("Informe o leite de ao menos uma ordenha.");
      const ordenhas = [Number(o1) || 0, Number(o2) || 0];
      if (o3.trim() !== "") ordenhas.push(Number(o3) || 0);
      enviar(
        "/producao/controles",
        { data_controle: data, entradas: [{ numero_matriz: animal, ordenhas }] },
        `Controle leiteiro — vaca ${animal} (${total.toFixed(1)} kg)`,
        () => { setO1(""); setO2(""); setO3(""); },
      );
    } else {
      if (!lote) return erroValidacao("Selecione o lote.");
      const entradas = vacasDoLote
        .map((a) => {
          const [v1, v2, v3] = porVaca[a.numero] || ["", "", ""];
          const ordenhas = [Number(v1) || 0, Number(v2) || 0];
          if (v3.trim() !== "") ordenhas.push(Number(v3) || 0);
          return { numero_matriz: a.numero, ordenhas };
        })
        .filter((ent) => ent.ordenhas.some((v) => v > 0));
      if (!entradas.length) return erroValidacao("Informe a pesagem de ao menos uma vaca do lote.");
      enviar(
        "/producao/controles",
        { data_controle: data, entradas },
        `Controle leiteiro — lote ${lote} (${entradas.length} vaca(s), ${totalLote.toFixed(1)} kg)`,
        () => { setPorVaca({}); },
      );
    }
  }

  return (
    <>
      <MobCampo label="Lançar por">
        <BotoesEscolha
          opcoes={[{ valor: "vaca", label: "Vaca" }, { valor: "lote", label: "Lote" }]}
          valor={modo} onChange={setModo}
        />
      </MobCampo>

      {modo === "vaca" ? (
        <MobCampo label="Vaca (nº / nome)">
          <SeletorAnimal animais={animais} valor={animal} onChange={setAnimal} placeholder="Buscar vaca…" />
        </MobCampo>
      ) : (
        <MobCampo label="Lote">
          <select className="mob-input" value={lote} onChange={(e) => setLote(e.target.value)}>
            <option value="">Selecione…</option>
            {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </MobCampo>
      )}

      <MobCampo label="Data do controle">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>

      {modo === "vaca" ? (
        <>
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
        </>
      ) : lote ? (
        <div style={{ marginBottom: "0.9rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>{vacasDoLote.length} vaca(s) do lote {lote}</span>
            <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--mob-verde)" }}>Total: {totalLote.toFixed(1)} kg</span>
          </div>
          <div style={{ display: "grid", gap: "0.6rem" }}>
            {vacasDoLote.map((a) => (
              <div key={a.numero} className="mob-input" style={{ padding: "0.6rem 0.7rem" }}>
                <div style={{ fontWeight: 700, marginBottom: "0.4rem" }}>Nº {a.numero}{a.del_dias != null ? ` · DEL ${a.del_dias}` : ""}</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.4rem" }}>
                  <input type="number" inputMode="decimal" className="mob-input" placeholder="1ª (kg)"
                    value={(porVaca[a.numero] || ["", "", ""])[0]} onChange={(e) => setOrdVaca(a.numero, 0, e.target.value)} />
                  <input type="number" inputMode="decimal" className="mob-input" placeholder="2ª (kg)"
                    value={(porVaca[a.numero] || ["", "", ""])[1]} onChange={(e) => setOrdVaca(a.numero, 1, e.target.value)} />
                  <input type="number" inputMode="decimal" className="mob-input" placeholder="3ª (opcional)"
                    value={(porVaca[a.numero] || ["", "", ""])[2]} onChange={(e) => setOrdVaca(a.numero, 2, e.target.value)} />
                </div>
              </div>
            ))}
            {!vacasDoLote.length && <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem" }}>Nenhuma vaca neste lote.</p>}
          </div>
        </div>
      ) : (
        <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem", marginBottom: "0.9rem" }}>Selecione um lote para lançar a pesagem de todas as vacas de uma vez.</p>
      )}

      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}
