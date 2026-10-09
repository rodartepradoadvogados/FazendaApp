"use client";
// Exportação de relatório que CONTÉM réguas de referência (parecer jurídico de
// 08/10/2026, item 6.2) — reutilizável: Réguas hoje; RMCA e Resultado por litro
// quando passarem a mostrar réguas.
//
//   - Sem régua visível no relatório: exporta direto, como qualquer relatório.
//   - Com régua visível: Excel/PDF/Imprimir abre um diálogo. Com o parâmetro
//     `permitir_exportar_com_reguas` da fazenda DESLIGADO (padrão), só há
//     "Exportar sem réguas". Ligado: destinatário, tipo, finalidade e a caixa
//     (não marcada) "Autorizo o envio deste relatório a [destinatário]" — o POST
//     /relatorios/exportacoes é feito ANTES de gerar o arquivo, e o rodapé que a
//     API devolve vai no MESMO bloco da régua (export.ts: última linha da tabela;
//     impressão: dentro da lista de réguas), sem opção de remover.
//   - "Exportar sem réguas" também é registrado (com_reguas: false).
import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { AlertTriangle, FileSpreadsheet, Info, X } from "lucide-react";
import { ErroApi, registrarExportacaoRelatorio, type ExportacaoRelatorioIn } from "@/lib/api";
import { textoAutorizacao } from "@/lib/reguasReferencia";
import type { AcaoExportar } from "./BarraContexto";

export type OpcoesGeracao = { comReguas: boolean; rodape: string | null };
export type GerarExportacao = (tipo: AcaoExportar, o: OpcoesGeracao) => Promise<void> | void;
type Cancelado = Error & { cancelado: true };

const FORMATO: Record<AcaoExportar, ExportacaoRelatorioIn["formato"]> = { excel: "xlsx", pdf: "pdf", imprimir: null };
const ROTULO: Record<AcaoExportar, string> = { excel: "Excel", pdf: "PDF", imprimir: "Imprimir" };
const TIPOS: { v: NonNullable<ExportacaoRelatorioIn["destinatario_tipo"]>; rotulo: string }[] = [
  { v: "banco", rotulo: "Banco" }, { v: "contador", rotulo: "Contador" }, { v: "comprador", rotulo: "Comprador" }, { v: "outro", rotulo: "Outro" },
];

export function useExportacaoComReguas(o: {
  /** Nome do relatório no log (ex.: "reguas_referencia"). */
  relatorio: string;
  /** O que sai no arquivo tem alguma faixa de referência? */
  temReguas: boolean;
  /** Parâmetro da fazenda (GET /financeiro/reguas-referencia → exportacao.permitir_com_reguas). */
  permitir: boolean;
  /** Modelo do texto de autorização vindo da API (textos.exportacao_autorizacao.texto). */
  modeloAutorizacao?: string | null;
  /** Rótulo do parâmetro (textos.compartilhamento_parametro.texto), para dizer onde ligar. */
  rotuloParametro?: string | null;
  gerar: GerarExportacao;
}): { aoExportar: (tipo: AcaoExportar) => Promise<void>; dialogo: ReactNode } {
  const [tipo, setTipo] = useState<AcaoExportar | null>(null);
  const pendente = useRef<{ ok: () => void; falhou: (e: Error) => void } | null>(null);
  const ultimo = useRef(o);
  useEffect(() => { ultimo.current = o; });

  const aoExportar = async (t: AcaoExportar) => {
    if (!ultimo.current.temReguas) { await ultimo.current.gerar(t, { comReguas: false, rodape: null }); return; }
    // O botão da barra só mostra "Pronto" quando o arquivo sai de fato: a promessa espera o diálogo.
    return new Promise<void>((ok, falhou) => { pendente.current = { ok, falhou }; setTipo(t); });
  };
  const fechar = (erro?: Error) => {
    const p = pendente.current;
    pendente.current = null;
    setTipo(null);
    if (!p) return;
    if (erro) p.falhou(erro); else p.ok();
  };
  const dialogo = tipo ? (
    <DialogoExportacao tipo={tipo} relatorio={o.relatorio} permitir={o.permitir} modelo={o.modeloAutorizacao} rotuloParametro={o.rotuloParametro}
      gerar={o.gerar} onFeito={() => fechar()} onCancelar={() => fechar(Object.assign(new Error("cancelado"), { cancelado: true }) as Cancelado)} />
  ) : null;
  return { aoExportar, dialogo };
}

