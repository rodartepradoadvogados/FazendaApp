"use client";
// Excluir lançamento (página cheia) — 3 passos ligados aos endpoints reais:
//   1 · tipo      GET  /exclusoes/tipos                      (ExcluirTipos)
//   2 · registros GET  /exclusoes/buscar  + POST /exclusoes/impacto {tipo,id | itens[] ≤ 50, só admin}  (ExcluirRegistros)
//   3 · confirmar POST /exclusoes/confirmar                  (ExcluirConfirmar) — admin exclui na hora; operador GERA PEDIDO
// As abas Pedidos / Trilha ficam na moldura (Pedidos: admin decide, operador acompanha; Trilha só admin).
// Props preservadas: `ocultarTipos` (Cadastro esconde "animal"). As telas vivem em components/gerencial/telas/.
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  confirmarExclusao, confirmarExclusaoLote, ehAdmin, fetchMeusPedidosExclusao, fetchPendentesExclusao, fetchTiposExclusao,
  impactoExclusao, impactoExclusaoLote,
} from "@/lib/api";
import type { ImpactoExclusao } from "@/lib/exclusao";
import {
  itensDoLote, mensagemDe, montarRetorno, tipoDoRegistro, type RegistroBusca, type ResultadoApi, type Selecao, type TipoApi,
} from "@/lib/exclusaoTela";
import { MolduraExcluir, type AbaId } from "@/components/gerencial/telas/excluirComum";
import { ExcluirTipos } from "@/components/gerencial/telas/ExcluirTipos";
import { ExcluirRegistros } from "@/components/gerencial/telas/ExcluirRegistros";
import { ExcluirConfirmar } from "@/components/gerencial/telas/ExcluirConfirmar";
import { useExclusao, type Alvo } from "./useExclusao";
import { PedidosAdmin } from "./PedidosAdmin";
import { MeusPedidos } from "./MeusPedidos";
import { TrilhaExclusao } from "./TrilhaExclusao";

