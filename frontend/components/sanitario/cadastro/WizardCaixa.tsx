"use client";
// Central de Protocolos › Vacinas e exames › Cadastro — WIZARD de 9 etapas que
// deslizam (casco: components/protocolos/WizardProtocolo.tsx, que respeita
// prefers-reduced-motion). Começa por "do catálogo ou do zero":
//   - do catálogo: GET /sanitario/catalogo/{versao}/previa-copia traz a definição
//     já resolvida para a fazenda (NÃO grava); o wizard abre essa definição e só
//     ao CONCLUIR faz POST /catalogo/{versao}/ativar com os ajustes (vira a v1,
//     ligada ao catálogo). Cancelar não deixa cópia nenhuma;
//   - do zero: definição em branco; salvar = POST /sanitario/caixas.
// Cada "Continuar" valida a etapa no back (POST /caixas/validar); a Revisão
// mostra "entram / ficam de fora e por quê" (POST /caixas/previa) sem gravar.
// Só administrador (GET /sanitario/eu); o back recusa os demais de qualquer jeito.
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Plus } from "lucide-react";
import { WizardProtocolo, type PassoWizard } from "@/components/protocolos/WizardProtocolo";
import { TelaSkeleton } from "@/components/ui";
import {
  ativarDoCatalogo, catalogoDaFazenda, criarCaixa, errosValidacaoDoErro, listarCaixas, mensagemDoErro, mudarEstadoCaixas,
  novaVersaoCaixa, obterCaixa, obterParametros, previaCaixa, previaCopiaCatalogo, validarCaixa,
} from "@/lib/apiSanitario";
import {
  AO_FECHAR, COLUNAS_FICHA, CONDICOES, DOSE_UNIDADES, EVENTO_TIPOS, MESES_CURTOS, MODOS_LEITE, AJUDA_MODO_LEITE,
  ROTULO_COLUNA_FICHA, ROTULO_CONDICAO, ROTULO_EVENTO, ROTULO_MODO_LEITE, ROTULO_TIPO, ROTULO_UNIDADE, TIPOS_CAIXA,
  definicaoCompleta, definicaoVazia, fmtData, hojeISO, intOuNulo, numOuNulo, textoJanela, textoProduto, textoPublico,
  type CaixaDetalhe, type CaixaResumo, type CatalogoItemFazenda, type DefinicaoCaixa, type Parametros, type PreviaCaixa,
} from "@/lib/sanitarioTipos";
import { Faixa, Seg, carregarCategoriasSan, carregarEstoqueSan, useCarregar, type ItemEstoqueSan } from "../comum";
import { FolhaVazia } from "../FichaCampo";

type Form = { def: DefinicaoCaixa; ativo: boolean; aceitarCarencia: boolean };
type Apoio = {
  estoque: ItemEstoqueSan[]; categorias: { id: number; nome: string }[]; caixas: CaixaResumo[]; parametros: Parametros | null;
};
type Ctx = { form: Form; setForm: (f: Form) => void };

const PASSOS_TITULOS = ["Identificação", "Produto", "Público", "Janela", "Aglomeração e aviso", "Veterinário e etapas legais",
  "Carência", "Ficha de campo", "Revisão"];

function setDef(ctx: Ctx, patch: Partial<DefinicaoCaixa>) {
  ctx.setForm({ ...ctx.form, def: { ...ctx.form.def, ...patch } });
}
function campoNum(v: number | null | undefined): string { return v == null ? "" : String(v); }

// ── etapa 1 ──
function EtapaIdentificacao({ ctx, apoio, caixaId }: { ctx: Ctx; apoio: Apoio; caixaId: number | null }) {
  const d = ctx.form.def;
  const nomeNorm = (d.nome || "").trim().toLowerCase();
  const dup = nomeNorm ? apoio.caixas.find((c) => c.id !== caixaId && c.estado !== "arquivada" && c.nome.trim().toLowerCase() === nomeNorm) : null;
  return (
    <div className="san-wiz-etapa">
      <div className="san-campo">
        <span className="san-rot">Tipo</span>
        <Seg rotulo="Tipo" valor={d.tipo} opcoes={TIPOS_CAIXA.map((t) => ({ id: t, label: ROTULO_TIPO[t] }))}
          onChange={(t) => setDef(ctx, {
            tipo: t,
            produto_modo: t === "exame" ? "nao_se_aplica" : d.produto_modo === "nao_se_aplica" ? "vazio" : d.produto_modo,
          })} />
      </div>
      <div className="san-linha">
        <div className="san-campo" style={{ flex: "2 1 260px" }}>
          <label htmlFor="wNome">Nome</label>
          <input id="wNome" className="san-input" value={d.nome || ""} onChange={(e) => setDef(ctx, { nome: e.target.value })} placeholder="ex.: Raiva" />
        </div>
        <div className="san-campo">
          <label htmlFor="wCurto">Nome curto (aparece no dia)</label>
          <input id="wCurto" className="san-input" value={d.nome_curto || ""} onChange={(e) => setDef(ctx, { nome_curto: e.target.value })} placeholder="ex.: Raiva" />
        </div>
      </div>
      {dup && (
        <Faixa tipo="atencao">Já existe <b>{dup.nome}</b> ({ROTULO_TIPO[dup.tipo]}, {dup.estado}). Duas caixas iguais contam o mesmo animal duas vezes. Prefira editar a existente.</Faixa>
      )}
      <label className="san-liga">
        <input type="checkbox" checked={ctx.form.ativo} onChange={(e) => ctx.setForm({ ...ctx.form, ativo: e.target.checked })} />
        <span><b>Ativo</b><small>Inativo fica pronto, mas não gera nada: nem caixa, nem aviso.</small></span>
      </label>
      <label className="san-liga">
        <input type="checkbox" checked={d.obrigatoria} onChange={(e) => setDef(ctx, { obrigatoria: e.target.checked })} />
        <span><b>Obrigatório na fazenda</b><small>Entra na cobertura obrigatória do Painel.</small></span>
      </label>
    </div>
  );
}

