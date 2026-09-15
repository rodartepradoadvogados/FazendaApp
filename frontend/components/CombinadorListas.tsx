"use client";
import { useEffect, useMemo, useState } from "react";
import { Combine, RefreshCw } from "lucide-react";
import { fetchRelatoriosManejo, fetchAgenda, fetchRelatorioBst, fetchEstadosReprodutivos } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

/**
 * Combinador de Listas — escolhe 2+ listas de trabalho já existentes no site
 * (Listas de trabalho + BST) e cruza por número do animal (união, interseção
 * ou diferença), exportando o resultado em Excel/PDF. Tudo client-side:
 * reaproveita os mesmos endpoints já usados em Listas de Trabalho, Agenda e
 * Produção > BST — não duplica cálculo nenhum, só recombina o que já existe.
 *
 * A antiga tabela read-only "Lista de BST" foi removida daqui (T-2026-08):
 * duplicava, sem filtro/seleção/ação nenhuma, o que já aparece com mais
 * funcionalidade em Agenda (indicadores clicáveis) e em Produção > BST
 * (seleção + lançamento, ver PainelLancarBst.tsx). Os dados de BST
 * (fetchAgenda/fetchRelatorioBst) continuam sendo buscados aqui porque
 * alimentam os chips seleccionáveis do grupo "BST" abaixo.
 */

type Lista = { chave: string; rotulo: string; grupo: string; itens: { id: string; extra?: string }[] };
type ResultadoUnico = { escolhidas: Lista[]; linhas: { numero: string; presente_em: string }[] };
type ResultadoDiferenca = { lista: Lista; linhas: { numero: string }[] };

const card: React.CSSProperties = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem 1.1rem" };
const chip = (ativo: boolean): React.CSSProperties => ({
  display: "inline-flex", alignItems: "center", gap: "0.35rem", padding: "0.35rem 0.7rem", borderRadius: 999,
  border: "1px solid var(--border)", background: ativo ? "var(--pill-active-bg)" : "var(--surface-2)",
  color: ativo ? "var(--pill-active-fg)" : "var(--text)", fontSize: "0.8rem", cursor: "pointer",
});

