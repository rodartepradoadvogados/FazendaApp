"use client";
// Excluir lançamento — PASSO 3: conferir o impacto e decidir (página cheia). Dados REAIS de POST /exclusoes/impacto
// (um registro: {tipo,id}; lote: {itens[]}, ≤ 50, só admin). O resultado (excluído / pedido enviado) volta ao passo 2, na barra.
//
// Preservado do PainelImpacto + DecisaoExclusao + ResultadoExclusao v2:
//  • item{tipo,id,titulo}, bloqueia[], apagar[], reverter[], avisos[], risco, porque[], editar_url (+ qtd/valor/filhos/chip);
//  • bloqueado (`bloqueia.length > 0`): some a decisão, fica SÓ "Voltar" e o texto do que fazer (`bloqueia[].fazer`); em lote
//    não se confirma com bloqueio: o servidor PULARIA o item bloqueado, a tela manda desmarcá-lo (decisão conservadora);
//  • risco proporcional (o servidor repete tudo): baixo = só o botão; médio = motivo obrigatório (operador SEMPRE motivo);
//    alto = motivo + digitar a confirmação ("APAGAR"; ficha de animal: o número → confirmacaoEsperada). `porque` entra no texto;
//  • "Corrigir em vez de apagar" = `editar_url` do impacto ou destinoEditar(tipo, id);
//  • admin exclui na hora; operador GERA PEDIDO e o botão vira "Enviar pedido de exclusão".
import React from "react";
import { AlertTriangle, ArrowLeft, Ban, Check, Pencil, Trash2, Undo2 } from "lucide-react";
import { BarraAcao, BotaoOuro, Campo, Passo, Selo } from "@/components/gerencial/kit";
import { agruparPorNota, confirmacaoEsperada, destinoEditar, porqueDe, riscoItem, totaisImp, type ImpactoExclusao, type LinhaImpacto, type Risco } from "@/lib/exclusao";
import { dataBr, dataDoRegistro, exigencias, nomeCurto, tipoDoRegistro, verboDe, type TipoApi } from "@/lib/exclusaoTela";
import type { Alvo } from "@/components/exclusao/useExclusao";
import { Migalhas } from "./excluirComum";

const ROTULO_RISCO: Record<Risco, string> = { baixo: "Risco baixo", medio: "Risco médio", alto: "Risco alto" };
const NIVEIS: { id: Risco; titulo: string; texto: string }[] = [
  { id: "baixo", titulo: "Baixo", texto: "Um registro isolado, nada mais muda. Basta o botão." },
  { id: "medio", titulo: "Médio", texto: "Mexe em outros dados ou apaga mais de um. Motivo obrigatório." },
  { id: "alto", titulo: "Alto", texto: "Apaga muita coisa ou cadastro em uso. Motivo e digitar APAGAR (ficha de animal: o número)." },
];

const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;
const reais = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function Bloco({ tom, icone, titulo, sub, selo, children }: {
  tom: "bloqueio" | "apagar" | "reverter" | "aviso"; icone: React.ReactNode; titulo: string; sub: string; selo: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <section className="gx-imp" data-tom={tom} aria-label={titulo}>
      <div className="gx-imp-cab">{icone}<b>{titulo}</b><small>{sub}</small>{selo}</div>
      {children}
    </section>
  );
}

function Lista({ itens }: { itens: LinhaImpacto[] }) {
  return (
    <ul>
      {itens.map((l, i) => (
        <li key={`${i}-${l.titulo}`}>
          <b>{l.titulo}{(l.qtd ?? 1) > 1 && <> · {l.qtd}</>}{l.chip && <> <Selo tom="neutro">{l.chip}</Selo></>}</b>
          {l.consequencia && <span>{l.consequencia}</span>}
          {typeof l.valor === "number" && l.valor > 0 && <span>Dinheiro em aberto: {reais(l.valor)}</span>}
          {l.filhos && l.filhos.length > 0 && l.filhos.map((f, j) => <span key={j}>{f}</span>)}
        </li>
      ))}
    </ul>
  );
}

