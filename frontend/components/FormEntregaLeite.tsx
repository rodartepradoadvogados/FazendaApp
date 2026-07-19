"use client";
import { useState } from "react";
import { criarEntregaLeiteMensal } from "@/lib/api";
import { Campo, inputStyle, nota } from "@/components/lancamentos/comumForms";

export function FormEntregaLeite() {
  const [competencia, setCompetencia] = useState(() => new Date().toISOString().slice(0, 7));
  const [quantidade, setQuantidade] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!competencia) { setErro("Selecione o mês."); return; }
    if (!quantidade || Number(quantidade) <= 0) { setErro("Informe a quantidade entregue (litros)."); return; }

    setSalvando(true);
    try {
      await criarEntregaLeiteMensal({ competencia, quantidade_litros: Number(quantidade.replace(",", ".")), observacao: observacao || undefined });
      setSucesso(`Entrega de ${competencia} lançada com sucesso.`);
      setQuantidade(""); setObservacao("");
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar entrega mensal do leite");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Mês (competência)"><input type="month" style={inputStyle} value={competencia} onChange={(e) => setCompetencia(e.target.value)} /></Campo>
        <Campo label="Quantidade entregue (litros)"><input type="number" inputMode="decimal" style={inputStyle} value={quantidade} onChange={(e) => setQuantidade(e.target.value)} placeholder="soma das notinhas/app do laticínio no mês" /></Campo>
        <Campo label="Observação" full><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>
      <p style={nota}>Some as notinhas de entrega (ou o total do app do laticínio) do mês inteiro e lance aqui uma vez por mês — o relatório de Produção compara com o controle leiteiro projetado e a receita recebida.</p>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}
