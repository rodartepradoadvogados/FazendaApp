"use client";
// Excluir lançamento — PASSO 2: encontrar o(s) registro(s) do tipo escolhido (página cheia). Dados REAIS de
// GET /exclusoes/buscar?tipo&termo&data_inicio&data_fim (debounce de 250 ms; erro em texto no topo).
//
// Preservado da ListaResultados v2 + FormExclusaoLegado (nada se perde):
//  • "Data de/até" SÓ se o tipo não for `sem_filtro_data` (senão somem e vão vazios); o termo refina;
//  • ordenação por coluna (Data, Registro) e paginação (25/50/100; padrão 50); padrão = a ordem do servidor (mais recentes);
//  • coluna Data vem de `data` (ISO) do servidor; a coluna "Tipo" (selo com o tipo REAL) aparece SÓ em "Todos os lançamentos"
//    e o impacto/lote usam `tipo_real || tipo`;
//  • "Editar em vez de apagar": destinoEditar(tipo_real || tipo, id) — sem destino o link simplesmente não aparece;
//  • "Apagar" numa linha = impacto de UM item; caixas + barra = impacto de LOTE (itens[] ≤ 50, SÓ admin: operador não vê
//    caixas nem a barra). O limite 50 é dito em texto, não em erro seco;
//  • depois de apagar a tela volta aqui com a lista recarregada e a barra mostra o retorno (comprovante / pedido enviado);
//  • UMA área de rolagem (--gv-altura-tabela), tabela com scope="col" e aria-label nas caixas.
import React, { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowLeftRight, ArrowUp, Check, ChevronsUpDown, Pencil, Search, Trash2 } from "lucide-react";
import { BarraAcao, Campo, Passo, Selo } from "@/components/gerencial/kit";
import { buscarExclusao } from "@/lib/api";
import { destinoEditar } from "@/lib/exclusao";
import {
  LIMITE_LOTE, alternarPagina, alternarSelecao, botoesPagina, chaveRegistro, dataBr, dataDoRegistro, ordenarRegistros,
  paginar, podarSelecao, proximaOrdem, tetoDaBusca, tipoDoRegistro, tituloSemData,
  type ColunaOrdem, type Ordem, type RegistroBusca, type Retorno, type Selecao, type TipoApi,
} from "@/lib/exclusaoTela";
import { Migalhas } from "./excluirComum";

const PERDAS = new Set(["aborto", "natimorto", "outros", "motivo não informado", "motivo pendente"]);

/** Subtítulo com o 1º termo em destaque quando ele é o RESULTADO de um exame (texto + cor, nunca só cor). */
function Detalhe({ r, tipoReal }: { r: RegistroBusca; tipoReal: string }) {
  const [primeiro, ...resto] = (r.subtitulo || "").split(" · ");
  const cls = tipoReal !== "diagnostico" ? null
    : primeiro === "POSITIVO" ? "gx-res-pos" : primeiro === "NEGATIVO" ? "gx-res-neg" : PERDAS.has(primeiro) ? "gx-res-per" : null;
  if (!cls) return <>{r.subtitulo}</>;
  return <><span className={cls}>{primeiro}</span>{resto.length > 0 && <span style={{ color: "var(--text-muted)" }}> · {resto.join(" · ")}</span>}</>;
}

function CabOrdenavel({ rotulo, coluna, ordem, onOrdenar, largura }: { rotulo: string; coluna: ColunaOrdem; ordem: Ordem; onOrdenar: (c: ColunaOrdem) => void; largura?: string }) {
  const ativa = ordem?.coluna === coluna;
  // Sem clique ainda, a lista já está do mais recente ao mais antigo (ordem do servidor): a Data mostra isso.
  const seta = ativa ? (ordem!.dir === 1 ? <ArrowUp size={12} aria-hidden /> : <ArrowDown size={12} aria-hidden />)
    : coluna === "data" && !ordem ? <ArrowDown size={12} aria-hidden /> : <ChevronsUpDown size={12} aria-hidden />;
  const sort = ativa ? (ordem!.dir === 1 ? "ascending" : "descending") : coluna === "data" && !ordem ? "descending" : "none";
  return (
    <th scope="col" aria-sort={sort} style={largura ? { width: largura } : undefined}>
      <button type="button" className="gx-th-ord" title={`Ordenar por ${rotulo.toLowerCase()}`} onClick={() => onOrdenar(coluna)}>{rotulo} {seta}</button>
    </th>
  );
}