/** Lote: os registros marcados, agrupados por tipo; nas notas do Financeiro as parcelas se juntam pela nota. */
function ResumoLote({ alvo, tipos }: { alvo: Alvo; tipos: TipoApi[] }) {
  const rotulo = (id: string) => { const t = tipos.find((x) => x.id === id); return t ? nomeCurto(t) : id; };
  const porTipo = new Map<string, Alvo["registros"]>();
  alvo.registros.forEach((r) => {
    const t = tipoDoRegistro(r, alvo.tipoLista);
    porTipo.set(t, [...(porTipo.get(t) ?? []), r]);
  });
  return (
    <details className="gx-lote-det">
      <summary>Ver os {alvo.registros.length} registros do lote</summary>
      {[...porTipo.entries()].map(([t, regs]) => {
        const notas = t === "financeiro" ? agruparPorNota(regs.map((r) => ({ r, nota: r.titulo.split(" — ")[0] })), "nota") : null;
        return (
          <div key={t}>
            <div className="gv-rotulo" style={{ marginTop: "0.4rem" }}>{rotulo(t)} · {regs.length}</div>
            <ul>
              {notas
                ? Object.entries(notas).map(([nota, linhas]) => (
                  <li key={nota}><b>{nota}</b> {linhas.length > 1 ? `· ${linhas.length} parcelas marcadas — a nota inteira sai` : `· ${linhas[0].r.titulo.split(" — ").slice(1).join(" — ")}`}</li>
                ))
                : regs.map((r) => <li key={`${t}:${r.id}`}>{r.titulo}</li>)}
            </ul>
          </div>
        );
      })}
    </details>
  );
}

