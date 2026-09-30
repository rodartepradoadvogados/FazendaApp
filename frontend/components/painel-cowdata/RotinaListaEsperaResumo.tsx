"use client";
import { useEffect, useState } from "react";
import { ClipboardList } from "lucide-react";
import { fetchResumoRotinaListaEsperaCowData, type ResumoRotinaListaEsperaCowData } from "@/lib/api";
import { usePainelCowDataCor } from "@/lib/painelCowDataTema";

// Painel CowData (admin global), SOMENTE LEITURA: última execução da rotina da
// lista de espera, fazendas processadas hoje e os erros. Não há botão de ação.
export default function RotinaListaEsperaResumo() {
  const COR = usePainelCowDataCor();
  const [r, setR] = useState<ResumoRotinaListaEsperaCowData | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => { fetchResumoRotinaListaEsperaCowData().then(setR).catch((e) => setErro(e.message)); }, []);

  const ultima = r?.ultima_execucao_em
    ? new Date(r.ultima_execucao_em).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
    : "nenhuma ainda";
  return (
    <div data-testid="cowdata-rotina-lista-espera"
      style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1.1rem 1.3rem", marginBottom: "1.5rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.7rem" }}>
        <ClipboardList size={16} style={{ color: COR.dourado }} />
        <h2 style={{ fontSize: "0.95rem", fontWeight: 700 }}>Rotina da lista de espera</h2>
      </div>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.8rem" }}>{erro}</p>}
      {!erro && !r && <p style={{ color: COR.mudo, fontSize: "0.8rem" }}>Carregando…</p>}
      {r && (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "1.5rem", fontSize: "0.82rem" }}>
            <span><strong>Última execução:</strong> {ultima}</span>
            <span><strong>Fazendas com a rotina ligada:</strong> {r.fazendas_ativas}</span>
            <span><strong>Processadas hoje:</strong> {r.fazendas_processadas_hoje}</span>
            <span><strong>Animais que entraram hoje:</strong> {r.entraram_ultima_passada}</span>
            <span style={{ color: r.erros.length ? COR.vermelho : COR.mudo }}><strong>Erros:</strong> {r.erros.length}</span>
          </div>
          {r.erros.length > 0 && (
            <ul style={{ marginTop: "0.6rem", fontSize: "0.78rem", color: COR.vermelho }}>
              {r.erros.map((e) => <li key={e.fazenda_id}>{e.fazenda_nome}: {e.ultimo_erro}</li>)}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
