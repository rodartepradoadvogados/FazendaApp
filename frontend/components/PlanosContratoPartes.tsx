"use client";
// Partes da tela de contratação compartilhadas por FazendasAdmin (web) e
// FazendasMobile (Painel CowData): cartão "Preços dos planos", diálogo de
// remoção de módulos e botão "Preparar financeiro". As duas telas só diferem
// no tema (CSS vars no web, cores do Painel no mobile) — por isso `cores`.
import { useState, type CSSProperties } from "react";
import { AlertTriangle, Check, Wallet } from "lucide-react";
import { Modal } from "@/components/Modal";
import {
  atualizarPrecoPlano, prepararFinanceiroFazenda, type CatalogoPlanos, type PlanoCatalogo, type PreparoFinanceiro,
} from "@/lib/api";
import { NOME_MODULO, brl, ordenarPlanos, resumoPreparo, textoRemocao } from "@/lib/planosContrato";

export type CoresPlano = { texto: string; mudo: string; borda: string; dourado: string; verde: string; vermelho: string };
export const CORES_WEB: CoresPlano = {
  texto: "var(--text)", mudo: "var(--text-muted)", borda: "var(--border)", dourado: "var(--dourado)",
  verde: "var(--green-light)", vermelho: "var(--red)",
};

function formatarQuando(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function botao(cores: CoresPlano, cor: string, toque: boolean, desabilitado: boolean): CSSProperties {
  return {
    fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "var(--r-sm)", border: `1px solid ${cor}`, background: "transparent", color: cor,
    cursor: desabilitado ? "not-allowed" : "pointer", opacity: desabilitado ? 0.5 : 1, minHeight: toque ? "44px" : undefined,
    display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.35rem",
  };
}

// ── Cartão "Preços dos planos" ──
// Edita o preço de catálogo de cada plano (PUT /fazendas/catalogo/precos-plano).
// Vale para contratos novos: o preço de um contrato já fechado não muda.
export function PrecosPlanos({ catalogo, onAtualizado, cores, inputStyle, toque = false }: {
  catalogo: CatalogoPlanos | null;
  onAtualizado: (plano: string, novo: Partial<PlanoCatalogo>) => void;
  cores: CoresPlano; inputStyle: CSSProperties; toque?: boolean;
}) {
  const [rascunho, setRascunho] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState<string | null>(null);
  const [feito, setFeito] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  // Só guarda o que o operador digitou; sem rascunho vale o preço do catálogo.
  const valorDe = (p: string, pl: PlanoCatalogo) => rascunho[p] ?? pl.preco.toFixed(2);

  async function salvar(plano: string) {
    const texto = rascunho[plano];
    if (texto === undefined) return;
    const valor = texto.trim() === "" ? NaN : Number(texto.replace(",", "."));
    if (!Number.isFinite(valor) || valor < 0) { setErro("Informe um preço válido (zero ou mais)."); return; }
    setSalvando(plano); setErro(null); setFeito(null);
    try {
      const r = await atualizarPrecoPlano(plano, valor);
      onAtualizado(plano, { preco: r.preco, preco_padrao: r.preco_padrao, atualizado_em: r.atualizado_em, atualizado_por: r.atualizado_por });
      setRascunho((s) => Object.fromEntries(Object.entries(s).filter(([k]) => k !== plano)));
      setFeito(plano);
    } catch (e) { setErro(e instanceof Error ? e.message : "Erro ao salvar o preço."); }
    finally { setSalvando(null); }
  }

  if (!catalogo) return <p style={{ color: cores.mudo, fontSize: "0.8rem" }}>Carregando…</p>;
  return (
    <div>
      <p style={{ color: cores.mudo, fontSize: "0.78rem", marginBottom: "0.7rem" }}>
        O novo preço vale para contratos novos e para quem trocar de plano. <b>Não muda contratos já fechados</b> — cada
        fazenda continua pagando o preço fechado no contrato.
      </p>
      {erro && (
        <div role="alert" style={{ display: "flex", alignItems: "center", gap: "0.4rem", color: cores.vermelho, fontSize: "0.78rem", marginBottom: "0.6rem" }}>
          <AlertTriangle size={14} /><span>{erro}</span>
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {ordenarPlanos(Object.keys(catalogo)).map((p) => {
          const pl = catalogo[p];
          const mudou = rascunho[p] !== undefined && Number(rascunho[p].replace(",", ".")) !== pl.preco;
          const valorCampo = valorDe(p, pl);
          return (
            <div key={p} style={{ border: `1px solid ${cores.borda}`, borderRadius: "var(--r-sm)", padding: "0.55rem 0.7rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
                <div style={{ flex: "1 1 9rem", minWidth: 0 }}>
                  <div style={{ fontSize: "0.85rem", fontWeight: 700, color: cores.texto }}>{pl.nome || p}</div>
                  <div style={{ fontSize: "0.72rem", color: cores.mudo }}>{pl.modulos.map((m) => NOME_MODULO[m] || m).join(", ")}</div>
                </div>
                <label style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.78rem", color: cores.mudo }}>
                  <span id={`preco-plano-${p}`}>R$/mês</span>
                  <input type="number" min={0} step="0.01" inputMode="decimal" aria-labelledby={`preco-plano-${p}`}
                    style={{ ...inputStyle, width: "6.5rem" }} value={valorCampo}
                    onChange={(e) => { setRascunho((s) => ({ ...s, [p]: e.target.value })); setFeito(null); }} />
                </label>
                <button type="button" onClick={() => salvar(p)} disabled={!mudou || salvando !== null}
                  style={botao(cores, cores.dourado, toque, !mudou || salvando !== null)}>
                  {salvando === p ? "Salvando…" : "Salvar preço"}
                </button>
              </div>
              <div style={{ fontSize: "0.72rem", color: cores.mudo, marginTop: "0.3rem" }}>
                {pl.atualizado_por || pl.atualizado_em
                  ? <>Alterado por {pl.atualizado_por || "—"} em {formatarQuando(pl.atualizado_em)}</>
                  : <>Preço de fábrica, ainda não alterado</>}
                {pl.preco_padrao != null && pl.preco_padrao !== pl.preco && <> · de fábrica {brl(pl.preco_padrao)}</>}
                {feito === p && <span style={{ color: cores.verde, marginLeft: "0.5rem", fontWeight: 700 }}><Check size={12} style={{ verticalAlign: "-2px" }} /> Preço salvo</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Diálogo ao tirar módulo de contrato ativo ──
export function DialogoRemocaoModulos({ removidos, salvando, onConfirmar, onCancelar }: {
  removidos: string[]; salvando: boolean; onConfirmar: () => void; onCancelar: () => void;
}) {
  return (
    <Modal title="Tirar módulos deste contrato?" onClose={onCancelar} width="480px">
      <p style={{ fontSize: "0.85rem", marginBottom: "0.6rem" }}>Ao salvar, a fazenda deixa de ver:</p>
      <ul style={{ fontSize: "0.83rem", margin: "0 0 0.8rem 1.1rem", listStyle: "disc", display: "flex", flexDirection: "column", gap: "0.3rem" }}>
        {removidos.map((m) => <li key={m}>{textoRemocao(m)}</li>)}
      </ul>
      <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
        Os dados ficam guardados — nada é apagado. Se o módulo for contratado de novo, tudo volta a aparecer.
      </p>
      <div className="flex gap-2" style={{ justifyContent: "flex-end", flexWrap: "wrap" }}>
        <button type="button" onClick={onCancelar} className="btn-secondary" style={{ fontSize: "0.8rem", padding: "0.4rem 0.9rem", minHeight: "44px" }}>Voltar</button>
        <button type="button" onClick={onConfirmar} disabled={salvando}
          style={{ fontSize: "0.8rem", padding: "0.4rem 0.9rem", minHeight: "44px", borderRadius: "var(--r-sm)", border: "1px solid var(--red)", background: "transparent", color: "var(--red)", cursor: "pointer", fontWeight: 700 }}>
          {salvando ? "Salvando…" : "Tirar e salvar"}
        </button>
      </div>
    </Modal>
  );
}

// ── Botão "Preparar financeiro" (POST /fazendas/{id}/financeiro/preparar) ──
export function PrepararFinanceiro({ fazendaId, cores, toque = false }: { fazendaId: number; cores: CoresPlano; toque?: boolean }) {
  const [preparando, setPreparando] = useState(false);
  // Resultado/erro ficam amarrados à fazenda em que foram obtidos: ao abrir
  // outra fazenda o aviso da anterior simplesmente não aparece.
  const [retorno, setRetorno] = useState<{ fazendaId: number; resultado?: PreparoFinanceiro; erro?: string } | null>(null);
  const resultado = retorno?.fazendaId === fazendaId ? retorno.resultado : undefined;
  const erro = retorno?.fazendaId === fazendaId ? retorno.erro : undefined;

  async function preparar() {
    setPreparando(true); setRetorno(null);
    try { setRetorno({ fazendaId, resultado: await prepararFinanceiroFazenda(fazendaId) }); }
    catch (e) { setRetorno({ fazendaId, erro: e instanceof Error ? e.message : "Erro ao preparar o financeiro." }); }
    finally { setPreparando(false); }
  }

  return (
    <div style={{ border: `1px solid ${cores.borda}`, borderRadius: "var(--r-sm)", padding: "0.7rem 0.9rem", marginBottom: "1rem" }}>
      <div style={{ fontSize: "0.8rem", fontWeight: 700, color: cores.texto, marginBottom: "0.25rem" }}>Financeiro da fazenda</div>
      <p style={{ color: cores.mudo, fontSize: "0.75rem", marginBottom: "0.5rem" }}>
        Carrega o plano de contas padrão e deixa o Controle Financeiro pronto para o primeiro lançamento. Pode apertar de novo sem medo: não duplica nada.
      </p>
      <button type="button" onClick={preparar} disabled={preparando} style={botao(cores, cores.dourado, toque, preparando)}>
        <Wallet size={13} /> {preparando ? "Preparando…" : "Preparar financeiro"}
      </button>
      {resultado && (
        <p role="status" style={{ color: cores.verde, fontSize: "0.78rem", marginTop: "0.5rem" }}>{resumoPreparo(resultado)}</p>
      )}
      {erro && <p role="alert" style={{ color: cores.vermelho, fontSize: "0.78rem", marginTop: "0.5rem" }}>{erro}</p>}
    </div>
  );
}
