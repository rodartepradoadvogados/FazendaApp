"use client";
// Excluir lançamento — PASSO 2: encontrar o(s) registro(s) do tipo escolhido (aqui: Diagnóstico de gestação).
// Variante desktop de apresentação, página cheia (Captura largura 1800). Dados de exemplo; sem fetch.
//
// Substitui components/exclusao/ListaResultados.tsx (v2): lista de botões sem filtro de data, sem ordenação, sem
// paginação, sem "Editar" e sem o tipo real em "Todos os lançamentos" → TABELA compacta com tudo isso de volta, e a
// seleção em LOTE (que o backend já aceita e o front nunca usou).
//
// A versão ligada a dados precisa preservar:
//  • GET /exclusoes/buscar?tipo&termo&data_inicio&data_fim, com debounce de 250 ms; "Data de/até" SÓ se o tipo não
//    for `sem_filtro_data` (senão os dois campos somem e vão vazios); o termo refina; erro de busca em texto, no topo;
//  • ordenação por coluna (useOrdenacao/ThOrdenavel) e paginação de 50 (usePaginacao/Paginacao); padrão = mais recentes
//    primeiro (o servidor já devolve nessa ordem);
//  • DADO QUE FALTA no payload: o servidor remove `_data` antes de responder → a coluna Data exige expor `data` (ISO) em
//    cada item de /buscar (mudança pequena em `buscar`), senão a coluna sai do `titulo` por regex ("— Toque 17/10/2026");
//  • "Todos os lançamentos": cada item traz `tipo_real`; a coluna "Tipo" (selo com o label do tipo real) aparece SÓ nesse
//    tipo (prop `mostrarOrigem`), e o impacto/lote usam `tipo_real || tipo`;
//  • "Editar em vez de apagar": `destinoEditar(tipo_real || tipo, id)` (22 destinos). Para `diagnostico`, `movimento_lote`,
//    `secagem` etc. NÃO existe destino hoje — proposta: diagnostico → /lancamentos?ir=diagnostico; sem destino o link
//    simplesmente não aparece (como no legado);
//  • "Apagar" numa linha = impacto de UM item (POST /exclusoes/impacto {tipo,id}); caixas + barra = impacto de LOTE
//    (itens[] ≤ 50, SÓ admin; operador não vê caixas nem a barra). Limite 50 em texto, não em erro seco;
//  • tabelas com scope="col", caixas com aria-label, UMA área de rolagem (--gv-altura-tabela).
import React, { useState } from "react";
import { ArrowDown, ArrowLeftRight, ChevronsUpDown, Pencil, Search, Trash2 } from "lucide-react";
import { BarraAcao, Campo, Passo, Selo } from "@/components/gerencial/kit";
import { Migalhas, MolduraExcluir } from "./excluirComum";

type Exame = "Toque" | "Retoque" | "Perda de prenhez";
type Linha = { id: string; data: Date; matriz: string; exame: Exame; resultado: string; detalhe: string; hoje?: boolean };

