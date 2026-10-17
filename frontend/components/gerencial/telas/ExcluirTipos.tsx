"use client";
// Excluir lançamento — PASSO 1: escolher o tipo (página cheia). Dados REAIS de GET /exclusoes/tipos, já filtrados por
// `ocultarTipos` pelo ExclusaoPage. Grade de blocos compactos (5 colunas) agrupada por `dominio`, com `plural` (nome curto),
// `contagem` e `dica`; Cadastros recolhido. A moldura (abas + aviso) vem de ExclusaoPage.
//
// Preservado do EscolherTipo v2:
//  • busca LOCAL (label + plural + dica) com autoFocus; busca que casa com algum Cadastro abre o grupo sozinha;
//  • `todos_lancamentos` é o bloco largo (sai da grade); clicar num bloco escolhe o tipo (aoEscolher);
//  • `contagem` null → "—"; tipo sem `dominio` (sem META no servidor) cai em "Outros";
//  • `sem_filtro_data` do tipo segue para o passo 2 dentro do próprio tipo escolhido.
import React, { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { Ajuda, Passo, Selo } from "@/components/gerencial/kit";
import { agruparTipos, fmtContagem, nomeCurto, type TipoApi } from "@/lib/exclusaoTela";
import { TIPOS_DESTAQUE, iconeDoTipo } from "./excluirComum";

function Bloco({ t, cor, onEscolher }: { t: TipoApi; cor: string; onEscolher: (t: TipoApi) => void }) {
  const Icone = iconeDoTipo(t.id);
  return (
    <button type="button" className="gx-bloco" data-destaque={TIPOS_DESTAQUE.has(t.id) ? "true" : undefined} title={`${t.label}${t.dica ? ` — ${t.dica}` : ""}`}
      style={{ ["--gx-cor" as string]: cor }} onClick={() => onEscolher(t)}>
      <span className="gx-bloco-ic"><Icone size={17} aria-hidden /></span>
      <span className="gx-bloco-nome">{nomeCurto(t)}</span>
      <span className="gx-bloco-n" aria-label={t.contagem == null ? "sem contagem" : `${t.contagem} registros`}>{fmtContagem(t.contagem)}</span>
      <span className="gx-bloco-dica">{t.dica ?? ""}</span>
    </button>
  );
}

function Grupo({ id, nome, cor, tipos, onEscolher }: { id: string; nome: string; cor: string; tipos: TipoApi[]; onEscolher: (t: TipoApi) => void }) {
  return (
    <section className="gx-grupo" aria-labelledby={`gx-g-${id}`} style={{ ["--gx-cor" as string]: cor }}>
      <div className="gx-grupo-cab" id={`gx-g-${id}`}>{nome}<span>· {tipos.length} {tipos.length === 1 ? "tipo" : "tipos"}</span></div>
      <div className="gx-grade">{tipos.map((t) => <Bloco key={t.id} t={t} cor={cor} onEscolher={onEscolher} />)}</div>
    </section>
  );
}

export function ExcluirTipos({ tipos, carregando, erro, onEscolher, onRecarregar }: {
  tipos: TipoApi[]; carregando: boolean; erro: string | null; onEscolher: (t: TipoApi) => void; onRecarregar: () => void;
}) {
  const [termo, setTermo] = useState("");
  const [cadAberto, setCadAberto] = useState(false);

  const q = termo.trim();
  const ag = useMemo(() => agruparTipos(tipos, termo), [tipos, termo]);
  const cadVisivel = cadAberto || (q !== "" && ag.cadastros.length > 0);
  const Todos = ag.todos ? iconeDoTipo(ag.todos.id) : null;

  return (
    <Passo n={1} id="ex1-p1" titulo="O que você quer apagar?"
      direita={<span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }} aria-live="polite">{q ? `${ag.visiveis} de ${ag.total} tipos` : `${ag.total} tipos`}</span>}>
      <div className="gx-linha-busca">
        <div className="gx-busca">
          <Search size={14} aria-hidden />
          <input type="search" autoFocus value={termo} onChange={(e) => setTermo(e.target.value)} placeholder="Buscar um tipo — diagnóstico, parto, nota…" aria-label="Buscar tipo de lançamento" />
        </div>
        {ag.todos && Todos && (
          <button type="button" className="gx-bloco gx-todos" title={`${ag.todos.label}${ag.todos.dica ? ` — ${ag.todos.dica}` : ""}`} onClick={() => onEscolher(ag.todos!)}>
            <span className="gx-bloco-ic"><Todos size={22} aria-hidden /></span>
            <span className="gx-bloco-nome">Todos os lançamentos <span style={{ fontWeight: 600, color: "var(--text-muted)" }}>(mais recentes primeiro)</span></span>
            <span className="gx-bloco-n" aria-label={ag.todos.contagem == null ? "sem contagem" : `${ag.todos.contagem} registros`}>{fmtContagem(ag.todos.contagem)}</span>
            <span className="gx-bloco-dica">{ag.todos.dica || "Busca em todos os lançamentos — para quando você não sabe em qual tipo foi lançado."}</span>
          </button>
        )}
      </div>

      {erro && (
        <div className="gv-aviso" role="alert" data-tom="erro">
          <span>Não consegui carregar os tipos: {erro}</span>
          <button type="button" className="gx-link" onClick={onRecarregar}>Tentar de novo</button>
        </div>
      )}
      {carregando && !erro && <p className="gv-ajuda" role="status">Carregando os tipos…</p>}
      {!carregando && !erro && ag.visiveis === 0 && <p className="gv-ajuda">{q ? <>Nenhum tipo encontrado para “{termo}”.</> : "Nenhum tipo disponível."}</p>}

      {ag.grupos.map((g) => <Grupo key={g.id} id={g.id} nome={g.nome} cor={g.cor} tipos={g.tipos} onEscolher={onEscolher} />)}

      {ag.cadastros.length > 0 && (
        <section className="gx-grupo" aria-labelledby="gx-g-cad" style={{ ["--gx-cor" as string]: "var(--cat-acesso)" }}>
          <div className="gx-grupo-cab" id="gx-g-cad">Cadastros<span>· {ag.cadastros.length} {ag.cadastros.length === 1 ? "tipo" : "tipos"}</span></div>
          {!cadVisivel ? (
            <button type="button" className="gx-cad-cab" aria-expanded={false} aria-controls="gx-cad-grade" onClick={() => setCadAberto(true)}>
              <ChevronRight size={15} aria-hidden />
              <Selo tom="atencao">Raros e perigosos</Selo>
              <span className="gx-cad-txt">Lote, fornecedor, pessoa, doença, princípio ativo, safra… Apagar um cadastro em uso muda tudo o que depende dele (animais ficam sem lote, notas perdem o fornecedor). Se o dado só está errado, prefira editar.</span>
              <span className="gx-cad-acao">Mostrar os {ag.cadastros.length} cadastros</span>
            </button>
          ) : (
            <>
              <button type="button" className="gx-cad-cab" aria-expanded={true} aria-controls="gx-cad-grade" onClick={() => setCadAberto(false)}>
                <ChevronDown size={15} aria-hidden />
                <Selo tom="atencao">Raros e perigosos</Selo>
                <span className="gx-cad-txt">Cadastro em uso não sai sem consequência: o servidor mostra o que perde a ligação e pede confirmação digitada.</span>
                <span className="gx-cad-acao">Recolher</span>
              </button>
              <div className="gx-grade" id="gx-cad-grade">{ag.cadastros.map((t) => <Bloco key={t.id} t={t} cor="var(--cat-acesso)" onEscolher={onEscolher} />)}</div>
            </>
          )}
        </section>
      )}

      <Ajuda>Escolha o tipo para ver os registros dele. Nada é apagado nesta etapa; antes de confirmar você vê exatamente o que muda.</Ajuda>
    </Passo>
  );
}