function DialogoExportacao(p: {
  tipo: AcaoExportar; relatorio: string; permitir: boolean; modelo?: string | null; rotuloParametro?: string | null;
  gerar: GerarExportacao; onFeito: () => void; onCancelar: () => void;
}) {
  const uid = useId();
  const ref = useRef<HTMLDialogElement>(null);
  const [modo, setModo] = useState<"com" | "sem">(p.permitir ? "com" : "sem");
  const [destinatario, setDestinatario] = useState("");
  const [tipoDest, setTipoDest] = useState<NonNullable<ExportacaoRelatorioIn["destinatario_tipo"]>>("banco");
  const [finalidade, setFinalidade] = useState("");
  const [autorizo, setAutorizo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [desligado, setDesligado] = useState(!p.permitir);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  // A autorização é para ESTE destinatário: mudou o nome, a caixa desmarca.
  const mudarDestinatario = (v: string) => { setDestinatario(v); setAutorizo(false); };
  const comReguas = modo === "com" && !desligado;
  const pronto = !comReguas || (destinatario.trim().length > 0 && finalidade.trim().length > 0 && autorizo);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (!pronto || enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const r = await registrarExportacaoRelatorio(comReguas ? {
        relatorio: p.relatorio, formato: FORMATO[p.tipo], com_reguas: true, destinatario: destinatario.trim(),
        destinatario_tipo: tipoDest, finalidade: finalidade.trim(), autorizacao_confirmada: true,
      } : { relatorio: p.relatorio, formato: FORMATO[p.tipo], com_reguas: false });
      ref.current?.close();
      await p.gerar(p.tipo, { comReguas, rodape: comReguas ? r.rodape?.texto ?? null : null });
      p.onFeito();
    } catch (err) {
      const status = err instanceof ErroApi ? err.status : 0;
      if (status === 403) { setDesligado(true); setModo("sem"); }
      setErro((err as Error).message || "Não foi possível registrar a exportação.");
      if (ref.current && !ref.current.open) ref.current.showModal();
    } finally {
      setEnviando(false);
    }
  };

  return (
    <dialog ref={ref} className="c4-dlg" aria-labelledby={`${uid}-t`} onCancel={(e) => { e.preventDefault(); ref.current?.close(); p.onCancelar(); }}>
      <form onSubmit={enviar}>
        <div className="c4-h">
          <h2 id={`${uid}-t`}>{ROTULO[p.tipo]}: relatório com réguas de referência</h2>
          <button type="button" className="rl-btn" onClick={() => { ref.current?.close(); p.onCancelar(); }} aria-label="Fechar sem exportar"><X size={15} aria-hidden /> Fechar</button>
        </div>
        <div className="c4-b">
          <p style={{ margin: 0 }}>Este relatório mostra faixas de referência de mercado. Elas só saem do CowData com a sua autorização expressa, a cada envio.</p>
          {desligado ? (
            <div className="c4-info" role="status">
              <Info size={16} aria-hidden />
              <div>
                <b>A exportação com réguas está desligada nesta fazenda.</b>
                <p style={{ margin: ".2rem 0 0" }}>Só o administrador pode ligar, em Configurações › Parâmetros{p.rotuloParametro ? ` (“${p.rotuloParametro.split("\n")[0]}”)` : ""}. Você pode exportar sem as réguas: o arquivo sai só com os números da fazenda.</p>
              </div>
            </div>
          ) : (
            <fieldset className="c4-opcoes">
              <legend className="rl-sr">O que exportar</legend>
              <label><input type="radio" name={`${uid}-modo`} checked={modo === "com"} onChange={() => setModo("com")} /> <span><b>Com as réguas</b> — informe para quem vai e autorize o envio. O arquivo leva um rodapé automático que não pode ser removido.</span></label>
              <label><input type="radio" name={`${uid}-modo`} checked={modo === "sem"} onChange={() => setModo("sem")} /> <span><b>Sem as réguas</b> — só os números da fazenda.</span></label>
            </fieldset>
          )}
          {comReguas && (<>
            <div className="c4-grade2">
              <div className="c4-campo">
                <label htmlFor={`${uid}-dest`}>Destinatário</label>
                <input id={`${uid}-dest`} type="text" required maxLength={200} value={destinatario} autoComplete="off"
                  placeholder="Ex.: Banco do Brasil, agência 1234" onChange={(e) => mudarDestinatario(e.target.value)} />
              </div>
              <div className="c4-campo">
                <label htmlFor={`${uid}-tipo`}>Quem é</label>
                <select id={`${uid}-tipo`} value={tipoDest} onChange={(e) => setTipoDest(e.target.value as typeof tipoDest)}>
                  {TIPOS.map((t) => <option key={t.v} value={t.v}>{t.rotulo}</option>)}
                </select>
              </div>
            </div>
            <div className="c4-campo">
              <label htmlFor={`${uid}-fin`}>Finalidade</label>
              <input id={`${uid}-fin`} type="text" required maxLength={300} value={finalidade} placeholder="Ex.: pedido de crédito de custeio"
                onChange={(e) => setFinalidade(e.target.value)} />
            </div>
            <label className="c4-confirma">
              <input type="checkbox" checked={autorizo} disabled={!destinatario.trim()} onChange={(e) => setAutorizo(e.target.checked)} />
              <span>{textoAutorizacao(p.modelo, destinatario)}</span>
            </label>
          </>)}
          {erro && <div className="c4-erro" role="alert"><AlertTriangle size={16} aria-hidden /><span>{erro}</span></div>}
        </div>
        <div className="c4-p">
          <button type="button" className="rl-btn" onClick={() => { ref.current?.close(); p.onCancelar(); }}>Cancelar</button>
          <button type="submit" className="c4-btn-pri" disabled={!pronto || enviando}>
            <FileSpreadsheet size={15} aria-hidden /> {enviando ? "Registrando…" : comReguas ? `Autorizar e exportar (${ROTULO[p.tipo]})` : `Exportar sem réguas (${ROTULO[p.tipo]})`}
          </button>
        </div>
      </form>
    </dialog>
  );
}