const HOJE = new Date(2026, 9, 17);
const br = (d: Date) => `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
const dia = (d: Date, delta: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + delta);

// 14 linhas escritas à mão (as de cima aparecem na foto) + o resto gerado de forma determinística até fechar a página de 50.
const FIXAS: { matriz: string; exame: Exame; res: string; metodo?: string; ia: string; d: number }[] = [
  { matriz: "11153", exame: "Toque", res: "POSITIVO", metodo: "Palpação", ia: "28/08/2026", d: 0 },
  { matriz: "3335", exame: "Toque", res: "NEGATIVO", metodo: "Ultrassom", ia: "12/09/2026", d: 0 },
  { matriz: "075", exame: "Retoque", res: "POSITIVO", ia: "05/07/2026", d: -1 },
  { matriz: "9378", exame: "Toque", res: "POSITIVO", metodo: "Palpação", ia: "30/08/2026", d: -1 },
  { matriz: "2210", exame: "Toque", res: "NEGATIVO", metodo: "Cio de repasse", ia: "21/09/2026", d: -2 },
  { matriz: "4471", exame: "Retoque", res: "POSITIVO", ia: "14/07/2026", d: -2 },
  { matriz: "6802", exame: "Perda de prenhez", res: "aborto", ia: "19/05/2026", d: -3 },
  { matriz: "1187", exame: "Toque", res: "POSITIVO", metodo: "Palpação", ia: "25/08/2026", d: -3 },
  { matriz: "3902", exame: "Toque", res: "NEGATIVO", metodo: "Palpação", ia: "03/09/2026", d: -4 },
  { matriz: "5516", exame: "Retoque", res: "NEGATIVO", ia: "28/06/2026", d: -4 },
  { matriz: "0742", exame: "Toque", res: "POSITIVO", metodo: "Ultrassom", ia: "01/09/2026", d: -5 },
  { matriz: "8830", exame: "Toque", res: "POSITIVO", metodo: "Palpação", ia: "27/08/2026", d: -5 },
  { matriz: "2954", exame: "Toque", res: "NEGATIVO", metodo: "Palpação", ia: "10/09/2026", d: -7 },
  { matriz: "7701", exame: "Retoque", res: "POSITIVO", ia: "02/07/2026", d: -8 },
];
const MATRIZES = ["4012", "1650", "9120", "3478", "0861", "5239", "7344", "2096", "6615", "1308", "8472", "4955"];

function montar(): Linha[] {
  const out: Linha[] = FIXAS.map((f, i) => {
    const data = dia(HOJE, f.d);
    const resultado = f.res;
    const detalhe = f.exame === "Perda de prenhez" ? `${resultado} · inseminação de ${f.ia}` : [resultado, f.metodo, `inseminação de ${f.ia}`].filter(Boolean).join(" · ");
    return { id: `${4821 - i}:${f.exame === "Toque" ? "toque" : f.exame === "Retoque" ? "reconfirmacao" : "perda"}`, data, matriz: f.matriz, exame: f.exame, resultado, detalhe, hoje: f.d === 0 };
  });
  for (let i = FIXAS.length; i < 50; i++) {
    const data = dia(HOJE, -9 - Math.floor((i - FIXAS.length) / 2));
    const toque = i % 4 !== 3;
    const pos = i % 3 !== 0;
    const ia = dia(data, toque ? -(38 + (i % 9) * 3) : -(100 + (i % 5) * 4));
    const resultado = pos ? "POSITIVO" : "NEGATIVO";
    out.push({
      id: `${4821 - i}:${toque ? "toque" : "reconfirmacao"}`, data, matriz: MATRIZES[i % MATRIZES.length], exame: toque ? "Toque" : "Retoque", resultado,
      detalhe: [resultado, toque ? (i % 2 ? "Palpação" : "Ultrassom") : null, `inseminação de ${br(ia)}`].filter(Boolean).join(" · "),
    });
  }
  return out;
}
const LINHAS = montar();
const TOTAL = 126;
const LIMITE_LOTE = 50;

const classeRes = (r: string) => (r === "POSITIVO" ? "gx-res-pos" : r === "NEGATIVO" ? "gx-res-neg" : "gx-res-per");

function Detalhe({ l }: { l: Linha }) {
  const [res, ...resto] = l.detalhe.split(" · ");
  return <><span className={classeRes(l.resultado)}>{res}</span>{resto.length > 0 && <span style={{ color: "var(--text-muted)" }}> · {resto.join(" · ")}</span>}</>;
}

export function ExcluirRegistros({ mostrarOrigem = false }: { mostrarOrigem?: boolean }) {
  const [sel, setSel] = useState<Set<string>>(() => new Set([LINHAS[0].id, LINHAS[1].id, LINHAS[2].id]));
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [busca, setBusca] = useState("");

  const alternar = (id: string) => setSel((p) => { const s = new Set(p); if (s.has(id)) s.delete(id); else s.add(id); return s; });
  const todasMarcadas = LINHAS.every((l) => sel.has(l.id));
  const alternarTodas = () => setSel(todasMarcadas ? new Set() : new Set(LINHAS.slice(0, LIMITE_LOTE).map((l) => l.id)));
  const n = sel.size;
  const colunas = 5 + (mostrarOrigem ? 1 : 0);

  return (
    <MolduraExcluir>
      <Migalhas itens={["Tipos", "Diagnósticos de gestação"]} />

      <Passo n={2} id="ex2-p2" titulo="Encontre o registro"
        direita={<span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }} aria-live="polite">{TOTAL} exames · mais recentes primeiro</span>}>
        <div className="gx-filtros">
          <Campo rotulo="Data de" id="ex2-de"><input type="date" value={de} onChange={(e) => setDe(e.target.value)} /></Campo>
          <Campo rotulo="Data até" id="ex2-ate"><input type="date" value={ate} onChange={(e) => setAte(e.target.value)} /></Campo>
          <div className="gv-campo gx-campo-busca">
            <label htmlFor="ex2-busca">Buscar</label>
            <div className="gx-busca" style={{ flex: "none" }}>
              <Search size={14} aria-hidden />
              <input id="ex2-busca" type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="matriz, resultado, método…" style={{ minHeight: "2.1rem" }} />
            </div>
          </div>
          <span className="gv-espaco" style={{ flex: 1 }} />
          <p className="gv-ajuda" style={{ alignSelf: "center" }}>A lista se atualiza sozinha enquanto você digita.</p>
        </div>

        <div className="gx-compara" role="group" aria-label="Diagnóstico ou Serviço / IA">
          <div>
            <div className="gx-compara-topo"><Selo tom="atencao">Este tipo</Selo><b>Diagnóstico de gestação</b></div>
            <p>Desfaz <b>só o exame</b> (toque, retoque ou perda). A inseminação fica e o animal volta a «a tocar».</p>
          </div>
          <div>
            <div className="gx-compara-topo"><Selo tom="neutro">Outro tipo</Selo><b>Serviço / IA</b>
              <span style={{ flex: 1 }} />
              <button type="button" className="gx-acao-linha"><ArrowLeftRight size={13} aria-hidden />Ir para Serviços / IA</button>
            </div>
            <p>Apaga a <b>inseminação inteira</b>, com o diagnóstico dela; a inseminação anterior volta a valer.</p>
          </div>
        </div>

        <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "26rem" }}>
          <table className="gv-tabela">
            <caption className="sr-only" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>Exames de diagnóstico de gestação, do mais recente ao mais antigo</caption>
            <thead>
              <tr>
                <th scope="col" style={{ width: "2.4rem" }}>
                  <input type="checkbox" checked={todasMarcadas} onChange={alternarTodas} aria-label={`Selecionar os ${LIMITE_LOTE} exames desta página (limite do lote)`} />
                </th>
                <th scope="col" aria-sort="descending" style={{ width: "9.5rem" }}>
                  <button type="button" className="gx-th-ord" title="Ordenar por data">Data <ArrowDown size={12} aria-hidden /></button>
                </th>
                <th scope="col" style={{ width: "13rem" }}>
                  <button type="button" className="gx-th-ord" title="Ordenar por registro">Registro <ChevronsUpDown size={12} aria-hidden /></button>
                </th>
                <th scope="col">Detalhe</th>
                {mostrarOrigem && <th scope="col">Tipo</th>}
                <th scope="col" className="gv-dir" style={{ width: "13rem" }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {LINHAS.map((l) => {
                const marcada = sel.has(l.id);
                return (
                  <tr key={l.id} className={marcada ? "gv-linha-marcada" : undefined}>
                    <td><input type="checkbox" checked={marcada} onChange={() => alternar(l.id)} aria-label={`Selecionar ${l.exame} de ${l.matriz} em ${br(l.data)}`} /></td>
                    <td className="gv-num">{br(l.data)} {l.hoje && <Selo tom="info">Hoje</Selo>}</td>
                    <td><b className="gv-num">{l.matriz}</b> <span style={{ color: "var(--text-muted)" }}>· {l.exame}</span></td>
                    <td className="gv-quebra"><Detalhe l={l} /></td>
                    {mostrarOrigem && <td><Selo tom="neutro">Diagnóstico</Selo></td>}
                    <td className="gv-dir">
                      <a href="#editar" className="gx-acao-linha" style={{ marginRight: "0.35rem" }} aria-label={`Editar em vez de apagar: ${l.exame} de ${l.matriz}`}><Pencil size={12} aria-hidden />Editar</a>
                      <button type="button" className="gx-acao-linha" data-perigo="true" aria-label={`Apagar ${l.exame} de ${l.matriz} em ${br(l.data)}`}><Trash2 size={12} aria-hidden />Apagar</button>
                    </td>
                  </tr>
                );
              })}
              {LINHAS.length === 0 && <tr><td colSpan={colunas} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1.5rem" }}>Nenhum registro encontrado.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="gx-pag">
          <span>Mostrando <b>1–50</b> de <b>{TOTAL}</b></span>
          <span className="gx-pag-botoes" role="group" aria-label="Páginas">
            <button type="button" disabled aria-label="Página anterior">‹</button>
            <button type="button" aria-current="page">1</button>
            <button type="button">2</button>
            <button type="button">3</button>
            <button type="button" aria-label="Próxima página">›</button>
          </span>
          <span style={{ flex: 1 }} />
          <label htmlFor="ex2-tam">Por página</label>
          <select id="ex2-tam" defaultValue="50" style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border-strong, var(--border))", borderRadius: "var(--r-sm)", padding: "0.25rem 0.4rem", font: "inherit" }}>
            <option>25</option><option>50</option><option>100</option>
          </select>
        </div>
        <p className="gv-ajuda">Marque vários exames para apagar de uma vez (só administrador, até {LIMITE_LOTE} por lote). Para só corrigir o resultado, use “Editar” em vez de apagar.</p>
      </Passo>

      <BarraAcao
        resumo={`${n} ${n === 1 ? "selecionado" : "selecionados"} · máx. ${LIMITE_LOTE} por lote`}
        detalhe={n > 0 ? "Cada exame é desfeito sozinho; as inseminações ficam. Você confere o impacto do lote antes de confirmar." : "Marque as caixas para apagar em lote."}
        secundaria={<button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={n === 0}>Limpar seleção</button>}
        acao={<button type="button" className="btn-primary" disabled={n === 0 || n > LIMITE_LOTE}>Ver impacto do lote ({n})</button>}
      />
    </MolduraExcluir>
  );
}
