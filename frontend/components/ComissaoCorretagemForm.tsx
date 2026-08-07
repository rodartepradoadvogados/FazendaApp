"use client";
import { useState } from "react";
import { ParcelasEditor, CampoQtdParcelas, dividirParcelas, type Parcela } from "./ParcelasEditor";
import { CampoMoeda } from "@/components/CampoMoeda";

const selStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

type Props = {
  pagarComissao: boolean;
  setPagarComissao: (v: boolean) => void;
  corretorNome: string;
  setCorretorNome: (v: string) => void;
  valorComissao: string;
  setValorComissao: (v: string) => void;
  formaComissao: string;
  setFormaComissao: (v: string) => void;
  corretores: string[];
  // "separado": vencimento único OU parcelamento próprio da comissão (opcional
  // — só faz sentido quando a comissão não está redirecionada da transação-mãe).
  dataVencimentoComissao?: string;
  setDataVencimentoComissao?: (v: string) => void;
  parcelarComissao?: boolean;
  setParcelarComissao?: (v: boolean) => void;
  parcelasComissao?: Parcela[];
  setParcelasComissao?: (fn: (arr: Parcela[]) => Parcela[]) => void;
};

/** Bloco reutilizável de comissão de corretagem — usado na venda e na compra de animal. */
export default function ComissaoCorretagemForm({
  pagarComissao, setPagarComissao, corretorNome, setCorretorNome,
  valorComissao, setValorComissao, formaComissao, setFormaComissao, corretores,
  dataVencimentoComissao, setDataVencimentoComissao,
  parcelarComissao, setParcelarComissao, parcelasComissao, setParcelasComissao,
}: Props) {
  const [qtdParcelasComissao, setQtdParcelasComissao] = useState("2");
  const mostrarVencimentoProprio = formaComissao === "separado" && setDataVencimentoComissao;

  return (
    <div className="mb-3" style={{ maxWidth: "560px" }}>
      <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", cursor: "pointer" }}>
        <input type="checkbox" checked={pagarComissao} onChange={(e) => setPagarComissao(e.target.checked)} />
        Pagar comissão ao corretor
      </label>

      {pagarComissao && (
        <div style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.75rem", marginTop: "0.5rem" }}>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div><label style={labelStyle}>Corretor</label>
              <input style={selStyle} list="lista-corretores" value={corretorNome} onChange={(e) => setCorretorNome(e.target.value)} placeholder="Nome do corretor" />
              <datalist id="lista-corretores">
                {corretores.map((c) => <option key={c} value={c} />)}
              </datalist>
            </div>
            <div><label style={labelStyle}>Valor da comissão (R$)</label>
              <CampoMoeda style={selStyle} value={Number(valorComissao) || 0} onChange={(v) => setValorComissao(v ? String(v) : "")} /></div>
          </div>
          <label style={labelStyle}>Forma de pagamento da comissão</label>
          <div className="flex gap-4 mt-1" style={{ fontSize: "0.82rem" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
              <input type="radio" name="forma_comissao" checked={formaComissao === "redirecionado"} onChange={() => setFormaComissao("redirecionado")} />
              Redirecionar do valor da compra/venda (já paga junto)
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
              <input type="radio" name="forma_comissao" checked={formaComissao === "separado"} onChange={() => setFormaComissao("separado")} />
              Pagar separado (conta a pagar própria)
            </label>
          </div>
          <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
            {formaComissao === "redirecionado"
              ? "A comissão fica com o mesmo status de pagamento da compra/venda: se ela já nasce paga, a comissão também nasce paga; se é uma conta a pagar futura, a comissão também fica em aberto com o mesmo vencimento."
              : "A comissão vira uma conta a pagar própria, independente da compra/venda — com vencimento (e parcelamento, se quiser) só dela."}
          </p>

          {mostrarVencimentoProprio && (
            <div style={{ marginTop: "0.6rem" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", cursor: "pointer" }}>
                <input type="checkbox" checked={!!parcelarComissao} onChange={(e) => {
                  setParcelarComissao?.(e.target.checked);
                  if (e.target.checked && setParcelasComissao) {
                    setParcelasComissao(() => dividirParcelas(Number(valorComissao) || 0, Number(qtdParcelasComissao) || 1, dataVencimentoComissao || ""));
                  }
                }} />
                Parcelar a comissão
              </label>
              {!parcelarComissao ? (
                <div className="mt-2"><label style={labelStyle}>Vencimento da comissão</label>
                  <input type="date" style={selStyle} value={dataVencimentoComissao} onChange={(e) => setDataVencimentoComissao!(e.target.value)} /></div>
              ) : (
                <div className="mt-2" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  <CampoQtdParcelas qtd={qtdParcelasComissao} setQtd={(v) => {
                    setQtdParcelasComissao(v);
                    setParcelasComissao?.(() => dividirParcelas(Number(valorComissao) || 0, Number(v) || 1, dataVencimentoComissao || ""));
                  }} />
                  <ParcelasEditor parcelas={parcelasComissao || []} setParcelas={setParcelasComissao || (() => {})} valorReferencia={Number(valorComissao) || 0} />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
