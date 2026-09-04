"use client";
import { useEffect, useState } from "react";
import { Mail, Save, Share2, X } from "lucide-react";
import { Modal } from "@/components/Modal";
import { fetchDestinatarioRecibo, enviarReciboEmail } from "@/lib/api";
import { gerarReciboPDF, type LancamentoRecibo } from "@/lib/export";
import { baixarArquivo, ehApp, salvarArquivo } from "@/lib/nativo";

const inputStyle: React.CSSProperties = {
  padding: "0.5rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)",
  background: "var(--surface-2)", color: "var(--text)", fontSize: "0.85rem", width: "100%",
};

/** #505 — Emissão de recibo em toda transação financeira: modal com
 * Salvar (baixa o PDF gerado no navegador) / Enviar (envia o mesmo PDF por
 * e-mail) / Cancelar. O destinatário é sugerido pelo contexto do lançamento
 * (fornecedor/cliente/funcionário já cadastrado), mas sempre editável. */
export function ReciboModal({ lanc, onClose }: { lanc: LancamentoRecibo; onClose: () => void }) {
  const [destinatario, setDestinatario] = useState("");
  const [carregandoDestinatario, setCarregandoDestinatario] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [compartilhando, setCompartilhando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  // "Compartilhar" (folha nativa do Android) só faz sentido dentro do app —
  // no navegador é idêntico a "Salvar" (mesmo <a download>), então nem
  // aparece lá (ver lib/nativo.ts::baixarArquivo vs salvarArquivo).
  const [mostrarCompartilhar, setMostrarCompartilhar] = useState(false);
  useEffect(() => { ehApp().then(setMostrarCompartilhar); }, []);

  useEffect(() => {
    let ativo = true;
    if (!lanc.numero_lancamento) { setCarregandoDestinatario(false); return; }
    fetchDestinatarioRecibo(lanc.numero_lancamento)
      .then((d) => { if (ativo) setDestinatario(d.email || ""); })
      .finally(() => { if (ativo) setCarregandoDestinatario(false); });
    return () => { ativo = false; };
  }, [lanc.numero_lancamento]);

  async function salvar() {
    setErro(null);
    try {
      const doc = await gerarReciboPDF(lanc);
      await salvarArquivo(doc.output("blob"), `recibo_${lanc.numero_lancamento || "lancamento"}.pdf`);
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar o recibo");
    }
  }

  async function compartilhar() {
    setErro(null);
    setCompartilhando(true);
    try {
      const doc = await gerarReciboPDF(lanc);
      await baixarArquivo(doc.output("blob"), `recibo_${lanc.numero_lancamento || "lancamento"}.pdf`);
    } catch (e: any) {
      setErro(e.message || "Erro ao compartilhar o recibo");
    } finally {
      setCompartilhando(false);
    }
  }

  async function enviar() {
    setErro(null); setSucesso(null);
    if (!destinatario.trim()) { setErro("Informe o e-mail do destinatário."); return; }
    if (!lanc.numero_lancamento) { setErro("Este lançamento não tem número — não é possível enviar."); return; }
    setEnviando(true);
    try {
      const doc = await gerarReciboPDF(lanc);
      const blob = doc.output("blob");
      await enviarReciboEmail(lanc.numero_lancamento, destinatario.trim(), blob);
      setSucesso("Recibo enviado por e-mail.");
    } catch (e: any) {
      setErro(e.message || "Erro ao enviar o recibo");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Modal title={`Recibo${lanc.numero_lancamento ? ` — ${lanc.numero_lancamento}` : ""}`} onClose={onClose} width="440px">
      <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
        <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
          {lanc.tipo === "receita" ? "Recebemos de" : "Pagamos a"} <strong>{lanc.fornecedor || "—"}</strong> —{" "}
          {(lanc.valor_pago ?? lanc.valor).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}
          {lanc.valor_pago != null && Math.round((lanc.valor - lanc.valor_pago) * 100) / 100 !== 0 && (
            <> (conta original de {lanc.valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })} — pagamento parcial)</>
          )}
        </p>
        <div>
          <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>
            E-mail do destinatário
          </label>
          <input
            style={inputStyle} type="email" value={destinatario}
            placeholder={carregandoDestinatario ? "Buscando contato cadastrado…" : "nome@exemplo.com"}
            onChange={(e) => setDestinatario(e.target.value)}
          />
        </div>
        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
        {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem" }}>{sucesso}</p>}
        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "0.4rem" }}>
          <button className="btn-ghost" onClick={onClose}><X size={14} /> Cancelar</button>
          <button className="btn-ghost" onClick={salvar}><Save size={14} /> Salvar</button>
          {mostrarCompartilhar && (
            <button className="btn-ghost" onClick={compartilhar} disabled={compartilhando}>
              <Share2 size={14} /> {compartilhando ? "Abrindo…" : "Compartilhar"}
            </button>
          )}
          <button className="btn-primary" onClick={enviar} disabled={enviando}>
            <Mail size={14} /> {enviando ? "Enviando…" : "Enviar"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