export function ExcluirConfirmar({
  tipo, tipos, alvo, impacto, souAdmin, motivo, confirmacao, enviando, erro,
  onMotivo, onConfirmacao, onVoltar, onVoltarTipos, onConfirmar,
}: {
  tipo: TipoApi;
  tipos: TipoApi[];
  alvo: Alvo;
  impacto: ImpactoExclusao;
  souAdmin: boolean;
  motivo: string;
  confirmacao: string;
  enviando: boolean;
  erro: string | null;
  onMotivo: (v: string) => void;
  onConfirmacao: (v: string) => void;
  onVoltar: () => void;
  onVoltarTipos: () => void;
  onConfirmar: () => void;
}) {
  const lote = alvo.lote;
  const r0 = alvo.registros[0];
  const tipoReal = alvo.itens[0]?.tipo ?? tipo.id;
  const bloqueia = impacto.bloqueia ?? [];
  const bloqueado = bloqueia.length > 0;
  const risco = riscoItem(impacto);
  const exige = exigencias(risco, souAdmin);
  const esperado = confirmacaoEsperada(impacto.item.tipo, impacto.item.id);
  const porque = porqueDe([impacto]);
  const t = totaisImp(impacto);
  const nRegistros = alvo.registros.length;
  const todosDesfazem = alvo.itens.every((i) => verboDe(i.tipo) === "desfazer");
  const verbo = todosDesfazem ? "desfazer" : "apagar";
  const liberado = !bloqueado && (!exige.motivo || motivo.trim().length > 0) && (!exige.confirmacao || confirmacao.trim() === esperado);

  const tituloItem = lote ? `Lote de ${nRegistros} ${nRegistros === 1 ? "registro" : "registros"}` : (r0?.titulo ?? impacto.item.titulo);
  const iso = r0 ? dataDoRegistro(r0) : null;
  const href = lote ? null : (impacto.editar_url || destinoEditar(tipoReal, alvo.itens[0]?.id ?? ""));
  const nomeTipo = tipos.find((x) => x.id === tipoReal)?.label ?? tipo.label;
  const rotuloFaixa = lote ? `Você vai ${verbo} o lote` : `Você vai ${verbo}`;
  const nome = nomeCurto(tipo);

  return (
    <>
      <Migalhas itens={[
        { texto: "Tipos", aoClicar: onVoltarTipos },
        { texto: nome, aoClicar: onVoltar },
        { texto: lote ? `Lote de ${nRegistros}` : (r0 ? `${r0.titulo}` : impacto.item.titulo) },
      ]} />

      <div className="gx-desfazer" role="group" aria-label="O que será desfeito">
        <div>
          <div className="gx-desfazer-rotulo">{rotuloFaixa}</div>
          <div className="gx-desfazer-titulo">{tituloItem}</div>
          {!lote && r0?.subtitulo && <div className="gx-desfazer-sub">{r0.subtitulo}</div>}
          {lote && <div className="gx-desfazer-sub">{plural(t.n, "item será apagado", "itens serão apagados")} · {plural(t.rev, "ajuste", "ajustes")} · {plural(bloqueia.length, "bloqueio", "bloqueios")}</div>}
          <div className="gx-desfazer-meta">
            {lote
              ? <span>Tipo <b>{tipo.id === "todos_lancamentos" ? "vários" : nomeTipo}</b></span>
              : <>
                <span>Tipo <b>{nomeTipo}</b></span>
                <span aria-hidden="true">·</span>
                <span>Registro <b>{impacto.item.id || alvo.itens[0]?.id}</b></span>
                {iso && <><span aria-hidden="true">·</span><span>Data <b>{dataBr(iso)}</b></span></>}
              </>}
          </div>
          {lote && <ResumoLote alvo={alvo} tipos={tipos} />}
        </div>
        <div className="gx-desfazer-dir">
          <Selo tom={risco === "baixo" ? "ok" : "atencao"} titulo={porque.join("; ")}>{ROTULO_RISCO[risco]}</Selo>
          {href && <a href={href} className="gx-acao-linha"><Pencil size={12} aria-hidden />Corrigir em vez de apagar</a>}
        </div>
      </div>

      <Passo n={3} id="ex3-p3" titulo="Confira o que muda"
        direita={porque.length > 0 ? <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Porque: {porque.join("; ")}.</span> : undefined}>
        <div className="gx-impacto" aria-live="polite">
          <Bloco tom="bloqueio" icone={<Ban size={14} aria-hidden />} titulo="Bloqueia" sub="Impede de apagar até você resolver"
            selo={bloqueado ? <Selo tom="bloqueio">{plural(bloqueia.length, "bloqueio", "bloqueios")}</Selo> : <Selo tom="ok">Livre</Selo>}>
            {bloqueado ? (
              <ul>
                {bloqueia.map((b, i) => (
                  <li key={`${i}-${b.titulo}`}><b>{b.titulo}</b><span>{b.motivo}</span>{b.fazer && <span><b>O que fazer:</b> {b.fazer}</span>}</li>
                ))}
              </ul>
            ) : (
              <p className="gx-imp-vazio"><Check size={14} aria-hidden style={{ color: "var(--ft-verde)" }} />Nada bloqueia esta exclusão.</p>
            )}
          </Bloco>
          <Bloco tom="apagar" icone={<Trash2 size={14} aria-hidden />} titulo={verbo === "desfazer" ? "Será desfeito" : "Será apagado"} sub={verbo === "desfazer" ? "O dado volta a ficar em branco" : "Some do sistema e não volta"}
            selo={<Selo tom="bloqueio">{plural(impacto.apagar?.length ?? 0, "item", "itens")}</Selo>}>
            {(impacto.apagar ?? []).length > 0 ? <Lista itens={impacto.apagar} /> : <p className="gx-imp-vazio">Nada será apagado.</p>}
          </Bloco>
          <Bloco tom="reverter" icone={<Undo2 size={14} aria-hidden />} titulo="Será revertido" sub="É ajustado de volta"
            selo={<Selo tom="info">{plural(impacto.reverter?.length ?? 0, "ajuste", "ajustes")}</Selo>}>
            {(impacto.reverter ?? []).length > 0 ? <Lista itens={impacto.reverter} /> : <p className="gx-imp-vazio">Nada será revertido.</p>}
          </Bloco>
          <Bloco tom="aviso" icone={<AlertTriangle size={14} aria-hidden />} titulo="Avisos" sub="Atenção antes de confirmar"
            selo={<Selo tom="atencao">{plural(impacto.avisos?.length ?? 0, "aviso", "avisos")}</Selo>}>
            {(impacto.avisos ?? []).length > 0 ? <Lista itens={impacto.avisos} /> : <p className="gx-imp-vazio">Sem avisos.</p>}
          </Bloco>
        </div>
      </Passo>

      <Passo n={4} id="ex3-p4" titulo={bloqueado ? "Resolva o bloqueio" : "Confirme"}>
        {bloqueado ? (
          <p className="gv-aviso" data-tom="erro" role="alert">
            {lote
              ? "Há itens bloqueados no lote. Volte, desmarque os itens bloqueados e confira o impacto de novo."
              : "Não dá para apagar enquanto houver bloqueio. Resolva o que está acima (o texto “O que fazer” diz como) e tente de novo."}
          </p>
        ) : (
          <div className="gx-decisao">
            <div className="gx-campo-motivo" style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                <Campo rotulo={`Por que está ${verbo === "desfazer" ? "desfazendo" : "apagando"}? (fica na trilha)${exige.motivo ? "" : " — opcional"}`} id="ex3-motivo">
                  <textarea rows={2} value={motivo} onChange={(e) => onMotivo(e.target.value)} required={exige.motivo} aria-required={exige.motivo} />
                </Campo>
                <p className="gv-ajuda">
                  {exige.motivo ? "Obrigatório neste risco. " : "Neste risco o motivo é opcional. "}
                  {souAdmin
                    ? "Você é administrador: apaga na hora. Quando um operador faz isto, vira um pedido que o administrador decide."
                    : "Você não é administrador: isto vira um pedido, e o administrador decide. Você acompanha em Meus pedidos."}
                </p>
              </div>
              {exige.confirmacao && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                  <Campo rotulo={`Para confirmar, digite ${esperado}`} id="ex3-confirmacao">
                    <input value={confirmacao} onChange={(e) => onConfirmacao(e.target.value)} autoCapitalize={impacto.item.tipo === "animal" ? "none" : "characters"} spellCheck={false} autoComplete="off" />
                  </Campo>
                  <p className="gv-ajuda">{impacto.item.tipo === "animal" ? "Ficha de animal: digite o número do animal." : "Risco alto: digite APAGAR em maiúsculas."}</p>
                </div>
              )}
            </div>
            <div>
              <div className="gx-niveis" role="group" aria-label="O que cada risco exige">
                {NIVEIS.map((nv) => (
                  <div key={nv.id} className="gx-nivel" data-atual={nv.id === risco ? "true" : undefined}>
                    <b>{nv.titulo}{nv.id === risco && <> · <span style={{ color: "var(--ft-ouro-txt)" }}>este {lote ? "lote" : "registro"}</span></>}</b>
                    {nv.texto}
                  </div>
                ))}
              </div>
              {!exige.confirmacao && <p className="gv-ajuda" style={{ marginTop: "0.4rem" }}>{souAdmin ? `Digitar APAGAR não é exigido neste risco.` : "Quem digita a confirmação é o administrador, ao aprovar."}</p>}
            </div>
          </div>
        )}
      </Passo>

      <BarraAcao
        retorno={erro ? <span role="alert" style={{ color: "var(--ft-verm)", fontWeight: 700 }}>{erro}</span> : undefined}
        resumo={lote
          ? `${verbo === "desfazer" ? "Desfazer" : "Apagar"} ${tituloItem.toLowerCase()}`
          : `${souAdmin ? (verbo === "desfazer" ? "Desfazer" : "Apagar") : "Pedir a exclusão de"} 1 registro · ${r0?.titulo ?? impacto.item.titulo}`}
        detalhe={bloqueado ? "Bloqueado: nada será apagado"
          : souAdmin ? `${ROTULO_RISCO[risco]} · não dá para desfazer · fica na trilha${exige.motivo ? " com o seu motivo" : ""}`
          : `${ROTULO_RISCO[risco]} · o administrador decide · você acompanha em Meus pedidos`}
        secundaria={bloqueado ? undefined : <button type="button" className="btn-ghost" onClick={onVoltar} disabled={enviando} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", whiteSpace: "nowrap" }}><ArrowLeft size={14} aria-hidden />Voltar</button>}
        acao={bloqueado
          ? <button type="button" className="btn-primary-gold" onClick={onVoltar}><ArrowLeft size={14} aria-hidden /> Voltar</button>
          : souAdmin
            ? <button type="button" className="gx-perigo" disabled={!liberado || enviando} onClick={onConfirmar}><Trash2 size={15} aria-hidden />{enviando ? "Enviando…" : verbo === "desfazer" ? "Desfazer definitivamente" : "Apagar definitivamente"}</button>
            : <BotaoOuro desabilitado={!liberado || enviando} onClick={onConfirmar}>{enviando ? "Enviando…" : "Enviar pedido de exclusão"}</BotaoOuro>}
      />
    </>
  );
}
