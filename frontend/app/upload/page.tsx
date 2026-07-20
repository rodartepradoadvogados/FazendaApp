"use client";
import { useCallback, useEffect, useState } from "react";
import { Upload as UploadIcon, CheckCircle, XCircle, FileText, Loader2, RefreshCw, Info } from "lucide-react";
import { uploadCSV } from "@/lib/api";
import { SecaoRecolhivel } from "@/components/ui";

const TIPOS = [
  { id: "geral",            label: "GERAL.csv",                       desc: "Situação atual por animal (grupos, sit. rep., DEL)" },
  { id: "reprodutivo",      label: "Consulta_SQL_Reprodutivo.csv",    desc: "Serviços (IA/IATF/Cobertura) + partos" },
  { id: "conta_gerencial",  label: "CONTA_GERENCIAL.csv",            desc: "Movimentações financeiras desde 12/2025" },
  { id: "estoque",          label: "ESTOQUE.csv",                    desc: "Inventário de insumos e hormônios" },
  { id: "controle_leiteiro",label: "Controle_Leiteiro.csv",          desc: "Histórico de pesagens de leite por vaca" },
  { id: "dieta",            label: "DIETA.csv",                      desc: "Plano alimentar por lote (kg/cabeça/dia)" },
  { id: "sanidade",         label: "SANIDADE.csv",                   desc: "Medicamentos aplicados nos animais" },
  { id: "curva_abc",        label: "CURVA_ABC.csv",                  desc: "Classificação A/B/C de compras (Pareto de custos)" },
  { id: "plano_conta_gerencial", label: "PLANO_DE_CONTAS_GERENCIAIS.csv", desc: "Hierarquia do plano de contas gerenciais" },
  { id: "patrimonio",       label: "LISTA_DE_PATRIMONIO.csv",        desc: "Máquinas, veículos, implementos e terras" },
];

type Status = "idle" | "uploading" | "ok" | "error";
type TipoStatus = Record<string, { status: Status; msg: string }>;

