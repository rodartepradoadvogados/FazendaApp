"use client";
// Excluir lançamento — PASSO 1: escolher o tipo (variante desktop de apresentação, página cheia; Captura largura 1800).
//
// Substitui components/exclusao/EscolherTipo.tsx (v2): 23+ barras de largura total → grade de blocos compactos (5 colunas)
// agrupada por `dominio`, com `plural` (nome curto), `contagem` e `dica`; Cadastros recolhido. Passa a USAR os campos que a v2
// ignorava: dominio, plural, dica, cadastro, contagem (GET /exclusoes/tipos) e leva `sem_filtro_data` ao passo 2.
//
// A versão ligada a dados precisa preservar:
//  • lista de GET /exclusoes/tipos filtrada por `ocultarTipos`; busca LOCAL (label + plural + dica); `todos_lancamentos` é
//    o bloco largo (sai da grade); clicar num bloco chama `aoEscolher({tipo, id:"", titulo: label})` como hoje;
//  • `contagem` null → "—" (hoje só 10 tipos contam: financeiro, animal, estoque, compra_animal, compra_semen,
//    venda_animal, pessoa, lote, fornecedor, doenca);
//  • tipo sem `dominio` (os do REGISTRO sem META) cai em "Outros" até o backend completar META_TIPOS;
//  • busca que casa com algum Cadastro abre o grupo sozinha; autoFocus no campo de busca;
//  • abas Apagar/Pedidos/Trilha e o aviso do topo vêm de MolduraExcluir (papel decide texto do aviso e o rótulo
//    "Pedidos" × "Meus pedidos"; Trilha só admin).
import React, { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { Ajuda, Passo, Selo } from "@/components/gerencial/kit";
import { DOMINIOS, MolduraExcluir, TIPOS, TODOS, fmtN, nomeCurto, type TipoEx } from "./excluirComum";


function Bloco({ t, cor, onEscolher }: { t: TipoEx; cor: string; onEscolher?: (t: TipoEx) => void }) {
  return (
    <button type="button" className="gx-bloco" data-destaque={t.destaque ? "true" : undefined} title={`${t.label} — ${t.dica}`}
      style={{ ["--gx-cor" as string]: cor }} onClick={() => onEscolher?.(t)}>
      <span className="gx-bloco-ic"><t.Icone size={17} aria-hidden /></span>
      <span className="gx-bloco-nome">{nomeCurto(t)}{t.novo && <Selo tom="atencao">Novo</Selo>}</span>
      <span className="gx-bloco-n" aria-label={t.contagem == null ? "sem contagem" : `${t.contagem} registros`}>{fmtN(t.contagem)}</span>
      <span className="gx-bloco-dica">{t.dica}</span>
    </button>
  );
}

function Grupo({ id, nome, cor, tipos }: { id: string; nome: string; cor: string; tipos: TipoEx[] }) {
  return (
    <section className="gx-grupo" aria-labelledby={`gx-g-${id}`} style={{ ["--gx-cor" as string]: cor }}>
      <div className="gx-grupo-cab" id={`gx-g-${id}`}>{nome}<span>· {tipos.length} {tipos.length === 1 ? "tipo" : "tipos"}</span></div>
      <div className="gx-grade">{tipos.map((t) => <Bloco key={t.id} t={t} cor={cor} />)}</div>
    </section>
  );
}

export function ExcluirTipos() {
  const [termo, setTermo] = useState("");
  const [cadAberto, setCadAberto] = useState(false);

  const q = termo.trim().toLowerCase();
  const visiveis = useMemo(
    () => TIPOS.filter((t) => !q || `${t.label} ${t.plural} ${t.dica}`.toLowerCase().includes(q)),
    [q],
  );
  const principais = DOMINIOS.filter((d) => d.id !== "cad");
  const cadastros = visiveis.filter((t) => t.cadastro);
  const cadVisivel = cadAberto || (q !== "" && cadastros.length > 0);
  const total = TIPOS.length + 1;

  return (
    <MolduraExcluir>
      <Passo n={1} id="ex1-p1" titulo="O que você quer apagar?"
        direita={<span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }} aria-live="polite">{q ? `${visiveis.length} de ${TIPOS.length} tipos` : `${total} tipos`}</span>}>
        <div className="gx-linha-busca">
          <div className="gx-busca">
            <Search size={14} aria-hidden />
            <input type="search" value={termo} onChange={(e) => setTermo(e.target.value)} placeholder="Buscar um tipo — diagnóstico, parto, nota…" aria-label="Buscar tipo de lançamento" />
          </div>
          <button type="button" className="gx-bloco gx-todos" title={`${TODOS.label} — ${TODOS.dica}`}>
            <span className="gx-bloco-ic"><TODOS.Icone size={22} aria-hidden /></span>
            <span className="gx-bloco-nome">{TODOS.plural} <span style={{ fontWeight: 600, color: "var(--text-muted)" }}>(mais recentes primeiro)</span></span>
            <span className="gx-bloco-n" aria-label={`${TODOS.contagem} registros`}>{fmtN(TODOS.contagem)}</span>
            <span className="gx-bloco-dica">{TODOS.dica}</span>
          </button>
        </div>

        {visiveis.length === 0 && <p className="gv-ajuda">Nenhum tipo encontrado para “{termo}”.</p>}

        {principais.map((d) => {
          const lista = visiveis.filter((t) => !t.cadastro && t.dominio === d.id);
          return lista.length > 0 ? <Grupo key={d.id} id={d.id} nome={d.nome} cor={d.cor} tipos={lista} /> : null;
        })}

        {cadastros.length > 0 && (
          <section className="gx-grupo" aria-labelledby="gx-g-cad" style={{ ["--gx-cor" as string]: "var(--cat-acesso)" }}>
            <div className="gx-grupo-cab" id="gx-g-cad">Cadastros<span>· {cadastros.length} tipos</span></div>
            {!cadVisivel ? (
              <button type="button" className="gx-cad-cab" aria-expanded={false} aria-controls="gx-cad-grade" onClick={() => setCadAberto(true)}>
                <ChevronRight size={15} aria-hidden />
                <Selo tom="atencao">Raros e perigosos</Selo>
                <span className="gx-cad-txt">Lote, fornecedor, pessoa, doença, princípio ativo, safra… Apagar um cadastro em uso muda tudo o que depende dele (animais ficam sem lote, notas perdem o fornecedor). Se o dado só está errado, prefira editar.</span>
                <span className="gx-cad-acao">Mostrar os {cadastros.length} cadastros</span>
              </button>
            ) : (
              <>
                <button type="button" className="gx-cad-cab" aria-expanded={true} aria-controls="gx-cad-grade" onClick={() => setCadAberto(false)}>
                  <ChevronDown size={15} aria-hidden />
                  <Selo tom="atencao">Raros e perigosos</Selo>
                  <span className="gx-cad-txt">Cadastro em uso não sai sem consequência: o servidor mostra o que perde a ligação e pede confirmação digitada.</span>
                  <span className="gx-cad-acao">Recolher</span>
                </button>
                <div className="gx-grade" id="gx-cad-grade">{cadastros.map((t) => <Bloco key={t.id} t={t} cor="var(--cat-acesso)" />)}</div>
              </>
            )}
          </section>
        )}

        <Ajuda>Escolha o tipo para ver os registros dele. Nada é apagado nesta etapa; antes de confirmar você vê exatamente o que muda.</Ajuda>
      </Passo>
    </MolduraExcluir>
  );
}
