"use client";
// Peças compartilhadas da tela LANÇAR (app móvel de campo):
// tipos, helpers, cache offline de listas para selects, envio padrão
// (enviarOuEnfileirar) e um seletor de animal por busca (número/nome).
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { Search } from "lucide-react";
import { fetchComCache, enviarOuEnfileirar } from "@/lib/offline";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";

// ── Tipos das listas usadas nos formulários ──────────────────────────────────
export type Animal = {
  numero: string;
  nome?: string | null;
  grupo_primario?: string | null;
  categoria_abrev?: string | null;
  categoria_completa?: string | null;
  sit_rep?: string | null;
  del_dias?: number | null;
  sexo?: string | null;
};
export type EstoqueItem = {
  nome: string; quantidade?: number | null; unidade?: string | null; categoria?: string | null; estocavel?: boolean | null;
  conta_gerencial_despesa_padrao?: string | null; conta_gerencial_receita_padrao?: string | null;
  finalidade?: string | null; principio_ativo?: string | null; estoque_semen_id?: number | null; tipo_semen?: string | null;
};
export type Semen = { touro_nome: string; codigo?: string | null; tipo?: string | null; doses?: number | null };
export type DietaItem = { alimento: string; quantidade: number; unidade: string };
export type Dieta = { id: number; lote: number; ativa: boolean; itens_programados: DietaItem[] };