export default function CombinadorListas() {
  const [manejo, setManejo] = useState<any>(null);
  const [agenda, setAgenda] = useState<any>(null);
  const [bst, setBst] = useState<any>(null);
  const [estadosReprodutivos, setEstadosReprodutivos] = useState<any>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [selecionadas, setSelecionadas] = useState<string[]>([]);
  const [operacao, setOperacao] = useState<"uniao" | "intersecao" | "diferenca">("uniao");

  const carregar = () => {
    setCarregando(true); setErro(null);
    Promise.all([fetchRelatoriosManejo(), fetchAgenda(), fetchRelatorioBst(), fetchEstadosReprodutivos()])
      .then(([m, a, b, er]) => { setManejo(m); setAgenda(a); setBst(b); setEstadosReprodutivos(er); })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  };
  useEffect(() => { carregar(); }, []);

  const listas: Lista[] = useMemo(() => {
    if (!manejo && !agenda && !bst && !estadosReprodutivos) return [];
    const deManejo = (chave: string, rotulo: string, campo: keyof any) =>
      ({ chave, rotulo, grupo: "Listas de trabalho", itens: (manejo?.[campo] || []).map((r: any) => ({ id: String(r.numero), extra: r.grupo })) });
    const saida: Lista[] = manejo ? [
      deManejo("pev", "PEV — período de espera voluntário (pós-parto)", "pev"),
      deManejo("a_inseminar", "Aptas a inseminar", "a_inseminar"),
      deManejo("inseminados", "Inseminadas — aguardando diagnóstico", "inseminados"),
      deManejo("a_tocar", "A tocar (diagnóstico de prenhez pendente)", "a_tocar"),
      deManejo("a_reconfirmar", "A reconfirmar diagnóstico (2º toque)", "a_reconfirmar"),
      deManejo("prenhes", "Prenhes confirmadas", "prenhes"),
      deManejo("secagem", "Secagem — próximas (até 60 dias)", "secagem"),
      deManejo("previsao_partos", "Previsão de partos (gestantes reconfirmadas)", "previsao_partos"),
    ] : [];
    if (estadosReprodutivos) {
      saida.push({
        chave: "atrasadas",
        rotulo: "Atrasadas — passaram do prazo máximo para o 1º serviço",
        grupo: "Listas de trabalho",
        itens: (estadosReprodutivos.animais || [])
          .filter((a: any) => a.estado === "atrasada")
          .map((a: any) => ({ id: String(a.numero), extra: a.lote || a.categoria })),
      });
    }
    if (agenda) {
      saida.push(
        { chave: "bst_aptas", rotulo: "BST — aptas à aplicação", grupo: "BST", itens: (agenda.bst_elegiveis || []).map((r: any) => ({ id: String(r.numero_matriz), extra: r.grupo })) },
        { chave: "bst_incluir", rotulo: "BST — a incluir no próximo lote", grupo: "BST", itens: (agenda.bst_nunca_aplicados || []).map((r: any) => ({ id: String(r.numero_matriz), extra: r.grupo })) },
        { chave: "bst_inaptas", rotulo: "BST — inaptas (excluídas do programa)", grupo: "BST", itens: (agenda.bst_excluidos || []).map((r: any) => ({ id: String(r.numero_matriz), extra: r.motivo_exclusao })) },
      );
    }
    if (bst) {
      const porAnimal = new Map<string, string>();
      (bst.aplicacoes || []).forEach((r: any) => { if (!porAnimal.has(r.numero_matriz)) porAnimal.set(r.numero_matriz, r.lote || r.categoria || ""); });
      saida.push({ chave: "bst_aplicados", rotulo: "BST — já aplicadas (histórico)", grupo: "BST", itens: Array.from(porAnimal, ([id, extra]) => ({ id, extra })) });
    }
    return saida;
  }, [manejo, agenda, bst, estadosReprodutivos]);

  const gruposComEcho = useMemo(() => {
    const g: Record<string, Lista[]> = {};
    listas.forEach((l) => { (g[l.grupo] = g[l.grupo] || []).push(l); });
    return g;
  }, [listas]);

  const toggle = (chave: string) => setSelecionadas((s) => s.includes(chave) ? s.filter((c) => c !== chave) : [...s, chave]);

  // União/Interseção: um único resultado agregando todas as listas escolhidas.
  const resultadoUnico: ResultadoUnico | null = useMemo(() => {
    if (selecionadas.length < 2 || operacao === "diferenca") return null;
    const escolhidas = listas.filter((l) => selecionadas.includes(l.chave));
    const conjuntos = escolhidas.map((l) => new Set(l.itens.map((i) => i.id)));
    const idsResultado = operacao === "uniao"
      ? new Set(conjuntos.flatMap((c) => Array.from(c)))
      : new Set(Array.from(conjuntos[0]).filter((id) => conjuntos.every((c) => c.has(id))));
    const linhas = Array.from(idsResultado).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map((id) => ({
      numero: id,
      presente_em: escolhidas.filter((l) => l.itens.some((i) => i.id === id)).map((l) => l.rotulo).join(", "),
    }));
    return { escolhidas, linhas };
  }, [selecionadas, operacao, listas]);
  const ordResultado = useOrdenacao(resultadoUnico?.linhas ?? []);

  // Diferença: NÃO é "só na 1ª lista" — é exclusiva de cada lista escolhida,
  // uma tabela por lista (itens dela que não estão em NENHUMA das outras
  // selecionadas). Por isso não dá pra usar um único `resultado` como
  // União/Interseção: o resultado aqui é um array, um item por lista.
  const resultadosDiferenca: ResultadoDiferenca[] | null = useMemo(() => {
    if (selecionadas.length < 2 || operacao !== "diferenca") return null;
    const escolhidas = listas.filter((l) => selecionadas.includes(l.chave));
    return escolhidas.map((alvo, idx) => {
      const idsAlvo = new Set(alvo.itens.map((i) => i.id));
      const idsOutras = new Set(escolhidas.filter((_, i) => i !== idx).flatMap((l) => l.itens.map((i) => i.id)));
      const linhas = Array.from(idsAlvo)
        .filter((id) => !idsOutras.has(id))
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
        .map((id) => ({ numero: id }));
      return { lista: alvo, linhas };
    });
  }, [selecionadas, operacao, listas]);

  if (carregando) return <p style={{ color: "var(--text-muted)" }}>Carregando listas…</p>;
  if (erro) return <p style={{ color: "var(--red)" }}>{erro}</p>;

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <div style={card}>
        <div className="flex items-center justify-between" style={{ marginBottom: "0.7rem" }}>
          <div className="flex items-center gap-2" style={{ fontWeight: 700, fontSize: "0.95rem" }}>
            <Combine size={16} style={{ color: "var(--accent-icon)" }} /> Combinador de listas
          </div>
          <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={carregar}><RefreshCw size={13} /> Atualizar</button>
        </div>
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
          Escolha 2 ou mais listas para cruzar por número do animal, e o tipo de cruzamento. O resultado pode ser exportado.
        </p>

        {Object.entries(gruposComEcho).map(([grupo, ls]) => (
          <div key={grupo} style={{ marginBottom: "0.6rem" }}>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: "0.3rem" }}>{grupo}</p>
            <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
              {ls.map((l) => (
                <button key={l.chave} type="button" style={chip(selecionadas.includes(l.chave))} onClick={() => toggle(l.chave)}>
                  {l.rotulo} <span style={{ opacity: 0.75 }}>({l.itens.length})</span>
                </button>
              ))}
            </div>
          </div>
        ))}

        <div className="flex items-center gap-3 mt-3" style={{ flexWrap: "wrap" }}>
          <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Cruzamento:</label>
          {([
            { v: "uniao", label: "União (está em qualquer uma)" },
            { v: "intersecao", label: "Interseção (está em todas)" },
            { v: "diferenca", label: "Diferença (exclusivo de cada lista)" },
          ] as const).map((op) => (
            <button key={op.v} type="button" style={chip(operacao === op.v)} onClick={() => setOperacao(op.v)}>{op.label}</button>
          ))}
        </div>

        {selecionadas.length < 2 ? (
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.8rem" }}>Selecione ao menos 2 listas para combinar.</p>
        ) : operacao === "diferenca" ? (
          resultadosDiferenca && (
            <div style={{ marginTop: "0.9rem", display: "grid", gap: "1rem" }}>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                Diferença funciona diferente de União/Interseção: em vez de um resultado único, calcula — para cada lista
                selecionada — quem está só nela e em nenhuma das outras. Por isso aparece {resultadosDiferenca.length} tabela(s) abaixo, uma por lista.
              </p>
              {resultadosDiferenca.map((r) => (
                <div key={r.lista.chave}>
                  <div className="flex items-center justify-between mb-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                    <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>
                      Só em "{r.lista.rotulo}" ({r.linhas.length}) <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>— não está em nenhuma das outras selecionadas</span>
                    </span>
                    <ExportarBotoes
                      titulo={`Diferença — só em ${r.lista.rotulo}`}
                      colunas={[{ header: "Número", key: "numero" }]}
                      linhas={r.linhas}
                      nomeArquivoBase={`combinador_diferenca_${r.lista.chave}`}
                    />
                  </div>
                  {r.linhas.length === 0 ? (
                    <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Nenhum animal exclusivo desta lista.</p>
                  ) : (
                    <div style={{ overflowX: "auto", maxHeight: 260, overflowY: "auto" }}>
                      <table className="fazenda-table">
                        <thead><tr><th>Número</th></tr></thead>
                        <tbody>
                          {r.linhas.map((l) => <tr key={l.numero}><td>{l.numero}</td></tr>)}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )
        ) : resultadoUnico && (
          <div style={{ marginTop: "0.9rem" }}>
            <div className="flex items-center justify-between mb-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
              <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{resultadoUnico.linhas.length} animal(is) no resultado</span>
              <ExportarBotoes
                titulo={`Combinador de listas — ${operacao}`}
                colunas={[{ header: "Número", key: "numero" }, { header: "Presente em", key: "presente_em" }]}
                linhas={resultadoUnico.linhas}
                nomeArquivoBase="combinador_listas"
              />
            </div>
            {resultadoUnico.linhas.length === 0 ? (
              <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Nenhum animal atende ao cruzamento escolhido.</p>
            ) : (
              <div style={{ overflowX: "auto", maxHeight: 360, overflowY: "auto" }}>
                <table className="fazenda-table">
                  <thead><tr>
                    <ThOrdenavel label="Número" campo="numero" coluna={ordResultado.coluna} dir={ordResultado.dir} ordenar={ordResultado.ordenar} />
                    <ThOrdenavel label="Presente em" campo="presente_em" coluna={ordResultado.coluna} dir={ordResultado.dir} ordenar={ordResultado.ordenar} />
                  </tr></thead>
                  <tbody>
                    {ordResultado.linhasOrdenadas.map((r) => (
                      <tr key={r.numero}><td>{r.numero}</td><td style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{r.presente_em}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
