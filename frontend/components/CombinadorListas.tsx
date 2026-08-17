"use client";
import { useEffect, useMemo, useState } from "react";
import { Combine, RefreshCw, Droplets } from "lucide-react";
import { fetchRelatoriosManejo, fetchAgenda, fetchRelatorioBst } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

/**
 * Listas Gerenciais — a "Lista de BST" (quem está apta,
 * quem entra no próximo BST, quem está inapta e o histórico de aplicação) e
 * o Combinador de listas: escolhe 2+ listas de trabalho já existentes no
 * site e cruza por número do animal (união, interseção ou diferença),
 * exportando o resultado em Excel/PDF. Tudo client-side: reaproveita os
 * mesmos endpoints já usados em Listas de Trabalho, Agenda e Produção > BST
 * — não duplica cálculo nenhum, só recombina o que já existe.
 */

type Lista = { chave: string; rotulo: string; grupo: string; itens: { id: string; extra?: string }[] };

const card: React.CSSProperties = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "1rem 1.1rem" };
const chip = (ativo: boolean): React.CSSProperties => ({
  display: "inline-flex", alignItems: "center", gap: "0.35rem", padding: "0.35rem 0.7rem", borderRadius: 999,
  border: "1px solid var(--border)", background: ativo ? "var(--pill-active-bg)" : "var(--surface-2)",
  color: ativo ? "var(--pill-active-fg)" : "var(--text)", fontSize: "0.8rem", cursor: "pointer",
});

