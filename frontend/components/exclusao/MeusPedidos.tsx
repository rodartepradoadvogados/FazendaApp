"use client";
// "Meus pedidos" (Fase 2) — o operador acompanha o que pediu e pode cancelar.
import { useEffect, useState } from "react";
import { XCircle } from "lucide-react";
import { fetchMeusPedidosExclusao, cancelarPedidoExclusao } from "@/lib/api";
import type { PedidoExclusao } from "@/lib/exclusao";

export function MeusPedidos() {
  const [pedidos, setPedidos] = useState<PedidoExclusao[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = () => fetchMeusPedidosExclusao().then(setPedidos).catch((e: any) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  const cancelar = async (p: PedidoExclusao) => {
    setErro(null);
    try { await cancelarPedidoExclusao(p.id); carregar(); }
    catch (e: any) { setErro(e.message); }
  };

  if (pedidos.length === 0) {
    return <section className="exc-aba"><p className="muted">Você ainda não pediu nada.</p></section>;
  }

  return (
    <section className="exc-aba">
      {erro && <p className="exc-bloqueado">{erro}</p>}
      <ul className="exc-pedidos">
        {pedidos.map((p) => (
          <li key={p.id} className="exc-pedido">
            <div>
              <strong>{p.titulo ?? `${p.tipo} #${p.id_alvo}`}</strong>
              <p className="muted">Status: {p.status}{p.motivo_rejeicao ? ` — ${p.motivo_rejeicao}` : ""}</p>
            </div>
            {p.status === "pendente" && (
              <button className="btn-secondary" onClick={() => cancelar(p)}><XCircle size={14} /> Cancelar</button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}