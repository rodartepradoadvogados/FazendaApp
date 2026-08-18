"use client";
import { useState } from "react";
import { criarQualidadeLeite, baixarModeloQualidadeLeite, importarQualidadeLeitePlanilha } from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { TabBar } from "@/components/ui";
import { UploadPlanilha } from "@/components/UploadPlanilha";
import { Campo, Secao, inputStyle } from "@/components/lancamentos/comumForms";

type DadosQualidadeLeite = {
  numero_matriz: string | null; data_coleta: string;
  ccs: number | null; cbt: number | null; gordura_pct: number | null; proteina_pct: number | null;
  solidos_totais_pct: number | null; esd_pct: number | null; lactose_pct: number | null; nul: number | null;
  observacao?: string;
};
type SalvarQualidadeLeite = (dados: DadosQualidadeLeite) => Promise<{ enviado?: boolean } | void>;

export function FormQualidadeLeite({ animais, salvarQualidade = criarQualidadeLeite }: { animais: AnimalRow[]; salvarQualidade?: SalvarQualidadeLeite }) {
  const [alvo, setAlvo] = useState<"tanque" | "vaca" | "planilha">("tanque");
  const [matriz, setMatriz] = useState("");
  const [dataColeta, setDataColeta] = useState(() => new Date().toISOString().slice(0, 10));
  const [ccs, setCcs] = useState("");
  const [cbt, setCbt] = useState("");
  const [gordura, setGordura] = useState("");
  const [proteina, setProteina] = useState("");
  const [solidosTotais, setSolidosTotais] = useState("");
  const [esd, setEsd] = useState("");
  const [lactose, setLactose] = useState("");
  const [nul, setNul] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));

  async function salvar() {
    setErro(null); setSucesso(null);
    if (alvo === "vaca" && !matriz) { setErro("Selecione a vaca."); return; }
    if (!dataColeta) { setErro("Informe a data da coleta."); return; }

    setSalvando(true);
    try {
      const r = await salvarQualidade({
        numero_matriz: alvo === "vaca" ? matriz : null,
        data_coleta: dataColeta,
        ccs: num(ccs), cbt: num(cbt), gordura_pct: num(gordura), proteina_pct: num(proteina),
        solidos_totais_pct: num(solidosTotais), esd_pct: num(esd), lactose_pct: num(lactose), nul: num(nul),
        observacao: observacao || undefined,
      });
      setSucesso(r?.enviado === false
        ? "Sem internet — guardado, será enviado quando conectar."
        : "Qualidade do leite lançada com sucesso.");
      setMatriz(""); setCcs(""); setCbt(""); setGordura(""); setProteina(""); setSolidosTotais(""); setEsd(""); setLactose(""); setNul(""); setObservacao("");
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar qualidade do leite");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <TabBar<"tanque" | "vaca" | "planilha">
        abas={[
          { id: "tanque", label: "Todas as vacas em lactação (tanque)", title: "Coleta única representando o rebanho em lactação (amostra do tanque)" },
          { id: "vaca", label: "Uma vaca", title: "Coleta individual de uma vaca" },
          { id: "planilha", label: "Importar de planilha", title: "Lançar várias coletas de uma vez, a partir de uma planilha (Excel ou CSV)" },
        ]}
        ativa={alvo}
        onChange={setAlvo}
      />

      {alvo === "planilha" ? (
        <UploadPlanilha
          modelos={[{ label: "Baixar modelo", baixar: baixarModeloQualidadeLeite }]}
          onImportar={importarQualidadeLeitePlanilha}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {alvo === "vaca" && <Campo label="Vaca" full><AnimalPicker animais={animais} value={matriz} onChange={setMatriz} placeholder="Selecione a vaca…" /></Campo>}
            <Campo label="Data da coleta"><input type="date" style={inputStyle} value={dataColeta} onChange={(e) => setDataColeta(e.target.value)} /></Campo>
          </div>

          <Secao>Índices de qualidade</Secao>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <Campo label="CCS (mil céls./mL)"><input type="number" inputMode="decimal" style={inputStyle} value={ccs} onChange={(e) => setCcs(e.target.value)} /></Campo>
            <Campo label="CBT (mil UFC/mL)"><input type="number" inputMode="decimal" style={inputStyle} value={cbt} onChange={(e) => setCbt(e.target.value)} /></Campo>
            <Campo label="Gordura (%)"><input type="number" inputMode="decimal" style={inputStyle} value={gordura} onChange={(e) => setGordura(e.target.value)} /></Campo>
            <Campo label="Proteína (%)"><input type="number" inputMode="decimal" style={inputStyle} value={proteina} onChange={(e) => setProteina(e.target.value)} /></Campo>
            <Campo label="Sólidos totais — ST (%)"><input type="number" inputMode="decimal" style={inputStyle} value={solidosTotais} onChange={(e) => setSolidosTotais(e.target.value)} /></Campo>
            <Campo label="ESD (%)"><input type="number" inputMode="decimal" style={inputStyle} value={esd} onChange={(e) => setEsd(e.target.value)} /></Campo>
            <Campo label="Lactose (%) — opcional"><input type="number" inputMode="decimal" style={inputStyle} value={lactose} onChange={(e) => setLactose(e.target.value)} /></Campo>
            <Campo label="NUL / ureia (mg/dL) — opcional"><input type="number" inputMode="decimal" style={inputStyle} value={nul} onChange={(e) => setNul(e.target.value)} /></Campo>
          </div>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "-0.4rem" }}>Todos os índices são opcionais — preencha só os que o laudo trouxer.</p>
          <Campo label="Observação" full><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>

          {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
          {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
          <div className="flex items-center gap-3 mt-4">
            <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
          </div>
        </>
      )}
    </>
  );
}
