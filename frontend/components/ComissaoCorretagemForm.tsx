"use client";

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
};

/** Bloco reutilizável de comissão de corretagem — usado na venda e na compra de animal. */
export default function ComissaoCorretagemForm({
  pagarComissao, setPagarComissao, corretorNome, setCorretorNome,
  valorComissao, setValorComissao, formaComissao, setFormaComissao, corretores,
}: Props) {
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
              <input type="number" step="0.01" style={selStyle} value={valorComissao} onChange={(e) => setValorComissao(e.target.value)} /></div>
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
        </div>
      )}
    </div>
  );
}
