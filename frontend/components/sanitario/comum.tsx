"use client";
// Peças pequenas do Sanitário Preventivo v2, usadas por todas as telas do
// módulo (site) e pensadas para o app de campo reaproveitar:
//   - useEuSanitario: o que o usuário pode fazer (GET /sanitario/eu) — o front
//     só esconde botões; quem trava é o back.
//   - useCarregar: estado carregando/erro/dados de uma leitura, sem catch vazio.
//   - OrigemIcone (janela / manual / curral), ChipSituacao, Faixa, Seg.
//   - BarraDesfazer: o "desfazer em 10 s" depois de registrar.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, CalendarCheck, CheckCircle2, Hand, Info, UserPlus } from "lucide-react";
import { fetchCategoriasManejo, fetchEstoqueAtivos } from "@/lib/api";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { desfazerRegistros, meuPapel, mensagemDoErro } from "@/lib/apiSanitario";
import { ROTULO_SITUACAO, ehItemFarmacia, type EuSanitario, type ItemEstoqueClassificavel } from "@/lib/sanitarioTipos";

// ── papel do usuário (cache por sessão de página) ──
let _eu: Promise<EuSanitario> | null = null;
export function useEuSanitario(): { eu: EuSanitario | null; admin: boolean; erro: string | null } {
  const [eu, setEu] = useState<EuSanitario | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    let vivo = true;
    if (!_eu) _eu = meuPapel();
    _eu.then((r) => { if (vivo) setEu(r); }).catch((e) => {
      _eu = null; // permite tentar de novo na próxima tela
      if (vivo) setErro(mensagemDoErro(e, "Não foi possível saber o seu papel no sanitário."));
    });
    return () => { vivo = false; };
  }, []);
  return { eu, admin: !!eu?.administrador, erro };
}