export default function UploadPage() {
  const [estados, setEstados] = useState<TipoStatus>(
    Object.fromEntries(TIPOS.map(t => [t.id, { status: "idle" as Status, msg: "" }]))
  );
  const [dragging, setDragging] = useState<string | null>(null);

  const handleFile = useCallback(async (tipo: string, file: File) => {
    setEstados(p => ({ ...p, [tipo]: { status: "uploading", msg: "Enviando..." } }));
    try {
      const res = await uploadCSV(tipo, file);
      const partes: string[] = [];
      if (res.total !== undefined)    partes.push(`${res.total} animais`);
      if (res.inseridos !== undefined) partes.push(`${res.inseridos} inseridos`);
      if (res.atualizados !== undefined) partes.push(`${res.atualizados} atualizados`);
      if (res.servicos !== undefined)  partes.push(`${res.servicos} serviços`);
      if (res.partos !== undefined)    partes.push(`${res.partos} partos`);
      if (res.registros !== undefined) partes.push(`${res.registros} registros`);
      setEstados(p => ({ ...p, [tipo]: { status: "ok", msg: partes.join(" · ") || "Importado com sucesso" } }));
    } catch (e: any) {
      setEstados(p => ({ ...p, [tipo]: { status: "error", msg: e.message } }));
    }
  }, []);

  return (
    <div className="p-6 animate-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <UploadIcon size={22} style={{ color: "var(--dourado)" }} />
          Upload de CSV
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Importe os relatórios exportados do Ideagri. A ordem recomendada é: GERAL → Reprodutivo → Controle Leiteiro → Dieta → Sanidade → Financeiro (Plano de Contas → Conta Gerencial) → Estoque → Curva ABC → Patrimônio.
        </p>
      </div>

      <div className="card mb-4 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
        <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
          Cada arquivo já é importado assim que você o envia. Depois de subir os relatórios, <strong style={{ color: "var(--text)" }}>recarregue a página</strong> para que as telas passem a mostrar os dados novos.
        </p>
        <button className="btn-primary" title="Recarregar a página para refletir os dados enviados" onClick={() => window.location.reload()}>
          <RefreshCw size={16} /> Recarregar página
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {TIPOS.map(tipo => {
          const estado = estados[tipo.id];
          return (
            <div key={tipo.id} className="card">
              <div className="flex items-start gap-3 mb-3">
                <FileText size={18} style={{ color: "var(--dourado)", flexShrink: 0, marginTop: "2px" }} />
                <div>
                  <p style={{ fontWeight: 700, fontSize: "0.9rem" }}>{tipo.label}</p>
                  <p style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{tipo.desc}</p>
                </div>
              </div>

              <label
                className={`dropzone ${dragging === tipo.id ? "active" : ""}`}
                style={{ cursor: "pointer", display: "block" }}
                onDragOver={e => { e.preventDefault(); setDragging(tipo.id); }}
                onDragLeave={() => setDragging(null)}
                onDrop={e => {
                  e.preventDefault(); setDragging(null);
                  const f = e.dataTransfer.files[0];
                  if (f) handleFile(tipo.id, f);
                }}
              >
                <input
                  type="file"
                  accept=".csv"
                  style={{ display: "none" }}
                  onChange={e => {
                    const f = e.target.files?.[0];
                    if (f) handleFile(tipo.id, f);
                    e.target.value = "";
                  }}
                />
                {estado.status === "uploading" ? (
                  <div className="flex flex-col items-center gap-2">
                    <Loader2 size={28} style={{ color: "var(--vinho-light)", animation: "spin 1s linear infinite" }} />
                    <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Processando...</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <UploadIcon size={24} style={{ color: "var(--text-muted)" }} />
                    <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                      Arraste o CSV aqui ou <span style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>clique para selecionar</span>
                    </p>
                  </div>
                )}
              </label>

              {estado.status !== "idle" && estado.status !== "uploading" && (
                <div
                  className="flex items-center gap-2 mt-3 p-2 rounded-lg"
                  style={{
                    background: estado.status === "ok" ? "rgba(46,125,82,0.15)" : "rgba(192,57,43,0.15)",
                    border: `1px solid ${estado.status === "ok" ? "var(--green)" : "var(--red)"}`,
                    fontSize: "0.8rem",
                  }}
                >
                  {estado.status === "ok"
                    ? <CheckCircle size={16} style={{ color: "var(--green-light)", flexShrink: 0 }} />
                    : <XCircle size={16} style={{ color: "var(--red)", flexShrink: 0 }} />}
                  <span style={{ color: estado.status === "ok" ? "var(--green-light)" : "#E07070" }}>
                    {estado.msg}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-6">
        <SecaoRecolhivel titulo="Como exportar do Ideagri" icon={Info} descricao="Passo a passo de exportação de cada relatório do Ideagri">
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", lineHeight: 1.7 }}>
            1. <strong>GERAL:</strong> Meus Relatórios › Geral — situação atual (sem filtro de período)<br />
            2. <strong>Reprodutivo:</strong> Utilitários › Consulta SQL (arrastar o arquivo SQL) — exportar .csv<br />
            3. <strong>Controle Leiteiro:</strong> Relatórios › Controle Leiteiro — histórico de pesagens (todas as datas), exportar .csv<br />
            4. <strong>Dieta:</strong> Nutrição/Alimentação › Dieta por lote — exportar o plano vigente (kg/cabeça/dia) em .csv<br />
            5. <strong>Sanidade:</strong> Relatórios › Sanidade — medicamentos aplicados no período desejado, exportar .csv<br />
            6. <strong>Plano de Contas Gerenciais:</strong> Cadastros › Plano de Contas Gerenciais — exportar a hierarquia em .csv (suba antes da Conta Gerencial)<br />
            7. <strong>Financeiro (Conta Gerencial):</strong> Relatórios › Gestão › Movimentação financeira por conta gerencial — desde 12/2025<br />
            8. <strong>Estoque:</strong> Inventário — data atual<br />
            9. <strong>Curva ABC:</strong> Relatórios › Compras › Curva ABC — classificação A/B/C de custos, exportar .csv<br />
            10. <strong>Patrimônio:</strong> Cadastros › Patrimônio (bens, máquinas, veículos e terras) — exportar a lista em .csv<br />
            <br />
            <strong style={{ color: "var(--dourado-light)" }}>Encoding dos arquivos:</strong> Windows-1252 (Latin-1), separador ponto-e-vírgula (;), decimal com vírgula.
          </p>
        </SecaoRecolhivel>
      </div>
    </div>
  );
}