export function ExclusaoPage({ ocultarTipos }: { ocultarTipos?: string[] } = {}) {
  const [aba, setAba] = useState<AbaId>("apagar");
  const [pendentes, setPendentes] = useState(0);
  const [tipos, setTipos] = useState<TipoApi[]>([]);
  const [carregandoTipos, setCarregandoTipos] = useState(true);
  const [erroTipos, setErroTipos] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  // Papel lido do navegador: no servidor (SSR) vale "não admin" e o cliente corrige sem erro de hidratação.
  const souAdmin = useSyncExternalStore(() => () => {}, () => ehAdmin(), () => false);
  const [enviando, setEnviando] = useState(false);
  const ex = useExclusao();
  const { estado } = ex;
  const topo = useRef<HTMLDivElement>(null);
  const primeiraEtapa = useRef(true);

  useEffect(() => {
    let vivo = true;
    fetchTiposExclusao()
      .then((t: TipoApi[]) => { if (vivo) { setTipos(ocultarTipos ? t.filter((x) => !ocultarTipos.includes(x.id)) : t); setErroTipos(null); } })
      .catch((e) => { if (vivo) setErroTipos(mensagemDe(e, "falha de rede")); })
      .finally(() => { if (vivo) setCarregandoTipos(false); });
    return () => { vivo = false; };
    // `ocultarTipos` é fixo por tela (Cadastro passa ["animal"]); só uma nova tentativa recarrega.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tentativa]);
  const recarregarTipos = () => { setCarregandoTipos(true); setErroTipos(null); setTentativa((n) => n + 1); };

  // Contador da aba Pedidos: admin = pedidos esperando decisão; operador = os seus ainda pendentes.
  useEffect(() => {
    if (aba !== "apagar" && aba !== "pedidos") return;
    let vivo = true;
    const contar = souAdmin
      ? fetchPendentesExclusao().then((p: unknown[]) => p.length)
      : fetchMeusPedidosExclusao().then((p: { status: string }[]) => p.filter((x) => x.status === "pendente").length);
    contar.then((n: number) => { if (vivo) setPendentes(n); }).catch(() => {});
    return () => { vivo = false; };
  }, [souAdmin, aba, estado.recarga]);

  // A cada troca de passo o foco vai para o topo do conteúdo (leitor de tela e teclado acompanham a mudança).
  useEffect(() => {
    if (primeiraEtapa.current) { primeiraEtapa.current = false; return; }
    topo.current?.focus();
  }, [estado.etapa]);

  const calcular = async (alvo: Alvo, pedir: () => Promise<unknown>) => {
    ex.setCarregando(true);
    try { ex.setImpacto(alvo, (await pedir()) as ImpactoExclusao); }
    catch (e) { ex.setErro(mensagemDe(e, "Erro ao calcular o impacto")); }
  };

  const apagarUm = (r: RegistroBusca) => {
    const t = tipoDoRegistro(r, estado.tipo!.id);
    return calcular(
      { lote: false, itens: [{ tipo: t, id: String(r.id) }], registros: [r], tipoLista: estado.tipo!.id },
      () => impactoExclusao(t, String(r.id)),
    );
  };

  const apagarLote = (sel: Selecao) => {
    const itens = itensDoLote(sel, estado.tipo!.id);
    return calcular({ lote: true, itens, registros: [...sel.values()], tipoLista: estado.tipo!.id }, () => impactoExclusaoLote(itens));
  };

  const confirmar = async () => {
    const { alvo, impacto, motivo, confirmacao } = estado;
    if (!alvo || !impacto) return;
    setEnviando(true);
    try {
      const m = motivo.trim() || undefined;
      const c = confirmacao.trim() || undefined;
      const r: ResultadoApi = alvo.lote
        ? await confirmarExclusaoLote(alvo.itens, m, c)
        : await confirmarExclusao(impacto.item.tipo, impacto.item.id, m, c);
      ex.concluido(montarRetorno(r, alvo.registros[0]?.titulo ?? impacto.item.titulo, alvo.lote ? alvo.registros.length : 0));
    } catch (e) {
      ex.setErro(mensagemDe(e, "Erro ao excluir"));
    } finally {
      setEnviando(false);
    }
  };

  const irParaAba = (a: AbaId) => { setAba(a); };

  return (
    <MolduraExcluir aba={aba} onAba={irParaAba} souAdmin={souAdmin} pedidosPendentes={pendentes}>
      <div ref={topo} tabIndex={-1} style={{ outline: "none" }}>
        <div hidden={aba !== "apagar"}>
          {estado.etapa === "tipos" && (
            <ExcluirTipos tipos={tipos} carregando={carregandoTipos} erro={erroTipos} onEscolher={ex.escolherTipo} onRecarregar={recarregarTipos} />
          )}
          {estado.tipo && estado.etapa !== "tipos" && (
            // Fica montado (só escondido) durante a confirmação: "Voltar" devolve o filtro, a página e as caixas como estavam.
            <div hidden={estado.etapa === "confirmar"}>
              <ExcluirRegistros
                key={estado.tipo.id}
                tipo={estado.tipo}
                tipos={tipos}
                souAdmin={souAdmin}
                recarga={estado.recarga}
                retorno={estado.retorno}
                calculando={estado.carregando}
                erro={estado.etapa === "registros" ? estado.erro : null}
                onVoltarTipos={ex.voltarTipos}
                onEscolherTipo={ex.escolherTipo}
                onApagar={apagarUm}
                onLote={apagarLote}
                onAtalho={irParaAba}
                onFecharRetorno={ex.limparRetorno}
              />
            </div>
          )}
          {estado.etapa === "confirmar" && estado.tipo && estado.alvo && estado.impacto && (
            <ExcluirConfirmar
              tipo={estado.tipo}
              tipos={tipos}
              alvo={estado.alvo}
              impacto={estado.impacto}
              souAdmin={souAdmin}
              motivo={estado.motivo}
              confirmacao={estado.confirmacao}
              enviando={enviando}
              erro={estado.erro}
              onMotivo={ex.setMotivo}
              onConfirmacao={ex.setConfirmacao}
              onVoltar={ex.voltarRegistros}
              onVoltarTipos={ex.voltarTipos}
              onConfirmar={confirmar}
            />
          )}
        </div>
        {aba === "pedidos" && (souAdmin ? <PedidosAdmin /> : <MeusPedidos />)}
        {aba === "trilha" && souAdmin && <TrilhaExclusao />}
      </div>
    </MolduraExcluir>
  );
}