// ── etapa 2 ──
function EtapaProduto({ ctx, apoio }: { ctx: Ctx; apoio: Apoio }) {
  const d = ctx.form.def;
  if (d.tipo === "exame") return <Faixa>Exame não usa produto nem dose. Siga para o público.</Faixa>;
  const porPeso = d.dose_unidade === "mL_por_kg" || d.dose_unidade === "mL_por_x_kg";
  return (
    <div className="san-wiz-etapa">
      <div className="san-opcs" role="radiogroup" aria-label="Produto">
        {([["estoque", "Vincular item do estoque", "A baixa é feita a cada animal registrado."],
          ["sem_estoque", "Sem controle de estoque", "Só registra o nome; não baixa nada."],
          ["vazio", "Deixar em branco", "Escolhe o produto no dia."]] as const).map(([k, t, s]) => (
          <label key={k} className="san-opc">
            <input type="radio" name="wProd" checked={d.produto_modo === k} onChange={() => setDef(ctx, { produto_modo: k })} />
            <span><b>{t}</b><small>{s}</small></span>
          </label>
        ))}
      </div>
      {d.produto_modo === "estoque" && (
        <div className="san-campo">
          <label htmlFor="wEstq">Item do estoque</label>
          <select id="wEstq" className="san-input" value={d.estoque_id ?? ""} onChange={(e) => setDef(ctx, { estoque_id: intOuNulo(e.target.value) })}>
            <option value="">Escolha…</option>
            {apoio.estoque.map((e) => <option key={e.id} value={e.id}>{e.nome}{e.quantidade != null ? ` · saldo ${e.quantidade} ${e.unidade || ""}` : ""}</option>)}
          </select>
        </div>
      )}
      {d.produto_modo === "sem_estoque" && (
        <div className="san-campo">
          <label htmlFor="wPtxt">Nome do produto</label>
          <input id="wPtxt" className="san-input" value={d.produto_texto || ""} onChange={(e) => setDef(ctx, { produto_texto: e.target.value })} />
        </div>
      )}
      <div className="san-linha">
        <div className="san-campo curto">
          <label htmlFor="wDose">Dose (número livre)</label>
          <input id="wDose" className="san-input" type="number" step="0.1" min={0} value={campoNum(d.dose_valor)}
            onChange={(e) => setDef(ctx, { dose_valor: numOuNulo(e.target.value) })} />
        </div>
        <div className="san-campo medio">
          <label htmlFor="wUn">Unidade</label>
          <select id="wUn" className="san-input" value={d.dose_unidade ?? ""} onChange={(e) => setDef(ctx, { dose_unidade: (e.target.value || null) as DefinicaoCaixa["dose_unidade"] })}>
            <option value="">—</option>
            {DOSE_UNIDADES.map((u) => <option key={u} value={u}>{ROTULO_UNIDADE[u]}</option>)}
          </select>
        </div>
        {d.dose_unidade === "mL_por_x_kg" && (
          <div className="san-campo curto">
            <label htmlFor="wX">X (kg)</label>
            <input id="wX" className="san-input" type="number" min={1} value={campoNum(d.dose_x_kg)} onChange={(e) => setDef(ctx, { dose_x_kg: numOuNulo(e.target.value) })} />
          </div>
        )}
      </div>
      {porPeso && (
        <div className="san-campo">
          <span className="san-rot">Animal sem peso</span>
          <Seg rotulo="Animal sem peso" valor={d.peso_ausente} onChange={(v) => setDef(ctx, { peso_ausente: v })}
            opcoes={[{ id: "exigir", label: "Pedir o peso no curral" }, { id: "estimado", label: "Usar o peso médio da categoria (estimado)" }]} />
        </div>
      )}
    </div>
  );
}

