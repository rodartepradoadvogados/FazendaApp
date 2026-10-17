"use client";
// Excluir lançamento — PASSO 3: conferir o impacto e decidir (aqui: desfazer o toque de 11153, 17/10/2026).
// Variante desktop de apresentação, página cheia (Captura largura 1800). Dados de exemplo; sem fetch.
//
// Substitui PainelImpacto.tsx + DecisaoExclusao.tsx + ResultadoExclusao.tsx (v2). Corrige: o impacto não dizia QUAL
// registro estava sendo apagado (agora a faixa "Você vai desfazer" repete o item + tipo + id), 4 blocos em uma coluna
// longa (agora 2×2 compactos, com TEXTO além da cor), botão "Apagar" em marinho igual aos demais (agora vermelho de
// perigo com o verbo inteiro: "Apagar definitivamente"), e o resultado numa tela solta (agora volta na barra).
//
// A versão ligada a dados precisa preservar:
//  • POST /exclusoes/impacto → {item{tipo,id,titulo}, bloqueia[], apagar[], reverter[], avisos[], risco, porque[], editar_url};
//    lote (itens[] ≤ 50, só admin) usa o mesmo layout com a faixa "Lote de N itens" e agruparPorNota nas parcelas;
//    para lote/risco use riscoDe/somarImpacto de lib/exclusao.ts;
//  • bloqueado (`bloqueia.length > 0`): some a decisão, fica SÓ "Voltar" e o texto do que fazer (`bloqueia[].fazer`);
//  • risco proporcional (servidor repete tudo, a tela só mostra): baixo = só o botão; médio = motivo obrigatório (operador
//    SEMPRE motivo); alto = motivo + digitar a confirmação ("APAGAR"; para ficha de animal, o número do animal →
//    confirmacaoEsperada). `porque` entra no texto do risco;
//  • "Corrigir em vez de apagar" = `editar_url` do impacto (ou destinoEditar(tipo, id));
//  • admin exclui na hora (POST /exclusoes/confirmar); operador GERA PEDIDO e o botão vira "Enviar pedido de exclusão";
//    retorno: excluido → comprovante (código EX-AAAA-NNNN) + "ficou na trilha" (guardada 30 dias); solicitado/ja_pedido/apoiado →
//    "Pedido enviado" / "Você já tinha pedido" / "Você apoiou o pedido de <fulano>" + atalho para Meus pedidos;
//  • depois de apagar a tela volta ao passo 2 já com a lista recarregada e a barra mostra o retorno (bloco "Depois de apagar").
import React, { useState } from "react";
import { AlertTriangle, ArrowLeft, Ban, Check, Pencil, Trash2, Undo2 } from "lucide-react";
import { BarraAcao, Campo, Passo, Selo } from "@/components/gerencial/kit";
import { Migalhas, MolduraExcluir } from "./excluirComum";

type LinhaImp = { titulo: string; consequencia: string };
type Risco = "baixo" | "medio" | "alto";

// Exemplo no formato de ImpactoExclusao (lib/exclusao.ts). O servidor devolve `apagar` com o texto do exame em `titulo`;
// as consequências detalhadas de `reverter`/`avisos` são do exemplo.
const IMPACTO = {
  item: { tipo: "diagnostico", id: "4821:toque", titulo: "Toque de 11153 em 17/10/2026 (POSITIVO · Palpação)" },
  consequenciaItem: "o animal volta a «a tocar»",
  bloqueia: [] as { titulo: string; motivo: string; fazer: string }[],
  apagar: [{ titulo: "Toque de 11153 em 17/10/2026 (POSITIVO · Palpação)", consequencia: "Só o exame é desfeito; a inseminação de 28/08/2026 continua no histórico." }] as LinhaImp[],
  reverter: [
    { titulo: "Situação reprodutiva de 11153", consequencia: "Volta de PRENHE (toque positivo) para «a tocar»." },
    { titulo: "Agenda reprodutiva", consequencia: "O retoque previsto para 26/11/2026 sai da Agenda; a vaca volta à lista de diagnóstico." },
  ] as LinhaImp[],
  avisos: [{ titulo: "Não dá para desfazer", consequencia: "Depois de apagado, só relançando o diagnóstico em Lançamentos › Diagnóstico de gestação." }] as LinhaImp[],
  risco: "medio" as Risco,
  porque: ["mexe em outros dados (situação reprodutiva e agenda)"],
};

const ROTULO_RISCO: Record<Risco, string> = { baixo: "Risco baixo", medio: "Risco médio", alto: "Risco alto" };
const NIVEIS: { id: Risco; titulo: string; texto: string }[] = [
  { id: "baixo", titulo: "Baixo", texto: "Um registro isolado, nada mais muda. Basta o botão." },
  { id: "medio", titulo: "Médio", texto: "Mexe em outros dados ou apaga mais de um. Motivo obrigatório." },
  { id: "alto", titulo: "Alto", texto: "Apaga muita coisa ou cadastro em uso. Motivo e digitar APAGAR (ficha de animal: o número)." },
];

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

function Lista({ itens }: { itens: LinhaImp[] }) {
  return (
    <ul>
      {itens.map((l) => <li key={l.titulo}><b>{l.titulo}</b><span>{l.consequencia}</span></li>)}
    </ul>
  );
}

const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;

