"use client";
// Painel do admin (Fase 2) — pedidos pendentes de não-admins. Aprovar (com
// confirmação no risco alto), rejeitar (com motivo) e arquivar (alvo sumiu).
import { useEffect, useState } from "react";
import { Check, X, Archive } from "lucide-react";
import { fetchPendentesExclusao, aprovarExclusao, rejeitarExclusao, arquivarPedidoExclusao } from "@/lib/api";
import { confirmacaoEsperada, type PedidoExclusao } from "@/lib/exclusao";

export function PedidosAdmin() {
  const [pedidos, setPedidos] = useState<PedidoExclusao[]>([]);
  const [confirmacoes, setConfirmacoes] = useState<Record<number, string>>({});
  const [motivos, setMotivos] = useState<Record<number, string>>({});
  const [erro, setErro] = useState<string | null>(null);

  const carregar = () => fetchPendentesExclusao().then(setPedidos).catch((e: any) => setErro(e.message));
  useEffect(() => { carregar(); }, []);

  const precisaConfirmacao = (p: PedidoExclusao) => p.risco === "alto" || (p.impacto?.risco ?? null) === "alto";

  const aprovar = async (p: PedidoExclusao) => {
    setErro(null);
    const esperado = confirmacaoEsperada(p.tipo, p.id_alvo);
    if (precisaConfirmacao(p) && (confirmacoes[p.id] ?? "").trim() !== esperado) {
      setErro(`Digite ${esperado} para aprovar.`);
      return;
    }
    try { await aprovarExclusao(p.id, confirmacoes[p.id]); carregar(); }
    catch (e: any) { setErro(e.message); }
  };

  const rejeitar = async (p: PedidoExclusao) => {
    setErro(null);
    try { await rejeitarExclusao(p.id, motivos[p.id]); carregar(); }
    catch (e: any) { setErro(e.message); }
  };

  const arquivar = async (p: PedidoExclusao) => {
    setErro(null);
    try { await arquivarPedidoExclusao(p.id); carregar(); }
    catch (e: any) { setErro(e.message); }
  };

  if (pedidos.length === 0) {
    return <section className="exc-aba"><p className="muted">Nenhum pedido esperando.</p></section>;
  }

  return (
    <section className="exc-aba">
      {erro && <p className="exc-bloqueado">{erro}</p>}
      <ul className="exc-pedidos">
        {pedidos.map((p) => (
          <li key={p.id} className="exc-pedido">
            <div>
              <strong>{p.titulo ?? `${p.tipo} #${p.id_alvo}`}</strong>
              <p className="muted">Pedido por {p.solicitado_por ?? "—"} · risco {p.risco ?? "baixo"}</p>
              {p.alvo_existe === false && <p className="exc-bloqueado">O alvo já não existe mais.</p>}
              {p.apoiadores && p.apoiadores.length > 0 && <p className="muted">Também pedido por: {p.apoiadores.join(", ")}</p>}
            </div>
            {p.alvo_existe !== false && (
              <div className="exc-pedido-acoes">
                {precisaConfirmacao(p) && (
                  <input className="exc-input" placeholder={confirmacaoEsperada(p.tipo, p.id_alvo)}
                    value={confirmacoes[p.id] ?? ""} onChange={(e) => setConfirmacoes({ ...confirmacoes, [p.id]: e.target.value })} />
                )}
                <button className="btn-primary" onClick={() => aprovar(p)}><Check size={14} /> Aprovar</button>
                <input className="exc-input" placeholder="Motivo da rejeição" value={motivos[p.id] ?? ""}
                  onChange={(e) => setMotivos({ ...motivos, [p.id]: e.target.value })} />
                <button className="btn-secondary" onClick={() => rejeitar(p)}><X size={14} /> Rejeitar</button>
              </div>
            )}
            {p.alvo_existe === false && (
              <button className="btn-secondary" onClick={() => arquivar(p)}><Archive size={14} /> Arquivar</button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}