export default function CombinadorListas() {
  const [manejo, setManejo] = useState<any>(null);
  const [agenda, setAgenda] = useState<any>(null);
  const [bst, setBst] = useState<any>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [selecionadas, setSelecionadas] = useState<string[]>([]);
  const [operacao, setOperacao] = useState<"uniao" | "intersecao" | "diferenca">("uniao");

  const carregar = () => {
    setCarregando(true); setErro(null);
    Promise.all([fetchRelatoriosManejo(), fetchAgenda(), fetchRelatorioBst()])
      .then(([m, a, b]) => { setManejo(m); setAgenda(a); setBst(b); })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  };
  useEffect(() => { carregar(); }, []);

  const listas: Lista[] = useMemo(() => {
    if (!manejo && !agenda && !bst) return [];
    const deManejo = (chave: string, rotulo: string, campo: keyof any) =>
      ({ chave, rotulo, grupo: "Listas de trabalho", itens: (manejo?.[campo] || []).map((r: any) => ({ id: String(r.numero), extra: r.grupo })) });
    const saida: Lista[] = manejo ? [
      deManejo("pev", "PEV (pós-parto)", "pev"),
      deManejo("a_inseminar", "A inseminar", "a_inseminar"),
      deManejo("inseminados", "Inseminados", "inseminados"),
      deManejo("a_tocar", "A tocar", "a_tocar"),
      deManejo("a_reconfirmar", "A reconfirmar", "a_reconfirmar"),
      deManejo("prenhes", "Prenhes", "prenhes"),
      deManejo("secagem", "Secagem", "secagem"),
      deManejo("previsao_partos", "Previsão de partos", "previsao_partos"),
    ] : [];
    if (agenda) {
      saida.push(
        { chave: "bst_aptas", rotulo: "BST — Aptas", grupo: "BST", itens: (agenda.bst_elegiveis || []).map((r: any) => ({ id: String(r.numero_matriz), extra: r.grupo })) },
        { chave: "bst_incluir", rotulo: "BST — Incluir no próximo", grupo: "BST", itens: (agenda.bst_nunca_aplicados || []).map((r: any) => ({ id: String(r.numero_matriz), extra: r.grupo })) },
        { chave: "bst_inaptas", rotulo: "BST — Inaptas", grupo: "BST", itens: (agenda.bst_excluidos || []).map((r: any) => ({ id: String(r.numero_matriz), extra: r.motivo_exclusao })) },
      );
    }
    if (bst) {
      const porAnimal = new Map<string, string>();
      (bst.aplicacoes || []).forEach((r: any) => { if (!porAnimal.has(r.numero_matriz)) porAnimal.set(r.numero_matriz, r.lote || r.categoria || ""); });
      saida.push({ chave: "bst_aplicados", rotulo: "BST — Já aplicados (histórico)", grupo: "BST", itens: Array.from(porAnimal, ([id, extra]) => ({ id, extra })) });
    }
    return saida;
  }, [manejo, agenda, bst]);

  const gruposComEcho = useMemo(() => {
    const g: Record<string, Lista[]> = {};
    listas.forEach((l) => { (g[l.grupo] = g[l.grupo] || []).push(l); });
    return g;
  }, [listas]);

  const toggle = (chave: string) => setSelecionadas((s) => s.includes(chave) ? s.filter((c) => c !== chave) : [...s, chave]);

  const resultado = useMemo(() => {
    if (selecionadas.length < 2) return null;
    const escolhidas = listas.filter((l) => selecionadas.includes(l.chave));
    const conjuntos = escolhidas.map((l) => new Set(l.itens.map((i) => i.id)));
    let idsResultado: Set<string>;
    if (operacao === "uniao") {
      idsResultado = new Set(conjuntos.flatMap((c) => Array.from(c)));
    } else if (operacao === "intersecao") {
      idsResultado = new Set(Array.from(conjuntos[0]).filter((id) => conjuntos.every((c) => c.has(id))));
    } else {
      idsResultado = new Set(Array.from(conjuntos[0]).filter((id) => !conjuntos.slice(1).some((c) => c.has(id))));
    }
    const linhas = Array.from(idsResultado).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map((id) => ({
      numero: id,
      presente_em: escolhidas.filter((l) => l.itens.some((i) => i.id === id)).map((l) => l.rotulo).join(", "),
    }));
    return { escolhidas, linhas };
  }, [selecionadas, operacao, listas]);
  const ordResultado = useOrdenacao(resultado?.linhas ?? []);

  const bstAptas = agenda?.bst_elegiveis || [];
  const bstIncluir = agenda?.bst_nunca_aplicados || [];
  const bstInaptas = agenda?.bst_excluidos || [];
  const bstAplicados = bst?.aplicacoes || [];

  if (carregando) return <p style={{ color: "var(--text-muted)" }}>Carregando listas…</p>;
  if (erro) return <p style={{ color: "var(--red)" }}>{erro}</p>;

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      {/* Combinador de listas */}
      <div style={card}>
        <div className="flex items-center gap-2" style={{ fontWeight: 700, fontSize: "0.95rem", marginBottom: "0.7rem" }}>
          <Combine size={16} style={{ color: "var(--accent-icon)" }} /> Combinador de listas
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
            { v: "diferenca", label: "Diferença (só na 1ª, exclui as demais)" },
          ] as const).map((op) => (
            <button key={op.v} type="button" style={chip(operacao === op.v)} onClick={() => setOperacao(op.v)}>{op.label}</button>
          ))}
        </div>

        {selecionadas.length < 2 ? (
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.8rem" }}>Selecione ao menos 2 listas para combinar.</p>
        ) : resultado && (
          <div style={{ marginTop: "0.9rem" }}>
            <div className="flex items-center justify-between mb-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
              <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{resultado.linhas.length} animal(is) no resultado</span>
              <ExportarBotoes
                titulo={`Combinador de listas — ${operacao}`}
                colunas={[{ header: "Número", key: "numero" }, { header: "Presente em", key: "presente_em" }]}
                linhas={resultado.linhas}
                nomeArquivoBase="combinador_listas"
              />
            </div>
            {resultado.linhas.length === 0 ? (
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

      {/* Lista de BST */}
      <div style={card}>
        <div className="flex items-center justify-between" style={{ marginBottom: "0.7rem" }}>
          <div className="flex items-center gap-2" style={{ fontWeight: 700, fontSize: "0.95rem" }}>
            <Droplets size={16} style={{ color: "var(--accent-icon)" }} /> Lista de BST
          </div>
          <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={carregar}><RefreshCw size={13} /> Atualizar</button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {[
            { titulo: "Aptas", linhas: bstAptas, cor: "var(--green-light)" },
            { titulo: "Incluir no próximo BST", linhas: bstIncluir, cor: "var(--dourado-light)" },
            { titulo: "Inaptas", linhas: bstInaptas, cor: "var(--red)" },
            { titulo: "Já aplicados (histórico)", linhas: bstAplicados, cor: "var(--text-muted)" },
          ].map((bloco) => (
            <div key={bloco.titulo} style={{ background: "var(--surface-2)", borderRadius: 8, padding: "0.7rem" }}>
              <div className="flex items-center justify-between" style={{ marginBottom: "0.4rem" }}>
                <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>{bloco.titulo}</span>
                <span style={{ fontSize: "0.78rem", fontWeight: 700, color: bloco.cor }}>{bloco.linhas.length}</span>
              </div>
              {bloco.linhas.length === 0 ? (
                <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Nenhum animal.</p>
              ) : (
                <div style={{ maxHeight: 160, overflowY: "auto" }}>
                  <table className="fazenda-table" style={{ fontSize: "0.76rem" }}>
                    <tbody>
                      {bloco.linhas.map((r: any, i: number) => (
                        <tr key={i}>
                          <td>{r.numero_matriz}</td>
                          <td style={{ color: "var(--text-muted)" }}>{r.grupo || r.lote || r.categoria || r.motivo_exclusao || ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