export function ExcluirConfirmar() {
  const [motivo, setMotivo] = useState("Toque lançado no animal errado (era a 3335).");
  const risco = IMPACTO.risco;
  const pedeMotivo = true; // admin: médio e alto; operador: sempre
  const liberado = !pedeMotivo || motivo.trim().length > 0;

  return (
    <MolduraExcluir>
      <Migalhas itens={["Tipos", "Diagnósticos de gestação", "11153 · Toque de 17/10/2026"]} />

      <div className="gx-desfazer" role="group" aria-label="O que será desfeito">
        <div>
          <div className="gx-desfazer-rotulo">Você vai desfazer</div>
          <div className="gx-desfazer-titulo">Toque de 11153 em 17/10/2026 (POSITIVO)</div>
          <div className="gx-desfazer-sub">O animal volta a «a tocar». A inseminação de 28/08/2026 continua.</div>
          <div className="gx-desfazer-meta">
            <span>Tipo <b>Diagnóstico de gestação</b></span>
            <span aria-hidden="true">·</span>
            <span>Registro <b>{IMPACTO.item.id}</b></span>
            <span aria-hidden="true">·</span>
            <span>Método <b>Palpação</b></span>
          </div>
        </div>
        <div className="gx-desfazer-dir">
          <Selo tom="atencao" titulo={IMPACTO.porque.join("; ")}>{ROTULO_RISCO[risco]}</Selo>
          <a href="#editar" className="gx-acao-linha"><Pencil size={12} aria-hidden />Corrigir em vez de apagar</a>
        </div>
      </div>

      <Passo n={3} id="ex3-p3" titulo="Confira o que muda"
        direita={<span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Porque: {IMPACTO.porque.join("; ")}.</span>}>
        <div className="gx-impacto" aria-live="polite">
          <Bloco tom="bloqueio" icone={<Ban size={14} aria-hidden />} titulo="Bloqueia" sub="Impede de apagar até você resolver"
            selo={<Selo tom="ok">Livre</Selo>}>
            <p className="gx-imp-vazio"><Check size={14} aria-hidden style={{ color: "var(--ft-verde)" }} />Nada bloqueia esta exclusão.</p>
          </Bloco>
          <Bloco tom="apagar" icone={<Trash2 size={14} aria-hidden />} titulo="Será apagado" sub="Some do sistema e não volta"
            selo={<Selo tom="bloqueio">{plural(IMPACTO.apagar.length, "item", "itens")}</Selo>}>
            <Lista itens={IMPACTO.apagar} />
          </Bloco>
          <Bloco tom="reverter" icone={<Undo2 size={14} aria-hidden />} titulo="Será revertido" sub="É ajustado de volta"
            selo={<Selo tom="info">{plural(IMPACTO.reverter.length, "ajuste", "ajustes")}</Selo>}>
            <Lista itens={IMPACTO.reverter} />
          </Bloco>
          <Bloco tom="aviso" icone={<AlertTriangle size={14} aria-hidden />} titulo="Avisos" sub="Atenção antes de confirmar"
            selo={<Selo tom="atencao">{plural(IMPACTO.avisos.length, "aviso", "avisos")}</Selo>}>
            <Lista itens={IMPACTO.avisos} />
          </Bloco>
        </div>
      </Passo>

      <Passo n={4} id="ex3-p4" titulo="Confirme">
        <div className="gx-decisao">
          <div className="gx-campo-motivo" style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
            <Campo rotulo="Por que está apagando? (fica na trilha)" id="ex3-motivo">
              <textarea rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
            </Campo>
            <p className="gv-ajuda">Obrigatório neste risco. Você é administrador: apaga na hora. Quando um operador faz isto, vira um pedido que o administrador decide.</p>
          </div>
          <div>
            <div className="gx-niveis" role="group" aria-label="O que cada risco exige">
              {NIVEIS.map((nv) => (
                <div key={nv.id} className="gx-nivel" data-atual={nv.id === risco ? "true" : undefined}>
                  <b>{nv.titulo}{nv.id === risco && <> · <span style={{ color: "var(--ft-ouro-txt)" }}>este registro</span></>}</b>
                  {nv.texto}
                </div>
              ))}
            </div>
            <p className="gv-ajuda" style={{ marginTop: "0.4rem" }}>Digitar APAGAR não é exigido neste risco.</p>
          </div>
        </div>
      </Passo>

      <BarraAcao
        resumo="Apagar 1 exame · Toque de 11153 (17/10/2026)"
        detalhe={`${ROTULO_RISCO[risco]} · não dá para desfazer · fica na trilha com o seu motivo`}
        secundaria={<button type="button" className="btn-ghost" style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", whiteSpace: "nowrap" }}><ArrowLeft size={14} aria-hidden />Voltar</button>}
        acao={<button type="button" className="gx-perigo" disabled={!liberado}><Trash2 size={15} aria-hidden />Apagar definitivamente</button>}
      />

      <div className="gx-depois">
        <div className="gv-rotulo">Depois de apagar · a tela volta ao passo 2 e a barra mostra o retorno</div>
        <BarraAcao
          retorno={
            <>
              <span className="gx-ok" role="status"><Check size={14} aria-hidden /> Excluído: toque de 11153 em 17/10/2026.</span>
              <span>Comprovante <span className="gx-comprovante">EX-2026-0007</span></span>
              <span style={{ color: "var(--text-muted)" }}>Ficou na trilha: quem, quando e o quê (guardada por 30 dias).</span>
              <span style={{ flex: 1 }} />
              <button type="button" className="gx-acao-linha">Ver na trilha</button>
            </>
          }
          resumo="Nenhum registro em confirmação"
          detalhe="A lista foi recarregada: o animal 11153 já aparece em «a tocar» no Diagnóstico de gestação."
          acao={<button type="button" className="btn-primary">Apagar outro</button>}
        />
      </div>
    </MolduraExcluir>
  );
}
