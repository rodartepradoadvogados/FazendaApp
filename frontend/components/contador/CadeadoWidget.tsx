"use client";
// Widget do cadeado — ver frontend/lib/useCadeado.ts para o estado e
// backend/fazenda/auth.py::bloquear_escrita_contador para a trava real.
import { useState } from "react";
import { Lock, Unlock } from "lucide-react";
import { CORES_CONTADOR } from "@/app/contador/layout";
import { formatarContagem, type useCadeado } from "@/lib/useCadeado";

type Cadeado = ReturnType<typeof useCadeado>;

export function CadeadoWidget({ cadeado }: { cadeado: Cadeado }) {
  const C = CORES_CONTADOR;
  const [aberto, setAberto] = useState(false);
  const [senha, setSenha] = useState("");

  if (cadeado.destravado) {
    return (
      <div style={{
        display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.7rem 1rem",
        background: "color-mix(in srgb, " + C.positivo + " 12%, " + C.painel + ")",
        border: `1px solid ${C.positivo}`, borderRadius: "var(--r-sm)", marginBottom: "1.2rem",
      }}>
        <Unlock size={16} color={C.positivo} />
        <p style={{ margin: 0, fontSize: "0.82rem", color: C.texto }}>
          Cadeado destravado — <strong>{formatarContagem(cadeado.restanteSegundos)}</strong> restantes
        </p>
        <button type="button" onClick={cadeado.bloquear}
          style={{ marginLeft: "auto", background: "none", border: "none", color: C.mudo, fontSize: "0.75rem", textDecoration: "underline", cursor: "pointer" }}>
          Travar agora
        </button>
      </div>
    );
  }

  return (
    <div style={{ padding: "0.9rem 1rem", background: C.painel, border: `1px solid ${C.borda}`, borderRadius: "var(--r-sm)", marginBottom: "1.2rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
        <Lock size={16} color={C.cobreClaro} />
        <p style={{ margin: 0, fontSize: "0.82rem", color: C.texto }}>
          Ações extraordinárias exigem destravar o cadeado com sua senha.
        </p>
        {!aberto && (
          <button type="button" onClick={() => setAberto(true)}
            style={{
              marginLeft: "auto", background: C.cobre, color: "#fff", border: "none", borderRadius: "var(--r-sm)",
              padding: "0.4rem 0.8rem", fontSize: "0.78rem", fontWeight: 700, cursor: "pointer",
            }}>
            Destravar
          </button>
        )}
      </div>
      {aberto && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const ok = await cadeado.destravar(senha);
            if (ok) { setSenha(""); setAberto(false); }
          }}
          style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.7rem" }}
        >
          <input
            type="password" autoFocus value={senha} onChange={(e) => setSenha(e.target.value)}
            placeholder="Sua senha"
            style={{
              flex: 1, background: C.painelAlt, color: C.texto, border: `1px solid ${C.borda}`,
              borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.82rem",
            }}
          />
          <button type="submit" disabled={cadeado.destravando || !senha}
            style={{
              background: C.cobre, color: "#fff", border: "none", borderRadius: "var(--r-sm)",
              padding: "0.45rem 0.8rem", fontSize: "0.78rem", fontWeight: 700, cursor: "pointer",
              opacity: cadeado.destravando || !senha ? 0.6 : 1,
            }}>
            {cadeado.destravando ? "Verificando…" : "Confirmar"}
          </button>
          <button type="button" onClick={() => { setAberto(false); setSenha(""); }}
            style={{ background: "none", border: "none", color: C.mudo, fontSize: "0.78rem", cursor: "pointer" }}>
            Cancelar
          </button>
        </form>
      )}
      {cadeado.erro && <p style={{ margin: "0.5rem 0 0", fontSize: "0.78rem", color: C.negativo }}>{cadeado.erro}</p>}
    </div>
  );
}
