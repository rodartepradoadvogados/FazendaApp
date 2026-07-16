"use client";
// Tela REBANHO › aba "Baixar" — saída definitiva do rebanho (irreversível).
// Form mínimo: animal (busca) · tipo de baixa · motivo · data · observação.
// Mesmo endpoint do desktop: POST /baixas/ (via fila offline).
// Confirmação em 2 toques: o botão vira "Confirmar baixa?" antes de enviar.
import { useEffect, useState } from "react";
import { Skull } from "lucide-react";
import { fetchOpcoesBaixa, today, formatDate } from "@/lib/api";
import { fetchComCache, enviarOuEnfileirar } from "@/lib/offline";
import { MobCampo, MobAviso } from "@/components/mobile/ui";
import { BuscaAnimal } from "./comum";

type Opcoes = { tipos_baixa: string[]; motivos: string[]; motivos_doenca: string[] };
type Resultado = "ok" | "offline" | "erro";

const LABEL_TIPO: Record<string, string> = {
  morte: "Morte", descarte_voluntario: "Descarte voluntário", descarte_involuntario: "Descarte involuntário",
};
const LABEL_MOTIVO: Record<string, string> = { venda: "Venda", abate: "Abate", acidente: "Acidente", doenca: "Doença" };

export default function Baixar() {
  const [opcoes, setOpcoes] = useState<Opcoes | null>(null);

  // "definitiva" = saída do rebanho (morte/descarte); "a_descartar" = vaca
  // segue ativa, mas sai das ações reprodutivas (mesmo conceito do site).
  const [modo, setModo] = useState<"definitiva" | "a_descartar">("definitiva");

  const [numero, setNumero] = useState("");
  const [tipoBaixa, setTipoBaixa] = useState("");
  const [motivo, setMotivo] = useState("");
  const [data, setData] = useState(today());
  const [observacao, setObservacao] = useState("");
  const [confirmar, setConfirmar] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: Resultado; texto: string } | null>(null);

  useEffect(() => {
    fetchComCache<Opcoes>("opcoes_baixa", () => fetchOpcoesBaixa()).then(({ dados }) => { if (dados) setOpcoes(dados); });
  }, []);

  // Qualquer alteração cancela o estado "confirmar".
  function set<T>(setter: (v: T) => void) { return (v: T) => { setter(v); setConfirmar(false); }; }

  function limpar() { setNumero(""); setTipoBaixa(""); setMotivo(""); setData(today()); setObservacao(""); setConfirmar(false); }

  function mudarModo(v: "definitiva" | "a_descartar") { setModo(v); setConfirmar(false); }

  function vibrar(padrao: number | number[]) {
    try { navigator.vibrate?.(padrao); } catch { /* sem suporte — segue sem vibrar */ }
  }

  async function enviar() {
    setAviso(null);
    if (!numero) { setAviso({ tipo: "erro", texto: "Selecione o animal." }); return; }

    if (modo === "a_descartar") {
      if (!confirmar) { setConfirmar(true); vibrar(15); return; }
      setEnviando(true);
      try {
        const { enviado } = await enviarOuEnfileirar(
          "/baixas/a-descartar",
          { animais: [numero], descartar: true, observacao: observacao || undefined },
          `A descartar — brinco ${numero}`,
        );
        setAviso(enviado
          ? { tipo: "ok", texto: 'Marcado como "A descartar" — segue ativo, fora das ações reprodutivas.' }
          : { tipo: "offline", texto: "Sem internet — guardado, será enviado ao conectar." });
        vibrar(enviado ? 20 : [15, 60, 15]);
        limpar();
      } catch (e) {
        setConfirmar(false);
        setAviso({ tipo: "erro", texto: e instanceof Error ? e.message : 'Erro ao marcar "A descartar".' });
        vibrar([25, 60, 25, 60, 25]);
      } finally {
        setEnviando(false);
      }
      return;
    }

    if (!tipoBaixa) { setAviso({ tipo: "erro", texto: "Selecione o tipo de baixa." }); return; }
    if (!motivo) { setAviso({ tipo: "erro", texto: "Selecione o motivo." }); return; }
    if (!confirmar) { setConfirmar(true); vibrar(15); return; } // 1º toque: pede confirmação

    setEnviando(true);
    try {
      const { enviado } = await enviarOuEnfileirar(
        "/baixas/",
        { animais: [numero], tipo_baixa: tipoBaixa, motivo, data_baixa: data, observacao: observacao || undefined },
        `Baixa — brinco ${numero} (${LABEL_MOTIVO[motivo] || motivo})`,
      );
      setAviso(enviado
        ? { tipo: "ok", texto: "Baixa salva." }
        : { tipo: "offline", texto: "Sem internet — guardado, será enviado ao conectar." });
      vibrar(enviado ? 20 : [15, 60, 15]);
      limpar();
    } catch (e) {
      setConfirmar(false);
      setAviso({ tipo: "erro", texto: e instanceof Error ? e.message : "Erro ao registrar baixa." });
      vibrar([25, 60, 25, 60, 25]);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div>
      <MobCampo label="O que fazer">
        <div className="flex gap-4" style={{ fontSize: "0.82rem" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <input type="radio" name="modo_baixa" checked={modo === "definitiva"} onChange={() => mudarModo("definitiva")} />
            Baixa definitiva
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <input type="radio" name="modo_baixa" checked={modo === "a_descartar"} onChange={() => mudarModo("a_descartar")} />
            Marcar "A descartar"
          </label>
        </div>
      </MobCampo>

      <p style={{ fontSize: "0.82rem", color: "var(--mob-vermelho)", fontWeight: 600, marginBottom: "0.8rem" }}>
        {modo === "definitiva"
          ? "Atenção: a baixa é a saída definitiva do rebanho e não pode ser desfeita pelo app."
          : 'A vaca continua ativa (ordenha, sanidade, movimentação), mas sai das ações reprodutivas (IATF, inseminação, candidatas).'}
      </p>

      <MobCampo label="Animal">
        <BuscaAnimal valor={numero} onEscolher={set(setNumero)} />
      </MobCampo>

      {modo === "definitiva" && (
        <>
          <MobCampo label="Tipo de baixa">
            <select className="mob-input" value={tipoBaixa} onChange={(e) => set(setTipoBaixa)(e.target.value)}>
              <option value="">Selecione…</option>
              {(opcoes?.tipos_baixa || []).map((t) => <option key={t} value={t}>{LABEL_TIPO[t] || t}</option>)}
            </select>
          </MobCampo>

          <MobCampo label="Motivo">
            <select className="mob-input" value={motivo} onChange={(e) => set(setMotivo)(e.target.value)}>
              <option value="">Selecione…</option>
              {(opcoes?.motivos || []).map((m) => <option key={m} value={m}>{LABEL_MOTIVO[m] || m}</option>)}
            </select>
          </MobCampo>

          <MobCampo label="Data">
            <input type="date" className="mob-input" value={data} onChange={(e) => set(setData)(e.target.value)} />
            <span style={{ fontSize: "0.75rem", color: "var(--mob-muted)" }}>{formatDate(data)}</span>
          </MobCampo>
        </>
      )}

      <MobCampo label="Observação (opcional)">
        <textarea className="mob-input" rows={2} value={observacao} onChange={(e) => set(setObservacao)(e.target.value)}
          placeholder={modo === "definitiva" ? "ex.: encontrada morta no pasto" : "ex.: baixa produção, aguardando decisão"} />
      </MobCampo>

      <button type="button" className="mob-btn" onClick={enviar} disabled={enviando}
        style={{ marginTop: "0.5rem", background: confirmar ? "var(--mob-vermelho)" : undefined, color: confirmar ? "#fff" : undefined }}>
        <Skull size={18} />{" "}
        {enviando
          ? "Enviando…"
          : confirmar
          ? (modo === "definitiva" ? "Confirmar baixa?" : "Confirmar marcação?")
          : (modo === "definitiva" ? "Baixar animal" : 'Marcar "A descartar"')}
      </button>
      {confirmar && !enviando && (
        <button type="button" className="mob-btn-2" onClick={() => setConfirmar(false)} style={{ marginTop: "0.5rem" }}>Cancelar</button>
      )}

      {aviso && <MobAviso tipo={aviso.tipo === "ok" ? "ok" : aviso.tipo === "offline" ? "offline" : "erro"}>{aviso.texto}</MobAviso>}
    </div>
  );
}