export function ExcluirRegistros({
  tipo, tipos, souAdmin, recarga, retorno, calculando, erro, onVoltarTipos, onEscolherTipo, onApagar, onLote, onAtalho, onFecharRetorno,
}: {
  tipo: TipoApi;
  tipos: TipoApi[];
  souAdmin: boolean;
  /** Sobe a cada exclusão concluída: recarrega a lista e limpa a seleção. */
  recarga: number;
  retorno: Retorno | null;
  /** Calculando o impacto (pedido ao servidor em andamento). */
  calculando: boolean;
  erro: string | null;
  onVoltarTipos: () => void;
  onEscolherTipo: (t: TipoApi) => void;
  onApagar: (r: RegistroBusca) => void;
  onLote: (sel: Selecao) => void;
  onAtalho: (a: "trilha" | "pedidos") => void;
  onFecharRetorno: () => void;
}) {
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [busca, setBusca] = useState("");
  const [lista, setLista] = useState<RegistroBusca[]>([]);
  const [buscando, setBuscando] = useState(true);
  const [erroBusca, setErroBusca] = useState<string | null>(null);
  const [ordem, setOrdem] = useState<Ordem>(null);
  const [pagina, setPagina] = useState(1);
  const [tamanho, setTamanho] = useState(50);
  const [sel, setSel] = useState<Selecao>(new Map());
  const [avisoLimite, setAvisoLimite] = useState(false);

  const semData = !!tipo.sem_filtro_data;
  const ehTodos = tipo.id === "todos_lancamentos";
  const seq = useRef(0);
  const ultimoFiltro = useRef<string | null>(null);

  // Busca: debounce de 250 ms só quando o FILTRO muda (digitando); entrar no passo ou recarregar após apagar é imediato.
  useEffect(() => {
    const filtro = JSON.stringify([tipo.id, busca, semData ? "" : de, semData ? "" : ate]);
    const imediato = ultimoFiltro.current === null || ultimoFiltro.current === filtro;
    ultimoFiltro.current = filtro;
    const h = setTimeout(async () => {
      const eu = ++seq.current;
      setBuscando(true); setErroBusca(null);
      try {
        const r = (await buscarExclusao(tipo.id, busca, semData ? "" : de, semData ? "" : ate)) as RegistroBusca[];
        if (eu !== seq.current) return; // chegou uma resposta mais nova
        setLista(r);
        setPagina(1);
        setSel((s) => podarSelecao(s, r, tipo.id));
      } catch (e: any) {
        if (eu === seq.current) { setErroBusca(e.message || "Erro na busca"); setLista([]); }
      } finally {
        if (eu === seq.current) setBuscando(false);
      }
    }, imediato ? 0 : 250);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tipo.id, busca, de, ate, semData, recarga]);

  // Depois de apagar (ou enviar o pedido) a seleção recomeça do zero.
  useEffect(() => { setSel(new Map()); setAvisoLimite(false); }, [recarga]);

  const ordenada = ordenarRegistros(lista, ordem);
  const pag = paginar(ordenada, pagina, tamanho);

  const n = sel.size;
  const todasMarcadas = pag.linhas.length > 0 && pag.linhas.every((r) => sel.has(chaveRegistro(r, tipo.id)));
  const algumasMarcadas = !todasMarcadas && pag.linhas.some((r) => sel.has(chaveRegistro(r, tipo.id)));
  const colunas = 4 + (souAdmin ? 1 : 0) + (ehTodos ? 1 : 0);
  const teto = tetoDaBusca(tipo.id);
  const rotuloTipo = (id: string) => tipos.find((t) => t.id === id)?.label ?? id;
  const outroTipoServico = tipos.find((t) => t.id === "servico");

  const marcar = (r: RegistroBusca) => {
    const x = alternarSelecao(sel, chaveRegistro(r, tipo.id), r);
    setSel(x.sel); setAvisoLimite(x.estourou);
  };
  const marcarPagina = () => {
    const x = alternarPagina(sel, pag.linhas, tipo.id);
    setSel(x.sel); setAvisoLimite(x.estourou);
  };

  const ordenarPor = (c: ColunaOrdem) => { setOrdem((o) => proximaOrdem(o, c)); setPagina(1); };
  const nome = tipo.plural ? tipo.plural.charAt(0).toUpperCase() + tipo.plural.slice(1) : tipo.label;
  const contagemTxt = buscando ? "Buscando…"
    : `${lista.length} ${lista.length === 1 ? "registro" : "registros"}${lista.length >= teto ? ` (os ${teto} mais recentes — refine por data ou busca)` : ""} · ${ordem ? "ordem escolhida" : "mais recentes primeiro"}`;

  const barraRetorno = retorno && (
    <>
      <span className="gx-ok" role="status" data-tom={retorno.tom}><Check size={14} aria-hidden /> {retorno.texto}</span>
      {retorno.comprovante && <span>Comprovante <span className="gx-comprovante">{retorno.comprovante}</span></span>}
      {retorno.tom === "ok" && <span style={{ color: "var(--text-muted)" }}>Ficou na trilha: quem, quando e o quê (guardada por 30 dias).</span>}
      {retorno.detalhes.map((d, i) => <span key={i} style={{ color: "var(--text-muted)" }}>{d}</span>)}
      <span style={{ flex: 1 }} />
      {retorno.atalho === "trilha" && souAdmin && <button type="button" className="gx-acao-linha" onClick={() => onAtalho("trilha")}>Ver na trilha</button>}
      {retorno.atalho === "pedidos" && <button type="button" className="gx-acao-linha" onClick={() => onAtalho("pedidos")}>{souAdmin ? "Ver pedidos" : "Ver meus pedidos"}</button>}
      <button type="button" className="gx-acao-linha" onClick={onFecharRetorno}>Fechar</button>
    </>
  );

  return (
    <>
      <Migalhas itens={[{ texto: "Tipos", aoClicar: onVoltarTipos }, { texto: nome }]} />

      {!souAdmin && barraRetorno && <div className="gx-retorno-op" aria-live="polite">{barraRetorno}</div>}

      <Passo n={2} id="ex2-p2" titulo="Encontre o registro"
        direita={<span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }} aria-live="polite">{contagemTxt}</span>}>
        {(erro || erroBusca) && <div className="gv-aviso" role="alert" data-tom="erro"><span>{erro || erroBusca}</span></div>}

        <div className="gx-filtros">
          {!semData && (
            <>
              <Campo rotulo="Data de" id="ex2-de"><input type="date" value={de} onChange={(e) => setDe(e.target.value)} /></Campo>
              <Campo rotulo="Data até" id="ex2-ate"><input type="date" value={ate} onChange={(e) => setAte(e.target.value)} /></Campo>
            </>
          )}
          <div className="gv-campo gx-campo-busca">
            <label htmlFor="ex2-busca">Buscar</label>
            <div className="gx-busca" style={{ flex: "none" }}>
              <Search size={14} aria-hidden />
              <input id="ex2-busca" type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="lote, medicamento, ação, número, nome…" style={{ minHeight: "2.1rem" }} />
            </div>
          </div>
          <span className="gv-espaco" style={{ flex: 1 }} />
          <p className="gv-ajuda" style={{ alignSelf: "center" }}>A lista se atualiza sozinha enquanto você digita.</p>
        </div>

        {tipo.id === "diagnostico" && (
          <div className="gx-compara" role="group" aria-label="Diagnóstico ou Serviço / IA">
            <div>
              <div className="gx-compara-topo"><Selo tom="atencao">Este tipo</Selo><b>Diagnóstico de gestação</b></div>
              <p>Desfaz <b>só o exame</b> (toque, retoque ou perda). A inseminação fica e o animal volta a «a tocar».</p>
            </div>
            <div>
              <div className="gx-compara-topo"><Selo tom="neutro">Outro tipo</Selo><b>Serviço / IA</b>
                <span style={{ flex: 1 }} />
                {outroTipoServico && <button type="button" className="gx-acao-linha" onClick={() => onEscolherTipo(outroTipoServico)}><ArrowLeftRight size={13} aria-hidden />Ir para Serviços / IA</button>}
              </div>
              <p>Apaga a <b>inseminação inteira</b>, com o diagnóstico dela; a inseminação anterior volta a valer.</p>
            </div>
          </div>
        )}

        <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "26rem" }}>
          <table className="gv-tabela">
            <caption style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>{`${nome}: registros encontrados`}</caption>
            <thead>
              <tr>
                {souAdmin && (
                  <th scope="col" style={{ width: "2.4rem" }}>
                    <input type="checkbox" checked={todasMarcadas} ref={(el) => { if (el) el.indeterminate = algumasMarcadas; }} onChange={marcarPagina}
                      disabled={pag.linhas.length === 0}
                      aria-label={`Selecionar os registros desta página (limite do lote: ${LIMITE_LOTE})`} />
                  </th>
                )}
                <CabOrdenavel rotulo="Data" coluna="data" ordem={ordem} onOrdenar={ordenarPor} largura="9.5rem" />
                <CabOrdenavel rotulo="Registro" coluna="titulo" ordem={ordem} onOrdenar={ordenarPor} />
                <th scope="col">Detalhe</th>
                {ehTodos && <th scope="col">Tipo</th>}
                <th scope="col" className="gv-dir" style={{ width: "13rem" }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {pag.linhas.map((r) => {
                const chave = chaveRegistro(r, tipo.id);
                const tr = tipoDoRegistro(r, tipo.id);
                const marcada = sel.has(chave);
                const iso = dataDoRegistro(r);
                const hoje = iso === new Date().toLocaleDateString("sv-SE");
                const href = destinoEditar(tr, String(r.id));
                const t = tituloSemData(r);
                return (
                  <tr key={chave} className={marcada ? "gv-linha-marcada" : undefined}>
                    {souAdmin && <td><input type="checkbox" checked={marcada} onChange={() => marcar(r)} aria-label={`Selecionar ${r.titulo}`} /></td>}
                    <td className="gv-num">{dataBr(iso)} {hoje && <Selo tom="info">Hoje</Selo>}</td>
                    <td className="gv-quebra" title={r.titulo}><b>{t}</b></td>
                    <td className="gv-quebra"><Detalhe r={r} tipoReal={tr} /></td>
                    {ehTodos && <td><Selo tom="neutro">{rotuloTipo(tr)}</Selo></td>}
                    <td className="gv-dir">
                      {href && (
                        <a href={href} className="gx-acao-linha" style={{ marginRight: "0.35rem" }} aria-label={`Editar em vez de apagar: ${r.titulo}`}><Pencil size={12} aria-hidden />Editar</a>
                      )}
                      <button type="button" className="gx-acao-linha" data-perigo="true" disabled={calculando} onClick={() => onApagar(r)} aria-label={`Apagar ${r.titulo}`}>
                        <Trash2 size={12} aria-hidden />Apagar
                      </button>
                    </td>
                  </tr>
                );
              })}
              {!buscando && lista.length === 0 && (
                <tr><td colSpan={colunas} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1.5rem" }}>Nenhum registro encontrado.</td></tr>
              )}
              {buscando && lista.length === 0 && (
                <tr><td colSpan={colunas} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1.5rem" }}>Buscando…</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {lista.length > 0 && (
          <div className="gx-pag">
            <span>Mostrando <b>{pag.de}–{pag.ate}</b> de <b>{pag.total}</b></span>
            <span className="gx-pag-botoes" role="group" aria-label="Páginas">
              <button type="button" disabled={pag.pagina <= 1} aria-label="Página anterior" onClick={() => setPagina(pag.pagina - 1)}>‹</button>
              {botoesPagina(pag.pagina, pag.paginas).map((b, i) => b === "…"
                ? <span key={`e${i}`} aria-hidden style={{ alignSelf: "center" }}>…</span>
                : <button key={b} type="button" aria-current={b === pag.pagina ? "page" : undefined} onClick={() => setPagina(b)}>{b}</button>)}
              <button type="button" disabled={pag.pagina >= pag.paginas} aria-label="Próxima página" onClick={() => setPagina(pag.pagina + 1)}>›</button>
            </span>
            <span style={{ flex: 1 }} />
            <label htmlFor="ex2-tam">Por página</label>
            <select id="ex2-tam" value={tamanho} onChange={(e) => { setTamanho(Number(e.target.value)); setPagina(1); }}
              style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border-strong, var(--border))", borderRadius: "var(--r-sm)", padding: "0.25rem 0.4rem", font: "inherit" }}>
              <option value={25}>25</option><option value={50}>50</option><option value={100}>100</option>
            </select>
          </div>
        )}
        <p className="gv-ajuda">
          {souAdmin
            ? <>Marque vários registros para apagar de uma vez (só administrador, até {LIMITE_LOTE} por lote). </>
            : <>Seu pedido de exclusão vai para o administrador decidir. </>}
          Para só corrigir um dado, use “Editar” em vez de apagar.
        </p>
        {avisoLimite && <p className="gv-ajuda" role="status" style={{ color: "var(--ft-ambar)", fontWeight: 700 }}>O lote aceita no máximo {LIMITE_LOTE} registros por vez: apague estes e depois marque os próximos.</p>}
      </Passo>

      {souAdmin && (
        <BarraAcao
          retorno={barraRetorno || undefined}
          resumo={calculando ? "Calculando o impacto…" : `${n} ${n === 1 ? "selecionado" : "selecionados"} · máx. ${LIMITE_LOTE} por lote`}
          detalhe={n > 0
            ? (tipo.id === "diagnostico" ? "Cada exame é desfeito sozinho; as inseminações ficam. Você confere o impacto do lote antes de confirmar." : "Você confere o impacto do lote antes de confirmar.")
            : "Marque as caixas para apagar em lote."}
          secundaria={<button type="button" className="btn-ghost" onClick={() => { setSel(new Map()); setAvisoLimite(false); }} disabled={n === 0}>Limpar seleção</button>}
          acao={<button type="button" className="btn-primary-gold" disabled={n === 0 || n > LIMITE_LOTE || calculando} onClick={() => onLote(sel)}>Ver impacto do lote ({n})</button>}
        />
      )}
    </>
  );
}