// ── etapa 3 ──
function EtapaPublico({ ctx, apoio, caixaId }: { ctx: Ctx; apoio: Apoio; caixaId: number | null }) {
  const d = ctx.form.def;
  const alternarCat = (id: number) => setDef(ctx, { categorias: d.categorias.includes(id) ? d.categorias.filter((c) => c !== id) : [...d.categorias, id] });
  const alternarCond = (c: (typeof CONDICOES)[number]) => setDef(ctx, { pub_condicoes: d.pub_condicoes.includes(c) ? d.pub_condicoes.filter((x) => x !== c) : [...d.pub_condicoes, c] });
  return (
    <div className="san-wiz-etapa">
      <div className="san-campo">
        <span className="san-rot">Sexo</span>
        <Seg rotulo="Sexo" valor={d.pub_sexo} onChange={(v) => setDef(ctx, { pub_sexo: v })}
          opcoes={[{ id: "F", label: "Fêmeas" }, { id: "M", label: "Machos" }, { id: "ambos", label: "Ambos" }]} />
      </div>
      <div className="san-campo">
        <span className="san-rot">Categorias (nenhuma marcada = todas)</span>
        {d.categorias.length > 0 && (
          <Seg rotulo="Incluir ou excluir categorias" valor={d.pub_cat_modo} onChange={(v) => setDef(ctx, { pub_cat_modo: v })}
            opcoes={[{ id: "incluir", label: "Só as marcadas" }, { id: "excluir", label: "Todas, menos as marcadas" }]} />
        )}
        <div className="san-opcs" style={{ marginTop: "0.4rem" }}>
          {apoio.categorias.length ? apoio.categorias.map((c) => (
            <label key={c.id} className="san-opc"><input type="checkbox" checked={d.categorias.includes(c.id)} onChange={() => alternarCat(c.id)} /><span>{c.nome}</span></label>
          )) : <span className="san-nota">Nenhuma categoria de manejo cadastrada (Recria › Categorias).</span>}
        </div>
      </div>
      <div className="san-linha">
        <div className="san-campo medio">
          <label htmlFor="wIMin">Idade mínima (dias)</label>
          <input id="wIMin" className="san-input" type="number" min={0} value={campoNum(d.pub_idade_min_dias)} placeholder="sem mínimo"
            onChange={(e) => setDef(ctx, { pub_idade_min_dias: intOuNulo(e.target.value) })} />
          {d.pub_idade_min_dias != null && <span className="san-nota">≈ {Math.round(d.pub_idade_min_dias / 30.44)} meses</span>}
        </div>
        <div className="san-campo medio">
          <label htmlFor="wIMax">Idade máxima (dias)</label>
          <input id="wIMax" className="san-input" type="number" min={0} value={campoNum(d.pub_idade_max_dias)} placeholder="sem máximo"
            onChange={(e) => setDef(ctx, { pub_idade_max_dias: intOuNulo(e.target.value) })} />
          {d.pub_idade_max_dias != null && <span className="san-nota">≈ {Math.round(d.pub_idade_max_dias / 30.44)} meses</span>}
        </div>
      </div>
      <div className="san-campo">
        <span className="san-rot">Condição</span>
        <div className="san-opcs">
          {CONDICOES.map((c) => (
            <label key={c} className="san-opc"><input type="checkbox" checked={d.pub_condicoes.includes(c)} onChange={() => alternarCond(c)} /><span>{ROTULO_CONDICAO[c]}</span></label>
          ))}
        </div>
      </div>
      <div className="san-linha">
        <div className="san-campo medio">
          <label htmlFor="wHT">Histórico vacinal</label>
          <select id="wHT" className="san-input" value={d.pub_hist_tipo ?? ""} onChange={(e) => setDef(ctx, { pub_hist_tipo: (e.target.value || null) as DefinicaoCaixa["pub_hist_tipo"] })}>
            <option value="">Não filtrar</option><option value="ja">Já recebeu</option><option value="nunca">Nunca recebeu</option>
          </select>
        </div>
        {d.pub_hist_tipo && (
          <div className="san-campo">
            <label htmlFor="wHC">Qual vacina</label>
            <select id="wHC" className="san-input" value={d.pub_hist_caixa_id ?? ""} onChange={(e) => setDef(ctx, { pub_hist_caixa_id: intOuNulo(e.target.value) })}>
              <option value="">Escolha…</option>
              {apoio.caixas.filter((c) => c.id !== caixaId && c.estado !== "arquivada").map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
            </select>
          </div>
        )}
      </div>
      <p className="san-nota" style={{ margin: 0 }}>Ex.: RB51 só em quem nunca recebeu B19; reforço só em quem já tem a primovacinação. Quem começou uma série continua até completar, mesmo mudando de categoria.</p>
    </div>
  );
}

// ── etapa 4 ──
function EtapaJanela({ ctx }: { ctx: Ctx }) {
  const d = ctx.form.def;
  const marcados = new Set(d.periodo_grupos.flat());
  function alternarMes(m: number) {
    const grupos = d.periodo_grupos.map((g) => [...g]);
    if (marcados.has(m)) {
      const gi = grupos.findIndex((g) => g.includes(m));
      grupos[gi] = grupos[gi].filter((x) => x !== m);
      setDef(ctx, { periodo_grupos: grupos.filter((g) => g.length).sort((a, b) => a[0] - b[0]) });
    } else {
      setDef(ctx, { periodo_grupos: [...grupos, [m]].sort((a, b) => a[0] - b[0]) });
    }
  }
  function juntar(i: number) {
    const g = d.periodo_grupos.map((x) => [...x]);
    g.splice(i, 2, [...g[i], ...g[i + 1]].sort((a, b) => a - b));
    setDef(ctx, { periodo_grupos: g });
  }
  function separar(i: number) {
    const g = d.periodo_grupos.map((x) => [...x]);
    g.splice(i, 1, ...g[i].map((m) => [m]));
    setDef(ctx, { periodo_grupos: g });
  }
  const preParto = d.evento_tipo === "pre_parto";
  return (
    <div className="san-wiz-etapa">
      <p className="san-nota" style={{ margin: 0 }}>Use um filtro ou os dois. Com os dois, o animal precisa cumprir ambos.</p>
      <label className="san-liga">
        <input type="checkbox" checked={d.jan_usa_evento} onChange={(e) => setDef(ctx, { jan_usa_evento: e.target.checked, evento_tipo: d.evento_tipo || "idade" })} />
        <span><b>Por evento de vida</b><small>Nascimento, pré-parto, entrada em IA, parto, secagem, compra.</small></span>
      </label>
      {d.jan_usa_evento && (
        <div className="san-sub">
          <div className="san-linha">
            <div className="san-campo">
              <label htmlFor="wEv">Evento</label>
              <select id="wEv" className="san-input" value={d.evento_tipo ?? ""} onChange={(e) => {
                const t = e.target.value as DefinicaoCaixa["evento_tipo"];
                setDef(ctx, t === "pre_parto" ? { evento_tipo: t, evento_de_dias: -(Math.abs(d.evento_de_dias ?? 30)), evento_ate_dias: 0 } : { evento_tipo: t });
              }}>
                {EVENTO_TIPOS.map((t) => <option key={t} value={t}>{ROTULO_EVENTO[t]}</option>)}
              </select>
            </div>
            {preParto ? (
              <div className="san-campo medio">
                <label htmlFor="wEvDe">Dias antes do parto previsto</label>
                <input id="wEvDe" className="san-input" type="number" min={0} value={d.evento_de_dias != null ? String(Math.abs(d.evento_de_dias)) : ""}
                  onChange={(e) => { const n = intOuNulo(e.target.value); setDef(ctx, { evento_de_dias: n == null ? null : -Math.abs(n), evento_ate_dias: 0 }); }} />
              </div>
            ) : (<>
              <div className="san-campo curto">
                <label htmlFor="wEvDe">De (dias)</label>
                <input id="wEvDe" className="san-input" type="number" value={campoNum(d.evento_de_dias)} onChange={(e) => setDef(ctx, { evento_de_dias: intOuNulo(e.target.value) })} />
              </div>
              <div className="san-campo curto">
                <label htmlFor="wEvAte">Até (dias)</label>
                <input id="wEvAte" className="san-input" type="number" value={campoNum(d.evento_ate_dias)} onChange={(e) => setDef(ctx, { evento_ate_dias: intOuNulo(e.target.value) })} />
              </div>
            </>)}
          </div>
          <p className="san-nota" style={{ margin: 0 }}>
            {preParto ? "Fecha no parto real. Parto atrasado mantém a janela aberta."
              : d.evento_tipo === "idade" && d.evento_de_dias != null && d.evento_ate_dias != null
                ? `Idade de ${Math.round(d.evento_de_dias / 30.44)} a ${Math.round(d.evento_ate_dias / 30.44)} meses.` : "Contados a partir do evento."}
          </p>
        </div>
      )}
      <label className="san-liga">
        <input type="checkbox" checked={d.jan_usa_periodo} onChange={(e) => setDef(ctx, { jan_usa_periodo: e.target.checked, periodo_modo: d.periodo_modo || "meses" })} />
        <span><b>Por período do ano</b><small>Meses como na planilha, a cada N anos, ou contínuo.</small></span>
      </label>
      {d.jan_usa_periodo && (
        <div className="san-sub">
          <Seg rotulo="Tipo de período" valor={d.periodo_modo || "meses"} onChange={(v) => setDef(ctx, { periodo_modo: v })}
            opcoes={[{ id: "meses", label: "Meses do ano" }, { id: "frequencia", label: "A cada N anos" }, { id: "continuo", label: "Contínuo (todo mês)" }]} />
          {d.periodo_modo === "meses" && (<>
            <div className="san-meses" role="group" aria-label="Meses">
              {MESES_CURTOS.map((m, i) => <button key={m} type="button" aria-pressed={marcados.has(i)} onClick={() => alternarMes(i)}>{m}</button>)}
            </div>
            <div className="san-acoes">
              {d.periodo_grupos.length ? d.periodo_grupos.map((g, i) => (
                <span key={g.join("-")} className="san-tag destaque">
                  {g.map((m) => MESES_CURTOS[m]).join("/")}{g.length > 1 ? " · 1 dose" : ""}
                  {g.length > 1 && <button type="button" className="san-link" onClick={() => separar(i)}>separar</button>}
                  {d.periodo_grupos[i + 1] && d.periodo_grupos[i + 1][0] === g[g.length - 1] + 1 && (
                    <button type="button" className="san-link" onClick={() => juntar(i)}>juntar com {MESES_CURTOS[d.periodo_grupos[i + 1][0]]}</button>
                  )}
                </span>
              )) : <span className="san-nota">Clique nos meses. Meses vizinhos podem virar uma dose só (ex.: jun/jul).</span>}
            </div>
          </>)}
          {d.periodo_modo === "frequencia" && (
            <div className="san-linha">
              <div className="san-campo curto">
                <label htmlFor="wFa">A cada (anos)</label>
                <input id="wFa" className="san-input" type="number" min={1} value={campoNum(d.periodo_anos)} onChange={(e) => setDef(ctx, { periodo_anos: intOuNulo(e.target.value) })} />
              </div>
              <div className="san-campo curto">
                <label htmlFor="wFb">Ano-base</label>
                <input id="wFb" className="san-input" type="number" value={campoNum(d.periodo_ano_base)} onChange={(e) => setDef(ctx, { periodo_ano_base: intOuNulo(e.target.value) })} />
              </div>
              <div className="san-campo curto">
                <label htmlFor="wFm">Mês</label>
                <select id="wFm" className="san-input" value={d.periodo_grupos[0]?.[0] ?? ""} onChange={(e) => setDef(ctx, { periodo_grupos: e.target.value === "" ? [] : [[Number(e.target.value)]] })}>
                  <option value="">Escolha…</option>
                  {MESES_CURTOS.map((m, i) => <option key={m} value={i}>{m}</option>)}
                </select>
              </div>
            </div>
          )}
          {d.periodo_modo !== "continuo" ? (
            <div className="san-linha">
              <div className="san-campo curto">
                <label htmlFor="wDb">Data-base (dia do mês)</label>
                <input id="wDb" className="san-input" type="number" min={1} max={28} value={campoNum(d.data_base_dia)} onChange={(e) => setDef(ctx, { data_base_dia: intOuNulo(e.target.value) ?? 15 })} />
              </div>
              <p className="san-nota" style={{ flex: "2 1 240px", margin: 0 }}>O público é avaliado como o animal <b>estará</b> nesse dia.</p>
            </div>
          ) : <p className="san-nota" style={{ margin: 0 }}>Contínuo: o aviso antecipado vem só pelo mínimo de animais.</p>}
        </div>
      )}
      <div className="san-linha">
        <div className="san-campo medio">
          <label htmlFor="wCom">Começar em (opcional)</label>
          <input id="wCom" className="san-input" type="date" value={d.comecar_em || ""} onChange={(e) => setDef(ctx, { comecar_em: e.target.value || null })} />
        </div>
        <p className="san-nota" style={{ flex: "2 1 240px", margin: 0 }}>Ex.: exames que retomam em 2027.</p>
      </div>
      <div className="san-campo">
        <span className="san-rot">Quando a janela fechar</span>
        <div className="san-opcs" role="radiogroup" aria-label="Quando a janela fechar">
          {AO_FECHAR.map((k) => (
            <label key={k} className="san-opc">
              <input type="radio" name="wFecha" checked={d.ao_fechar === k} onChange={() => setDef(ctx, { ao_fechar: k })} />
              <span><b>{k === "perder" ? "Perder" : k === "manter" ? "Manter aberta" : "Descartar vacina"}</b>
                <small>{k === "perder" ? "Sai da caixa e fica como perdida." : k === "manter" ? "Continua como atrasada até aplicar." : "Some da lista; fica registrado."}</small></span>
            </label>
          ))}
        </div>
      </div>
      <label className="san-liga">
        <input type="checkbox" checked={d.serie.length > 0} onChange={(e) => setDef(ctx, { serie: e.target.checked ? [{ dose: 2, apos_dias: 30, janela_dias: 30 }] : [] })} />
        <span><b>Série (2ª dose)</b><small>Dose 1 e dose 2 dentro do mesmo ciclo.</small></span>
      </label>
      {d.serie.length > 0 && (
        <div className="san-sub">
          <div className="san-linha">
            <div className="san-campo curto">
              <label htmlFor="wS2">2ª dose após (dias)</label>
              <input id="wS2" className="san-input" type="number" min={1} value={campoNum(d.serie[0].apos_dias)}
                onChange={(e) => setDef(ctx, { serie: [{ ...d.serie[0], apos_dias: intOuNulo(e.target.value) ?? 1 }] })} />
            </div>
            <div className="san-campo curto">
              <label htmlFor="wS2j">Janela da 2ª dose (dias)</label>
              <input id="wS2j" className="san-input" type="number" min={1} value={campoNum(d.serie[0].janela_dias)}
                onChange={(e) => setDef(ctx, { serie: [{ ...d.serie[0], janela_dias: intOuNulo(e.target.value) ?? 30 }] })} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── etapa 5 ──
function EtapaAviso({ ctx, apoio }: { ctx: Ctx; apoio: Apoio }) {
  const d = ctx.form.def;
  return (
    <div className="san-wiz-etapa">
      <div className="san-linha">
        <div className="san-campo medio">
          <label htmlFor="wMin">Mínimo de animais para avisar</label>
          <input id="wMin" className="san-input" type="number" min={1} value={campoNum(d.aglo_min)} onChange={(e) => setDef(ctx, { aglo_min: intOuNulo(e.target.value) ?? 1 })} />
        </div>
        <div className="san-campo medio">
          <label htmlFor="wAnt">Antecedência do aviso (dias)</label>
          <input id="wAnt" className="san-input" type="number" min={0} value={campoNum(d.aviso_antecedencia_dias)} onChange={(e) => setDef(ctx, { aviso_antecedencia_dias: intOuNulo(e.target.value) ?? 0 })} />
        </div>
        <div className="san-campo medio">
          <label htmlFor="wFim">Avisar antes da janela fechar (dias, opcional)</label>
          <input id="wFim" className="san-input" type="number" min={0} value={campoNum(d.aviso_fim_janela_dias)} onChange={(e) => setDef(ctx, { aviso_fim_janela_dias: intOuNulo(e.target.value) })} />
        </div>
      </div>
      <label className="san-liga">
        <input type="checkbox" checked={d.push_admin} onChange={(e) => setDef(ctx, { push_admin: e.target.checked })} />
        <span><b>Push aos administradores</b><small>O aviso de “aglomerou” é só para administradores da fazenda.</small></span>
      </label>
      <Faixa>Nota na Agenda: <b>“{d.tipo === "exame" ? "Exame" : "Vacina"} {d.nome_curto || d.nome || "X"} aglomerou N animais — marcar data”</b>.</Faixa>
      <p className="san-nota" style={{ margin: 0 }}>Estes valores são desta caixa, não da fazenda inteira.{apoio.parametros ? ` Padrão da fazenda: ${apoio.parametros.antecedencia_padrao_dias} dias.` : ""}</p>
    </div>
  );
}

// ── etapa 6 ──
function EtapaLegal({ ctx, apoio }: { ctx: Ctx; apoio: Apoio }) {
  const d = ctx.form.def;
  const at = d.legal_atestado, co = d.legal_comprovacao, le = d.legal_leitura;
  return (
    <div className="san-wiz-etapa">
      {apoio.parametros?.prazos_legais_ativo && (
        <Faixa>Controle de prazos legais ligado{apoio.parametros.uf ? ` (UF ${apoio.parametros.uf})` : ""}: o atestado e a comprovação daqui viram prazos no Painel.</Faixa>
      )}
      <label className="san-liga">
        <input type="checkbox" checked={d.legal_crmv_pedir} onChange={(e) => setDef(ctx, { legal_crmv_pedir: e.target.checked })} />
        <span><b>Pedir veterinário com CRMV</b><small>Pede, não exige: dá para marcar e aplicar sem.</small></span>
      </label>
      <label className="san-liga">
        <input type="checkbox" checked={!!at} onChange={(e) => setDef(ctx, { legal_atestado: e.target.checked ? { destinatario_tipo: "orgao", quando: "primeiro", dias: 30 } : null })} />
        <span><b>Atestado</b><small>Para quem e em quanto tempo mandar.</small></span>
      </label>
      {at && (
        <div className="san-sub">
          <div className="san-linha">
            <div className="san-campo medio">
              <label htmlFor="wAtP">Para quem</label>
              <select id="wAtP" className="san-input" value={at.destinatario_tipo || "orgao"} onChange={(e) => setDef(ctx, { legal_atestado: { ...at, destinatario_tipo: e.target.value as "orgao" } })}>
                <option value="orgao">Órgão</option><option value="laticinio">Laticínio</option><option value="comprador">Comprador</option><option value="outro">Outro</option>
              </select>
            </div>
            <div className="san-campo">
              <label htmlFor="wAtD">Destinatário</label>
              <input id="wAtD" className="san-input" value={at.destinatario_texto || ""} placeholder="ex.: Agrodefesa / SIDAGO"
                onChange={(e) => setDef(ctx, { legal_atestado: { ...at, destinatario_texto: e.target.value || null } })} />
            </div>
          </div>
          <div className="san-linha">
            <div className="san-campo medio">
              <label htmlFor="wAtQ">Quando mandar</label>
              <select id="wAtQ" className="san-input" value={at.quando || "primeiro"} onChange={(e) => setDef(ctx, { legal_atestado: { ...at, quando: e.target.value as "primeiro" } })}>
                <option value="aplicacao">Dias após a aplicação</option><option value="nfe">Dias após a NF-e da compra</option><option value="primeiro">O que vencer primeiro</option>
              </select>
            </div>
            <div className="san-campo curto">
              <label htmlFor="wAtN">Dias</label>
              <input id="wAtN" className="san-input" type="number" min={0} value={campoNum(at.dias)} onChange={(e) => setDef(ctx, { legal_atestado: { ...at, dias: intOuNulo(e.target.value) ?? 0 } })} />
            </div>
          </div>
        </div>
      )}
      <label className="san-liga">
        <input type="checkbox" checked={!!co} onChange={(e) => setDef(ctx, { legal_comprovacao: e.target.checked ? { dias: 180, aviso_dias: 30, push: true, email: false } : null })} />
        <span><b>Comprovação periódica</b><small>Ex.: a cada 180 dias, com aviso antes e push ou e-mail ao administrador.</small></span>
      </label>
      {co && (
        <div className="san-sub">
          <div className="san-linha">
            <div className="san-campo curto">
              <label htmlFor="wCpD">A cada (dias)</label>
              <input id="wCpD" className="san-input" type="number" min={1} value={campoNum(co.dias)} onChange={(e) => setDef(ctx, { legal_comprovacao: { ...co, dias: intOuNulo(e.target.value) ?? 1 } })} />
            </div>
            <div className="san-campo curto">
              <label htmlFor="wCpA">Avisar antes (dias)</label>
              <input id="wCpA" className="san-input" type="number" min={0} value={campoNum(co.aviso_dias)} onChange={(e) => setDef(ctx, { legal_comprovacao: { ...co, aviso_dias: intOuNulo(e.target.value) ?? 0 } })} />
            </div>
            <label className="san-liga"><input type="checkbox" checked={co.push !== false} onChange={(e) => setDef(ctx, { legal_comprovacao: { ...co, push: e.target.checked } })} /><span>Push</span></label>
            <label className="san-liga"><input type="checkbox" checked={!!co.email} onChange={(e) => setDef(ctx, { legal_comprovacao: { ...co, email: e.target.checked } })} /><span>E-mail</span></label>
          </div>
        </div>
      )}
      <label className="san-liga">
        <input type="checkbox" checked={!!le} onChange={(e) => setDef(ctx, { legal_leitura: e.target.checked ? { modo: "so_resultado", horas: 72, tolerancia: 6 } : null })} />
        <span><b>Leitura ou resultado (exames)</b><small>Modo de lançar o resultado e janela de leitura.</small></span>
      </label>
      {le && (
        <div className="san-sub">
          <div className="san-linha">
            <div className="san-campo medio">
              <label htmlFor="wLm">Modo</label>
              <select id="wLm" className="san-input" value={le.modo || "so_resultado"} onChange={(e) => setDef(ctx, { legal_leitura: { ...le, modo: e.target.value as "so_resultado" } })}>
                <option value="so_resultado">Só resultado</option><option value="diferenca">Diferença</option><option value="medidas">Medidas completas</option>
              </select>
            </div>
            <div className="san-campo curto">
              <label htmlFor="wLh">Leitura em (horas)</label>
              <input id="wLh" className="san-input" type="number" min={0} value={campoNum(le.horas)} onChange={(e) => setDef(ctx, { legal_leitura: { ...le, horas: intOuNulo(e.target.value) } })} />
            </div>
            <div className="san-campo curto">
              <label htmlFor="wLt">Tolerância (± horas)</label>
              <input id="wLt" className="san-input" type="number" min={0} value={campoNum(le.tolerancia)} onChange={(e) => setDef(ctx, { legal_leitura: { ...le, tolerancia: intOuNulo(e.target.value) } })} />
            </div>
          </div>
        </div>
      )}
      <label className="san-liga">
        <input type="checkbox" checked={d.legal_reagente_aviso} onChange={(e) => setDef(ctx, { legal_reagente_aviso: e.target.checked })} />
        <span><b>Aviso de reagente</b><small>Gera só um aviso, sem pendência.</small></span>
      </label>
      <label className="san-liga">
        <input type="checkbox" checked={d.legal_marca_texto != null} onChange={(e) => setDef(ctx, { legal_marca_texto: e.target.checked ? "" : null })} />
        <span><b>Lembrete de marcação</b><small>Ex.: B19 com o algarismo do ano; RB51 com “V”.</small></span>
      </label>
      {d.legal_marca_texto != null && (
        <div className="san-sub">
          <div className="san-campo">
            <label htmlFor="wMk">Texto do lembrete</label>
            <input id="wMk" className="san-input" value={d.legal_marca_texto} onChange={(e) => setDef(ctx, { legal_marca_texto: e.target.value })} />
          </div>
        </div>
      )}
    </div>
  );
}

// ── etapa 7 ──
function EtapaCarencia({ ctx, admin, aceiteAnterior }: { ctx: Ctx; admin: boolean; aceiteAnterior: CaixaDetalhe["aceite_carencia"] }) {
  const d = ctx.form.def;
  if (d.tipo === "exame") return <Faixa>Exame não tem carência. A etapa fica visível para você conferir.</Faixa>;
  return (
    <div className="san-wiz-etapa">
      <p className="san-nota" style={{ margin: 0 }}>Etapa sempre visível; preencher é opcional. Em branco = não informada (nunca zero).</p>
      <div className="san-linha">
        <div className="san-campo curto">
          <label htmlFor="wCL">Leite (dias)</label>
          <input id="wCL" className="san-input" type="number" min={0} value={campoNum(d.car_leite_dias)} placeholder="não sei" onChange={(e) => setDef(ctx, { car_leite_dias: intOuNulo(e.target.value) })} />
        </div>
        <div className="san-campo curto">
          <label htmlFor="wCC">Carne (dias)</label>
          <input id="wCC" className="san-input" type="number" min={0} value={campoNum(d.car_carne_dias)} placeholder="não sei" onChange={(e) => setDef(ctx, { car_carne_dias: intOuNulo(e.target.value) })} />
        </div>
      </div>
      <div className="san-campo">
        <span className="san-rot">O que fazer com o leite durante a carência</span>
        <div className="san-opcs" role="radiogroup" aria-label="Modo do leite">
          {MODOS_LEITE.map((m) => (
            <label key={m} className="san-opc">
              <input type="radio" name="wCm" checked={d.car_modo_leite === m} onChange={() => setDef(ctx, { car_modo_leite: m })} />
              <span><b>{ROTULO_MODO_LEITE[m]}</b><small>{AJUDA_MODO_LEITE[m]}</small></span>
            </label>
          ))}
        </div>
      </div>
      {aceiteAnterior && <p className="san-nota" style={{ margin: 0 }}>A versão atual tem aceite de {fmtData(aceiteAnterior.aceito_em.slice(0, 10))}. Salvar cria uma versão nova: aceite de novo para não virar pendência.</p>}
      {admin ? (
        <label className="san-liga">
          <input type="checkbox" checked={ctx.form.aceitarCarencia} onChange={(e) => ctx.setForm({ ...ctx.form, aceitarCarencia: e.target.checked })} />
          <span><b>Aceitar a carência ao salvar</b><small>Um clique; o seu nome e a data ficam no registro.</small></span>
        </label>
      ) : <p className="san-nota">Só o administrador aceita a carência.</p>}
      {!ctx.form.aceitarCarencia && (
        <Faixa tipo="atencao">Sem aceite, vira pendência na Agenda. Enquanto isso o leite vai para o tanque e o registro marca “sem aceite”. No dia, um pop-up pergunta o que fazer.</Faixa>
      )}
    </div>
  );
}

// ── etapa 8 ──
function EtapaFicha({ ctx }: { ctx: Ctx }) {
  const d = ctx.form.def;
  const alternar = (c: (typeof COLUNAS_FICHA)[number]) =>
    setDef(ctx, { ficha_colunas: d.ficha_colunas.includes(c) ? d.ficha_colunas.filter((x) => x !== c) : COLUNAS_FICHA.filter((x) => x === c || d.ficha_colunas.includes(x)) });
  const cols = d.ficha_colunas.length ? d.ficha_colunas : (["brinco", "dose", "aplicado", "obs"] as const);
  return (
    <div className="san-wiz-etapa">
      <div className="san-campo">
        <span className="san-rot">Colunas da ficha</span>
        <div className="san-opcs">
          {COLUNAS_FICHA.map((c) => (
            <label key={c} className="san-opc"><input type="checkbox" checked={d.ficha_colunas.includes(c)} onChange={() => alternar(c)} /><span>{ROTULO_COLUNA_FICHA[c]}</span></label>
          ))}
        </div>
      </div>
      <div className="san-campo">
        <span className="san-rot">Prévia da ficha vazia (para imprimir e lançar depois)</span>
        <div style={{ overflowX: "auto" }}>
          <FolhaVazia ficha={{
            tipo: "vazia", fazenda: null, titulo: `${d.tipo === "exame" ? "Exame" : "Vacina"} · ${d.nome_curto || d.nome || "novo cadastro"}`,
            caixa_ids: [], colunas: cols.map((c) => ({ chave: c, rotulo: ROTULO_COLUNA_FICHA[c] })), linhas_em_branco: 4,
            campos_cabecalho: ["data", "veterinario", "crmv", "produto", "partida"],
          }} />
        </div>
      </div>
      <div className="san-campo">
        <label htmlFor="wObs">Observação (opcional)</label>
        <textarea id="wObs" className="san-input" value={d.observacao || ""} onChange={(e) => setDef(ctx, { observacao: e.target.value })} />
      </div>
    </div>
  );
}

// ── etapa 9 ──
function EtapaRevisao({ ctx, apoio, editando }: { ctx: Ctx; apoio: Apoio; editando: { nome: string; versao: number | null } | null }) {
  const d = ctx.form.def;
  const chave = JSON.stringify(d);
  const { dados: previa, erro, carregando, recarregar } = useCarregar<PreviaCaixa>(() => previaCaixa(d, null), [chave]);
  const nomesCat = useMemo(() => new Map(apoio.categorias.map((c) => [c.id, c.nome])), [apoio.categorias]);
  const estq = apoio.estoque.find((e) => e.id === d.estoque_id)?.nome;
  const grupos = useMemo(() => {
    const g = new Map<string, string[]>();
    for (const f of previa?.fora || []) { const m = f.motivo || f.texto || "fora da regra"; g.set(m, [...(g.get(m) || []), f.numero]); }
    return [...g.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [previa]);
  const legal = [d.legal_crmv_pedir && "CRMV pedido", d.legal_atestado && `atestado em ${d.legal_atestado.dias ?? 30} d`,
    d.legal_comprovacao && `comprovação a cada ${d.legal_comprovacao.dias} d`, d.legal_leitura && "leitura de resultado",
    d.legal_reagente_aviso && "aviso de reagente", d.legal_marca_texto != null && "lembrete de marca"].filter(Boolean).join(" · ");
  return (
    <div className="san-wiz-etapa">
      <dl className="san-def">
        <dt>Nome</dt><dd>{d.nome || "(sem nome)"} · {ROTULO_TIPO[d.tipo]}{d.obrigatoria ? " · obrigatório" : ""}</dd>
        <dt>Estado</dt><dd>{ctx.form.ativo ? "Ativo" : "Inativo (não gera nada)"}{editando ? ` · salva como v${(editando.versao || 0) + 1}, vale daqui para frente` : ""}</dd>
        <dt>Produto</dt><dd>{d.tipo === "exame" ? "não se aplica" : textoProduto({ modo: d.produto_modo, texto: d.produto_texto, dose_valor: d.dose_valor, dose_unidade: d.dose_unidade, dose_x_kg: d.dose_x_kg }, estq)}</dd>
        <dt>Público</dt><dd>{textoPublico(d, nomesCat)}</dd>
        <dt>Janela</dt><dd>{textoJanela(d)} · ao fechar: {d.ao_fechar}</dd>
        <dt>Aviso</dt><dd>mínimo {d.aglo_min} · {d.aviso_antecedencia_dias} dias antes</dd>
        <dt>Legal</dt><dd>{legal || "nada ligado"}</dd>
        <dt>Carência</dt><dd>{d.tipo === "exame" ? "não se aplica" : `leite ${d.car_leite_dias ?? "?"} d · carne ${d.car_carne_dias ?? "?"} d${d.car_modo_leite ? " · " + ROTULO_MODO_LEITE[d.car_modo_leite].toLowerCase() : ""} · ${ctx.form.aceitarCarencia ? "aceita ao salvar" : "sem aceite (vira pendência)"}`}</dd>
      </dl>
      <Faixa>Prévia {previa ? `na data-base ${fmtData(previa.data_base)}` : `em ${fmtData(hojeISO())}`}. <b>Nada é gravado</b> até você salvar.</Faixa>
      {erro ? <Faixa tipo="alerta">{erro} <button type="button" className="san-link" onClick={recarregar}>Tentar de novo</button></Faixa>
        : carregando || !previa ? <div className="skeleton" style={{ height: "10rem" }} role="status" aria-label="Calculando a prévia" /> : (
          <div className="san-previa">
            <section className="san-bloco">
              <div className="san-bloco-cab"><h3>Entram · {previa.contagem.entram}</h3></div>
              <div className="san-bloco-corpo">
                <ul>{previa.entram.length ? previa.entram.slice(0, 60).map((x) => (
                  <li key={x.animal_id}><b className="san-num">{x.numero}</b> <span className="san-nota">{x.categoria || ""}</span>
                    <small>{x.motivos.filter((m) => m.ok).map((m) => m.texto).join(" · ") || x.texto}</small></li>
                )) : <li className="san-nota">Ninguém entra com essa regra hoje.</li>}</ul>
              </div>
            </section>
            <section className="san-bloco">
              <div className="san-bloco-cab"><h3>Ficam de fora · {previa.contagem.fora}</h3></div>
              <div className="san-bloco-corpo">
                <ul>{grupos.map(([m, ids]) => (
                  <li key={m}><b>{m}</b><small className="san-num">{ids.length}: {ids.slice(0, 14).join(", ")}{ids.length > 14 ? "…" : ""}</small></li>
                ))}</ul>
              </div>
            </section>
          </div>
        )}
    </div>
  );
}

// ── escolher do catálogo ou do zero ──
function Comecar({ onZero, onCatalogo, ocupado, erro }: { onZero: () => void; onCatalogo: (c: CatalogoItemFazenda) => void; ocupado: boolean; erro: string | null }) {
  const { dados, erro: erroCat, carregando, recarregar } = useCarregar(() => catalogoDaFazenda(), []);
  return (
    <div className="san-bloco">
      <div className="san-bloco-cab"><h3>Escolher do catálogo ou criar do zero</h3></div>
      <div className="san-bloco-corpo san-wiz-etapa">
        <p className="san-nota" style={{ margin: 0 }}>O catálogo central da CowData traz cadastros prontos e revisados. Escolha um, ajuste o que quiser nas próximas etapas e, ao salvar, ele é copiado para a sua fazenda. Cancelar não copia nada.</p>
        {erro && <Faixa tipo="alerta">{erro}</Faixa>}
        {erroCat ? <Faixa tipo="alerta">{erroCat} <button type="button" className="san-link" onClick={recarregar}>Tentar de novo</button></Faixa>
          : carregando ? <div className="skeleton" style={{ height: "8rem" }} role="status" aria-label="Carregando o catálogo" /> : (
            <div className="san-opcs lista">
              {(dados || []).map((c) => {
                const copia = c.caixas_da_fazenda.find((x) => x.estado !== "arquivada");
                return (
                  <button key={c.id} type="button" className="san-opc" disabled={ocupado || !c.versao_id} onClick={() => onCatalogo(c)}>
                    <span style={{ flex: 1 }}>
                      <b>{c.nome}</b> <span className="san-tag">v{c.versao_atual}</span> <span className="san-tag">{ROTULO_TIPO[c.tipo] || c.tipo}</span>
                      <small>{c.nota_mudanca || "Item do catálogo central."}{copia ? ` Já existe na fazenda (${copia.estado}${copia.nova_versao ? ", com versão nova disponível" : ""}).` : ""}</small>
                    </span>
                    <ArrowRight size={14} aria-hidden="true" />
                  </button>
                );
              })}
              {!dados?.length && <p className="san-nota">O catálogo central ainda não tem itens.</p>}
              <button type="button" className="san-opc tracejado" onClick={onZero} disabled={ocupado}>
                <span style={{ flex: 1 }}><b>Criar do zero</b><small>Começa com tudo em branco. Nada é copiado.</small></span>
                <Plus size={14} aria-hidden="true" />
              </button>
            </div>
          )}
      </div>
    </div>
  );
}

export function WizardCaixa({ caixaId: caixaIdInicial = null, passoInicial = 0, admin, onSair }: {
  caixaId?: number | null; passoInicial?: number; admin: boolean;
  /** Sai do wizard; `mensagem` vem quando algo foi salvo. */
  onSair: (mensagem?: string) => void;
}) {
  const [caixaId, setCaixaId] = useState<number | null>(caixaIdInicial);
  const [detalhe, setDetalhe] = useState<CaixaDetalhe | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [apoio, setApoio] = useState<Apoio | null>(null);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erroComecar, setErroComecar] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [erroSalvar, setErroSalvar] = useState<string | null>(null);
  const [copiadoDoCatalogo, setCopiadoDoCatalogo] = useState<string | null>(null);
  // Item do catálogo escolhido e ainda NÃO copiado (a cópia só nasce ao concluir).
  const [doCatalogo, setDoCatalogo] = useState<{ versaoId: number; versao: number; nome: string } | null>(null);
  const [tentativa, setTentativa] = useState(0);

  useEffect(() => {
    let vivo = true;
    Promise.all([
      carregarEstoqueSan().catch(() => [] as ItemEstoqueSan[]),
      carregarCategoriasSan().catch(() => []),
      listarCaixas("todas"),
      obterParametros().catch(() => null),
      caixaIdInicial ? obterCaixa(caixaIdInicial) : Promise.resolve(null),
    ]).then(([estoque, categorias, caixas, parametros, det]) => {
      if (!vivo) return;
      setApoio({ estoque, categorias, caixas, parametros });
      if (det) {
        setDetalhe(det);
        setForm({ def: definicaoCompleta(det.definicao), ativo: det.estado === "ativa", aceitarCarencia: det.carencia_aceita });
      }
    }).catch((e) => { if (vivo) setErroCarga(mensagemDoErro(e, "Não foi possível abrir o cadastro.")); });
    return () => { vivo = false; };
  }, [caixaIdInicial, tentativa]);

  async function escolherCatalogo(c: CatalogoItemFazenda) {
    setErroComecar(null);
    const copia = c.caixas_da_fazenda.find((x) => x.estado !== "arquivada");
    if (copia) {
      setOcupado(true);
      try {
        const det = await obterCaixa(copia.caixa_id);
        setDetalhe(det); setCaixaId(det.id);
        setForm({ def: definicaoCompleta(det.definicao), ativo: det.estado === "ativa", aceitarCarencia: det.carencia_aceita });
        setCopiadoDoCatalogo(`${det.nome} já existia na fazenda: você está editando a cópia (v${det.versao_numero}).`);
      } catch (e) { setErroComecar(mensagemDoErro(e)); } finally { setOcupado(false); }
      return;
    }
    if (!c.versao_id) return;
    setOcupado(true);
    try {
      const pv = await previaCopiaCatalogo(c.versao_id);
      setDoCatalogo({ versaoId: pv.versao_id, versao: pv.versao, nome: c.nome });
      setForm({ def: definicaoCompleta(pv.definicao), ativo: false, aceitarCarencia: false });
      setCopiadoDoCatalogo(`Do catálogo: ${c.nome} v${pv.versao}. Ajuste o que quiser; a cópia só é criada na fazenda quando você salvar.`
        + (pv.avisos.length ? ` ${pv.avisos.join(" ")}` : ""));
    } catch (e) {
      setErroComecar(mensagemDoErro(e, "Não foi possível abrir o item do catálogo."));
    } finally { setOcupado(false); }
  }

  if (erroCarga) return <Faixa tipo="alerta">{erroCarga} <button type="button" className="san-link" onClick={() => { setErroCarga(null); setTentativa((n) => n + 1); }}>Tentar de novo</button></Faixa>;
  if (!apoio) return <TelaSkeleton kpis={0} label="Abrindo o cadastro" />;
  if (!admin) return <Faixa tipo="atencao">Só o administrador da fazenda cadastra ou edita vacinas e exames.</Faixa>;
  if (!form) {
    return (
      <div className="san-pagina">
        <div className="san-acoes"><button type="button" className="btn-ghost" onClick={() => onSair()}>Voltar para a lista</button></div>
        <Comecar ocupado={ocupado} erro={erroComecar} onCatalogo={escolherCatalogo}
          onZero={() => setForm({ def: definicaoVazia(), ativo: false, aceitarCarencia: false })} />
      </div>
    );
  }

  const ctxDe = (f: Form, sf: (f: Form) => void): Ctx => ({ form: f, setForm: sf });
  const validarEtapa = (etapa: number) => async (f: Form) => {
    try {
      const r = await validarCaixa(f.def, etapa, caixaId);
      return r.ok ? null : r.erros.map((e) => e.mensagem).join(" ");
    } catch (e) {
      return mensagemDoErro(e, "Não foi possível conferir esta etapa. Tente de novo.");
    }
  };
  const editando = caixaId && detalhe ? { nome: detalhe.nome, versao: detalhe.versao_numero } : null;
  const passos: PassoWizard<Form>[] = PASSOS_TITULOS.map((titulo, i) => {
    const etapa = i + 1;
    return {
      id: `e${etapa}`, titulo,
      validar: etapa < 9 ? validarEtapa(etapa) : undefined,
      render: ({ form: f, setForm: sf }) => {
        const ctx = ctxDe(f, sf);
        switch (etapa) {
          case 1: return <EtapaIdentificacao ctx={ctx} apoio={apoio} caixaId={caixaId} />;
          case 2: return <EtapaProduto ctx={ctx} apoio={apoio} />;
          case 3: return <EtapaPublico ctx={ctx} apoio={apoio} caixaId={caixaId} />;
          case 4: return <EtapaJanela ctx={ctx} />;
          case 5: return <EtapaAviso ctx={ctx} apoio={apoio} />;
          case 6: return <EtapaLegal ctx={ctx} apoio={apoio} />;
          case 7: return <EtapaCarencia ctx={ctx} admin={admin} aceiteAnterior={detalhe?.aceite_carencia ?? null} />;
          case 8: return <EtapaFicha ctx={ctx} />;
          default: return <EtapaRevisao ctx={ctx} apoio={apoio} editando={editando} />;
        }
      },
    };
  });

  async function salvar(): Promise<boolean> {
    if (!form) return false;
    setErroSalvar(null); setSalvando(true);
    try {
      const aceitar = form.def.tipo !== "exame" && form.aceitarCarencia;
      let det: CaixaDetalhe;
      if (caixaId) {
        det = await novaVersaoCaixa(caixaId, form.def, aceitar);
        const queroAtiva = form.ativo, estaAtiva = det.estado === "ativa";
        if (queroAtiva !== estaAtiva && det.estado !== "arquivada") await mudarEstadoCaixas([det.id], queroAtiva ? "ativar" : "inativar");
        onSair(`${det.nome} salvo como v${det.versao_numero}. Vale daqui para frente.`);
      } else if (doCatalogo) {
        det = await ativarDoCatalogo(doCatalogo.versaoId, form.ativo ? "ativa" : "inativa", form.def, aceitar);
        onSair(`${det.nome} copiado do catálogo v${doCatalogo.versao} ${form.ativo ? "e ativo" : "como inativo"}.`);
      } else {
        det = await criarCaixa(form.def, form.ativo ? "ativa" : "inativa", aceitar);
        onSair(`${det.nome} criado ${form.ativo ? "e ativo" : "como inativo"}.`);
      }
      return true;
    } catch (e) {
      const erros = errosValidacaoDoErro(e);
      setErroSalvar(erros.length ? erros.map((x) => `Etapa ${x.etapa} (${PASSOS_TITULOS[x.etapa - 1] || ""}): ${x.mensagem}`).join(" ")
        : mensagemDoErro(e, "Não foi possível salvar o cadastro."));
      return false;
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="san-pagina">
      {copiadoDoCatalogo && <Faixa tipo="ok">{copiadoDoCatalogo}</Faixa>}
      <WizardProtocolo<Form>
        chaveRascunho={caixaId || doCatalogo ? null : "wizard-sanitario:nova-caixa"}
        form={form} setForm={setForm}
        ehVazio={(f) => !(f.def.nome || "").trim()}
        passos={passos}
        passoInicial={Math.min(Math.max(passoInicial, 0), 8)}
        onCancelar={() => onSair()}
        onConcluir={salvar}
        salvando={salvando}
        erro={erroSalvar}
        ouroNoConcluir
        rotuloConcluir={caixaId ? "Salvar versão nova" : "Salvar cadastro"}
        tituloTopo={editando ? `Editando ${editando.nome} (v${editando.versao ?? 1})` : doCatalogo ? `Do catálogo: ${doCatalogo.nome}` : "Novo cadastro"}
      />
    </div>
  );
}