// ── Helpers ──────────────────────────────────────────────────────────────────
export function hoje(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Sem acento, sem caixa — para a busca ser tolerante ("joão" acha "JOAO"). */
export function normalizar(s: string): string {
  return (s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

// `estadoDe` é opcional: quando informado (rotuloDe do hook useEstadosReprodutivos),
// mostra a situação reprodutiva AO VIVO em vez do texto congelado a.sit_rep.
export function rotuloAnimal(a: Animal, estadoDe?: (numero: string) => string): string {
  const cat = a.categoria_abrev || a.categoria_completa || a.grupo_primario || "";
  const sit = estadoDe ? estadoDe(a.numero) : a.sit_rep;
  return [a.nome, cat, sit && sit !== "—" ? sit : null].filter(Boolean).join(" · ");
}

/** Busca por número (brinco), nome, lote, categoria ou situação reprodutiva. */
export function filtrarAnimais(animais: Animal[], busca: string, estadoDe?: (numero: string) => string): Animal[] {
  const q = normalizar(busca);
  if (!q) return animais;
  return animais.filter((a) =>
    normalizar(`${a.numero} ${a.nome || ""} ${a.grupo_primario || ""} ${a.categoria_abrev || a.categoria_completa || ""} ${estadoDe ? estadoDe(a.numero) : (a.sit_rep || "")}`).includes(q),
  );
}

// Unidades — mesma regra do backend (fazenda.rules.unidades) e do desktop:
// a unidade de aplicação precisa ser compatível com a unidade de estoque.
export const UNIDADES = ["ml", "kg", "L", "unidade", "dose", "saca 30kg", "saca 60kg"];
const GRUPOS_UNIDADE: string[][] = [["ml", "unidade", "dose"], ["L", "kg"]];
// Sinônimos/abreviações legadas (import de planilha, cadastro antigo) que
// precisam cair no mesmo grupo do valor canônico — senão o item some das
// opções de unidade compatível (ex.: "un" não batia com "unidade" e escondia "ml").
const SINONIMOS_UNIDADE: Record<string, string> = { un: "unidade", und: "unidade", unid: "unidade", unidades: "unidade" };
export function unidadesCompativeis(unidadeEstoque: string | null | undefined): string[] {
  if (!unidadeEstoque) return UNIDADES;
  const normalizada = SINONIMOS_UNIDADE[unidadeEstoque.trim().toLowerCase()] || unidadeEstoque;
  return GRUPOS_UNIDADE.find((g) => g.includes(normalizada)) || [unidadeEstoque];
}

// ── Cache offline de listas (selects funcionam com a última cópia) ───────────
export function useCache<T>(chave: string, buscar: () => Promise<T>, inicial: T): { dados: T; doCache: boolean; pronto: boolean } {
  const [estado, setEstado] = useState<{ dados: T; doCache: boolean; pronto: boolean }>({ dados: inicial, doCache: false, pronto: false });
  useEffect(() => {
    let vivo = true;
    fetchComCache(chave, buscar)
      .then((r) => { if (vivo) setEstado({ dados: (r.dados ?? inicial) as T, doCache: r.doCache, pronto: true }); })
      .catch(() => { if (vivo) setEstado((e) => ({ ...e, pronto: true })); });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave]);
  return estado;
}

/** Vibração curta de confirmação — feedback tátil pra quem já guardou o
 * celular no bolso ou está com luva/sujeira na tela. Sem suporte (iOS Safari
 * não tem `navigator.vibrate`), é um no-op silencioso. */
function vibrar(padrao: number | number[]) {
  try {
    navigator.vibrate?.(padrao);
  } catch {
    // ignora — vibração é só um reforço, nunca deve quebrar o envio.
  }
}

// ── Envio padrão de todos os formulários ─────────────────────────────────────
export type Aviso = { tipo: "ok" | "offline" | "erro"; msg: string } | null;

export function useEnvio() {
  const [aviso, setAviso] = useState<Aviso>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(
    caminho: string, corpo: unknown, descricao: string,
    aoLimpar?: () => void, msgs?: { ok?: string; offline?: string },
  ) {
    setEnviando(true);
    setAviso(null);
    try {
      const { enviado } = await enviarOuEnfileirar(caminho, corpo, descricao);
      setAviso(enviado
        ? { tipo: "ok", msg: msgs?.ok ?? "Lançamento salvo." }
        : { tipo: "offline", msg: msgs?.offline ?? "Sem internet — guardado, será enviado automaticamente ao conectar." });
      vibrar(enviado ? 20 : [15, 60, 15]);
      aoLimpar?.();
    } catch (e) {
      setAviso({ tipo: "erro", msg: e instanceof Error ? e.message : "Erro ao salvar." });
      vibrar([25, 60, 25, 60, 25]);
    } finally {
      setEnviando(false);
    }
  }

  /** Mostra um erro de validação sem chamar a rede. */
  function erroValidacao(msg: string) {
    setAviso({ tipo: "erro", msg });
  }

  return { aviso, setAviso, enviar, enviando, erroValidacao };
}

// ── Primitivos locais ────────────────────────────────────────────────────────
export function MobPill({ ativa, onClick, children }: { ativa: boolean; onClick: () => void; children: ReactNode }) {
  return <button type="button" className={`mob-pill${ativa ? " ativa" : ""}`} onClick={onClick}>{children}</button>;
}

export function LinhaPills({ children }: { children: ReactNode }) {
  return <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.9rem" }}>{children}</div>;
}

/**
 * Grade de blocos grandes e coloridos para escolher uma sub-ação real (ex.:
 * dentro de Reprodutivo: Inseminação/Diagnóstico/Parto/Protocolo IATF) — abre
 * o formulário só depois do toque no bloco, no lugar de pílulas de texto
 * pequenas disfarçando uma navegação de verdade. Mesmo visual dos 6 blocos da
 * tela raiz de Lançar (`.mob-bloco`), com o ícone tingido por categoria.
 */
export type OpcaoAcao = { id: string; label: string; icone: ReactNode; cor?: string };

export function GradeAcoes({ opcoes, onEscolher }: { opcoes: OpcaoAcao[]; onEscolher: (id: string) => void }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
      {opcoes.map((o) => (
        <button key={o.id} type="button" className="mob-bloco" onClick={() => onEscolher(o.id)}
          style={o.cor ? ({ "--c": o.cor } as CSSProperties) : undefined}>
          <span className="icone">{o.icone}</span>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Dois botões grandes exclusivos (ex.: Positivo/Negativo, M/F, Entrada/Saída). */
export function BotoesEscolha<T extends string>({ opcoes, valor, onChange }:
  { opcoes: { valor: T; label: string; cor?: string }[]; valor: T | ""; onChange: (v: T) => void }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${opcoes.length}, 1fr)`, gap: "0.6rem" }}>
      {opcoes.map((o) => {
        const ativo = valor === o.valor;
        const cor = o.cor || "var(--mob-vinho)";
        return (
          <button key={o.valor} type="button" onClick={() => onChange(o.valor)}
            style={{
              padding: "1rem 0.5rem", borderRadius: 14, fontSize: "1rem", fontWeight: 700, cursor: "pointer",
              border: `2px solid ${ativo ? cor : "var(--mob-border)"}`,
              background: ativo ? cor : "var(--mob-surface)",
              color: ativo ? "#FFFFFF" : "var(--mob-text)",
            }}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Seletor de animal por busca (número/nome). Serve tanto para o animal já
 * "fixado" no topo (vem preenchido e recolhido) quanto para escolher um novo.
 */
export function SeletorAnimal({ animais, valor, onChange, placeholder }:
  { animais: Animal[]; valor: string; onChange: (numero: string) => void; placeholder?: string }) {
  const [q, setQ] = useState("");
  const [editando, setEditando] = useState(false);
  const sel = animais.find((a) => a.numero === valor);
  const { rotuloDe } = useEstadosReprodutivos();

  if (sel && !editando) {
    return (
      <button type="button" className="mob-input" style={{ textAlign: "left", cursor: "pointer" }}
        onClick={() => { setEditando(true); setQ(""); }}>
        <strong>{sel.numero}</strong>{rotuloAnimal(sel, rotuloDe) ? ` · ${rotuloAnimal(sel, rotuloDe)}` : ""}
      </button>
    );
  }

  // Abre direto para seleção — a lista completa (ordenada por número) aparece
  // assim que o campo é tocado, sem precisar digitar nada; a busca só filtra
  // essa lista. Nunca é possível "enviar" texto livre: só o toque num item
  // chama onChange.
  const ordenados = [...animais].sort((a, b) => a.numero.localeCompare(b.numero, undefined, { numeric: true }));
  const filtrados = filtrarAnimais(ordenados, q, rotuloDe).slice(0, 30);
  return (
    <div>
      <div style={{ position: "relative" }}>
        <Search size={17} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--mob-muted)", pointerEvents: "none" }} />
        <input className="mob-input" autoFocus value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={placeholder || "Buscar brinco ou nome (ou toque numa vaca abaixo)…"} style={{ paddingLeft: "2.5rem" }} />
      </div>
      <div style={{ marginTop: "0.4rem", display: "grid", gap: "0.4rem", maxHeight: "50vh", overflowY: "auto" }}>
        {filtrados.map((a) => (
          <button key={a.numero} type="button" className="mob-btn-2" style={{ justifyContent: "flex-start", textAlign: "left", padding: "0.7rem 0.9rem" }}
            onClick={() => { onChange(a.numero); setEditando(false); setQ(""); }}>
            <span><strong>{a.numero}</strong>{rotuloAnimal(a, rotuloDe) ? ` · ${rotuloAnimal(a, rotuloDe)}` : ""}</span>
          </button>
        ))}
        {filtrados.length === 0 && <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem", padding: "0.2rem" }}>Nenhum animal encontrado.</p>}
      </div>
    </div>
  );
}