// ── leitura com estados ──
// `carregando` é derivado (a chave pedida ≠ a chave da última resposta), sem
// setState síncrono dentro do efeito.
export function useCarregar<T>(fn: () => Promise<T>, deps: unknown[]): {
  dados: T | null; erro: string | null; carregando: boolean; recarregar: () => void; setDados: (d: T | null) => void;
} {
  const [n, setN] = useState(0);
  const chave = JSON.stringify([deps, n]);
  const [st, setSt] = useState<{ chave: string | null; dados: T | null; erro: string | null }>({ chave: null, dados: null, erro: null });
  useEffect(() => {
    let vivo = true;
    fn()
      .then((d) => { if (vivo) setSt({ chave, dados: d, erro: null }); })
      .catch((e) => { if (vivo) setSt((s) => ({ chave, dados: s.dados, erro: mensagemDoErro(e) })); });
    return () => { vivo = false; };
    // `fn` muda a cada render; a leitura refaz quando as dependências (a chave) mudam.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave]);
  const recarregar = useCallback(() => setN((x) => x + 1), []);
  const setDados = useCallback((d: T | null) => setSt((s) => ({ ...s, dados: d })), []);
  return { dados: st.dados, erro: st.chave === chave ? st.erro : null, carregando: st.chave !== chave, recarregar, setDados };
}

// ── ícone de origem: veio pela janela × incluído manualmente × decisão no curral ──
const ORIGEM_INFO: Record<string, { rotulo: string; Icone: typeof CalendarCheck }> = {
  janela: { rotulo: "Veio pela janela", Icone: CalendarCheck },
  manual: { rotulo: "Incluído manualmente", Icone: UserPlus },
  curral: { rotulo: "Decisão no curral", Icone: Hand },
};
export function OrigemIcone({ origem, tamanho = 14 }: { origem: string; tamanho?: number }) {
  const info = ORIGEM_INFO[origem] ?? ORIGEM_INFO.janela;
  const { Icone } = info;
  return (
    <span className={`san-origem ${origem}`} title={info.rotulo} role="img" aria-label={info.rotulo}>
      <Icone size={tamanho} aria-hidden="true" />
    </span>
  );
}
export function LegendaOrigem({ extra }: { extra?: ReactNode }) {
  return (
    <div className="san-legenda">
      <span><OrigemIcone origem="janela" /> veio pela janela</span>
      <span><OrigemIcone origem="manual" /> incluído manualmente</span>
      <span><OrigemIcone origem="curral" /> decisão no curral</span>
      {extra && <span>{extra}</span>}
    </div>
  );
}

// ── chip de situação do animal numa caixa ──
export function ChipSituacao({ estado, texto }: { estado: string; texto?: string | null }) {
  return (
    <span className={`san-chip k-${estado}`} title={texto || undefined}>
      <i aria-hidden="true" />{ROTULO_SITUACAO[estado] ?? estado}
    </span>
  );
}
export function Chip({ tipo, children }: { tipo: "ok" | "alerta" | "aviso" | "janela" | "marcada" | "inativa" | string; children: ReactNode }) {
  return <span className={`san-chip k-${tipo}`}><i aria-hidden="true" />{children}</span>;
}

// ── faixa de aviso ──
export function Faixa({ tipo = "info", children, role }: { tipo?: "info" | "atencao" | "alerta" | "ok"; children: ReactNode; role?: string }) {
  const Icone = tipo === "ok" ? CheckCircle2 : tipo === "info" ? Info : AlertTriangle;
  return (
    <div className={`san-faixa ${tipo}`} role={role ?? (tipo === "alerta" ? "alert" : undefined)}>
      <Icone size={16} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

// ── botões segmentados (aria-pressed) ──
export function Seg<T extends string>({ opcoes, valor, onChange, rotulo }: {
  opcoes: readonly { id: T; label: ReactNode }[]; valor: T; onChange: (v: T) => void; rotulo: string;
}) {
  return (
    <div className="san-seg" role="group" aria-label={rotulo}>
      {opcoes.map((o) => (
        <button key={o.id} type="button" aria-pressed={valor === o.id} onClick={() => onChange(o.id)}>{o.label}</button>
      ))}
    </div>
  );
}

// ── desfazer em 10 s (quem gravou ou o administrador) ──
export function BarraDesfazer({ registroIds, ate, texto, onDesfeito, onFim }: {
  registroIds: number[]; ate: string | null; texto: ReactNode; onDesfeito: () => void; onFim: () => void;
}) {
  const [fim] = useState(() => (ate ? Date.parse(ate) : Date.now() + 10000));
  const [resta, setResta] = useState(10);
  const [desfazendo, setDesfazendo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    const t = setInterval(() => {
      const r = Math.max(0, Math.ceil((fim - Date.now()) / 1000));
      setResta(r);
      if (r <= 0) { clearInterval(t); onFim(); }
    }, 500);
    return () => clearInterval(t);
  }, [fim, onFim]);
  async function desfazer() {
    setDesfazendo(true); setErro(null);
    try {
      await desfazerRegistros(registroIds);
      onDesfeito();
    } catch (e) {
      setErro(mensagemDoErro(e, "Não foi possível desfazer."));
    } finally {
      setDesfazendo(false);
    }
  }
  return (
    <div className="san-desfazer" role="status">
      <CheckCircle2 size={16} aria-hidden="true" style={{ color: "var(--green-light)" }} />
      <span style={{ flex: 1, minWidth: 0 }}>{texto}</span>
      {erro && <span className="san-erro-txt">{erro}</span>}
      <span className="tempo">{resta} s</span>
      <button type="button" className="btn-ghost san-btn-sm" onClick={desfazer} disabled={desfazendo || resta <= 0}>
        {desfazendo ? "Desfazendo…" : "Desfazer"}
      </button>
    </div>
  );
}

// ── listas de apoio (estoque, categorias), guardadas enquanto a página está aberta ──
// O estoque vem INTEIRO, com a marca `farmacia` (lib/sanitarioTipos.ehItemFarmacia):
// a lista de ESCOLHA mostra só o que é da Farmácia (opcoesEstoqueSan), mas o
// nome de um item já gravado fora dela continua aparecendo (lookup por id).
export type ItemEstoqueSan = { id: number; nome: string; unidade: string | null; quantidade: number | null; farmacia?: boolean };
let _estoque: Promise<ItemEstoqueSan[]> | null = null;
export function carregarEstoqueSan(): Promise<ItemEstoqueSan[]> {
  if (!_estoque) {
    _estoque = fetchEstoqueAtivos().then((d: { itens?: (ItemEstoqueClassificavel & { id: number; nome: string; unidade?: string | null; quantidade?: number | null })[] }) =>
      (d.itens || []).filter((i) => typeof i.id === "number")
        .map((i) => ({ id: i.id, nome: i.nome, unidade: i.unidade ?? null, quantidade: i.quantidade ?? null, farmacia: ehItemFarmacia(i) }))
        .sort((a, b) => a.nome.localeCompare(b.nome)));
    _estoque.catch(() => { _estoque = null; });
  }
  return _estoque;
}
/** Itens oferecidos no <select> "Item do estoque": só Farmácia, mais o já escolhido (para não sumir ao editar). */
export function opcoesEstoqueSan<T extends ItemEstoqueSan>(lista: T[] | null | undefined, selecionado?: number | string | null): T[] {
  const sel = selecionado == null || selecionado === "" ? null : Number(selecionado);
  return (lista || []).filter((e) => e.farmacia !== false || e.id === sel);
}
let _categorias: Promise<{ id: number; nome: string }[]> | null = null;
export function carregarCategoriasSan(): Promise<{ id: number; nome: string }[]> {
  if (!_categorias) {
    _categorias = fetchCategoriasManejo().then((l) => l.filter((c) => typeof c.id === "number").map((c) => ({ id: c.id as number, nome: c.nome })));
    _categorias.catch(() => { _categorias = null; });
  }
  return _categorias;
}

// ── "Quem aplicou?" — pessoa do cadastro ou texto livre ──
export type PessoaEscolhida = { pessoa_id: number | null; texto: string };
export function CampoPessoa({ id, rotulo, valor, onChange }: {
  id: string; rotulo: string; valor: PessoaEscolhida; onChange: (v: PessoaEscolhida) => void;
}) {
  const { pessoas } = usePessoasAtivas();
  const sel = valor.pessoa_id ? String(valor.pessoa_id) : valor.texto ? "__txt" : "";
  const [escrevendo, setEscrevendo] = useState(sel === "__txt");
  return (
    <div className="san-linha">
      <div className="san-campo medio">
        <label htmlFor={id}>{rotulo}</label>
        <select id={id} className="san-input" value={escrevendo ? "__txt" : sel} onChange={(e) => {
          const v = e.target.value;
          setEscrevendo(v === "__txt");
          onChange(v === "__txt" ? { pessoa_id: null, texto: valor.texto } : { pessoa_id: v ? Number(v) : null, texto: "" });
        }}>
          <option value="">Não informar</option>
          {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
          <option value="__txt">Outra pessoa (escrever)</option>
        </select>
      </div>
      {escrevendo && (
        <div className="san-campo medio">
          <label htmlFor={`${id}Txt`}>Nome</label>
          <input id={`${id}Txt`} className="san-input" value={valor.texto} onChange={(e) => onChange({ pessoa_id: null, texto: e.target.value })} />
        </div>
      )}
    </div>
  );
}
