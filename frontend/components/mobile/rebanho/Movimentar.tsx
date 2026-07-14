"use client";
// Tela REBANHO › aba "Movimentar" — form mínimo de campo:
// animal (busca) · lote de destino · motivo (opcional) · data.
// Mesmo endpoint do desktop: POST /movimentacoes/mover (via fila offline).
import { useEffect, useState } from "react";
import { ArrowRightLeft } from "lucide-react";
import { fetchLotes, fetchMotivosMovimentacao, today, formatDate } from "@/lib/api";
import { fetchComCache, enviarOuEnfileirar } from "@/lib/offline";
import { MobCampo, MobAviso } from "@/components/mobile/ui";
import { BuscaAnimal } from "./comum";

type Lote = { id: number; codigo: string; nome: string; rotulo: string };
type Resultado = "ok" | "offline" | "erro";

export default function Movimentar() {
  const [lotes, setLotes] = useState<Lote[]>([]);
  const [motivos, setMotivos] = useState<string[]>([]);

  const [numero, setNumero] = useState("");
  const [destino, setDestino] = useState("");
  const [motivo, setMotivo] = useState("");
  const [data, setData] = useState(today());
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: Resultado; texto: string } | null>(null);

  useEffect(() => {
    fetchComCache<Lote[]>("lotes", () => fetchLotes()).then(({ dados }) => { if (dados) setLotes(dados); });
    fetchComCache<string[]>("motivos_mov", () => fetchMotivosMovimentacao()).then(({ dados }) => { if (dados) setMotivos(dados); });
  }, []);

  function limpar() { setNumero(""); setDestino(""); setMotivo(""); setData(today()); }

  function vibrar(padrao: number | number[]) {
    try { navigator.vibrate?.(padrao); } catch { /* sem suporte — segue sem vibrar */ }
  }

  async function enviar() {
    setAviso(null);
    if (!numero) { setAviso({ tipo: "erro", texto: "Selecione o animal." }); return; }
    if (!destino) { setAviso({ tipo: "erro", texto: "Selecione o lote de destino." }); return; }
    setEnviando(true);
    try {
      const { enviado } = await enviarOuEnfileirar(
        "/movimentacoes/mover",
        { data_movimento: data, motivo: motivo || undefined, lote_destino_codigo: destino, animais: [numero] },
        `Movimentação — brinco ${numero} → ${destino}`,
      );
      setAviso(enviado
        ? { tipo: "ok", texto: "Movimentação salva." }
        : { tipo: "offline", texto: "Sem internet — guardado, será enviado ao conectar." });
      vibrar(enviado ? 20 : [15, 60, 15]);
      limpar();
    } catch (e) {
      setAviso({ tipo: "erro", texto: e instanceof Error ? e.message : "Erro ao mover animal." });
      vibrar([25, 60, 25, 60, 25]);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div>
      <MobCampo label="Animal">
        <BuscaAnimal valor={numero} onEscolher={(n) => setNumero(n)} />
      </MobCampo>

      <MobCampo label="Lote de destino">
        <select className="mob-input" value={destino} onChange={(e) => setDestino(e.target.value)}>
          <option value="">Selecione…</option>
          {lotes.map((l) => <option key={l.id} value={l.codigo}>{l.rotulo || l.nome || l.codigo}</option>)}
        </select>
      </MobCampo>

      {motivos.length > 0 && (
        <MobCampo label="Motivo (opcional)">
          <select className="mob-input" value={motivo} onChange={(e) => setMotivo(e.target.value)}>
            <option value="">Selecione…</option>
            {motivos.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </MobCampo>
      )}

      <MobCampo label="Data">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
        <span style={{ fontSize: "0.75rem", color: "var(--mob-muted)" }}>{formatDate(data)}</span>
      </MobCampo>

      <button type="button" className="mob-btn" onClick={enviar} disabled={enviando} style={{ marginTop: "0.5rem" }}>
        <ArrowRightLeft size={18} /> {enviando ? "Enviando…" : "Movimentar animal"}
      </button>

      {aviso && <MobAviso tipo={aviso.tipo === "ok" ? "ok" : aviso.tipo === "offline" ? "offline" : "erro"}>{aviso.texto}</MobAviso>}
    </div>
  );
}
