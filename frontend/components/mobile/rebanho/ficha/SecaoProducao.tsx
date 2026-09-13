"use client";
// Seção PRODUÇÃO — Curva de lactação (já existia no mobile, só mudou de
// arquivo) + Trio do Equivalente Maduro (hoje só na ficha de mesa) + os
// acordeões de histórico de produção.
import { useEffect, useState } from "react";
import { formatDate, fetchEquivalenteMaduroDoAnimal, type TrioEquivalenteMaduro as Trio } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";
import { MobCard } from "@/components/mobile/ui";
// Mesmo componente SVG da curva de lactação de mesa — só o CSS muda (ver
// ESTILO_TOKENS_MESA abaixo).
import { CurvaLactacao, type FaixaReferencia, type PontoWood } from "@/components/CurvaLactacao";
import { TrioEquivalenteMaduroView, NotaExplicativaEM } from "@/components/TrioEquivalenteMaduro";
import { Secao, secaoPorChave, ESTILO_TOKENS_MESA, tituloCartao, type Ficha } from "./comumFicha";

export function SecaoProducao({ ficha, numero }: { ficha: Ficha; numero: string }) {
  const a = ficha.animal;
  let altContador = 0;
  const proximoAlt = (): 0 | 1 => (altContador++ % 2) as 0 | 1;

  // Mesmos pontos (DEL × kg) que a versão de mesa desenha na curva.
  const controlesLeiteiros = (ficha.controles_leiteiros as Record<string, unknown>[] | undefined) || [];
  const pontosLactacao = controlesLeiteiros
    .map((c) => ({
      del: Number(c.del_no_controle),
      kg: Number(c.producao_kg),
      data: c.data_controle ? formatDate(String(c.data_controle)) : null,
    }))
    .filter((p) => Number.isFinite(p.del) && Number.isFinite(p.kg));
  const referenciaLactacao = ficha.curva_referencia_rebanho as unknown as FaixaReferencia[] | undefined;
  const referenciaGrupoLactacao = ficha.curva_referencia_grupo_ordem_parto as unknown as FaixaReferencia[] | null | undefined;
  const curvaWoodLactacao = ficha.curva_wood as unknown as PontoWood[] | null | undefined;
  const jaPariu = ((ficha.partos as unknown[] | undefined) || []).length > 0;

  // Equivalente Maduro: busca SÓ quando esta seção é montada (o usuário abriu
  // "Produção"), não em paralelo no carregamento inicial da ficha inteira —
  // o app de campo trata conectividade ruim como cenário central (ver
  // frontend/lib/offline.ts). Cache com chave própria (`em_<numero>`),
  // separada de `ficha_<numero>`. Erro/404 (animal sem lactação ainda) fica
  // silencioso — mesmo comportamento da versão de mesa (FichaAnimal.tsx).
  const [trioEM, setTrioEM] = useState<Trio | null>(null);
  const [carregandoEM, setCarregandoEM] = useState(true);
  useEffect(() => {
    let vivo = true;
    setCarregandoEM(true);
    fetchComCache<Trio>(`em_${numero}`, () => fetchEquivalenteMaduroDoAnimal(numero))
      .then(({ dados }) => { if (vivo) setTrioEM(dados); })
      .catch(() => { if (vivo) setTrioEM(null); })
      .finally(() => { if (vivo) setCarregandoEM(false); });
    return () => { vivo = false; };
  }, [numero]);

  function acordeao(chave: string) {
    const s = secaoPorChave(chave);
    const linhas = (ficha[chave] as Record<string, unknown>[]) || [];
    const altInicio = altContador;
    altContador += linhas.length;
    return <Secao key={chave} chave={chave} titulo={s.titulo} campos={s.campos} linhas={linhas} altInicio={altInicio} />;
  }

  return (
    <div>
      {carregandoEM && (
        <p style={{ color: "var(--mob-muted)", fontSize: "0.82rem", marginBottom: "0.85rem" }}>Carregando Equivalente Maduro…</p>
      )}
      {!carregandoEM && trioEM && (
        <MobCard alt={proximoAlt()} style={{ marginBottom: "0.85rem" }}>
          <p style={tituloCartao}>Equivalente maduro</p>
          <div style={ESTILO_TOKENS_MESA}>
            <TrioEquivalenteMaduroView trio={trioEM} />
            <NotaExplicativaEM />
          </div>
        </MobCard>
      )}

      {a.sexo === "F" && (jaPariu || pontosLactacao.length > 0) && (
        <MobCard alt={proximoAlt()} style={{ marginBottom: "0.85rem" }}>
          <p style={tituloCartao}>Curva de lactação</p>
          <div style={ESTILO_TOKENS_MESA}>
            <CurvaLactacao pontos={pontosLactacao} referencia={referenciaLactacao}
              referenciaGrupo={referenciaGrupoLactacao || undefined} curvaWood={curvaWoodLactacao || undefined} />
          </div>
        </MobCard>
      )}

      {acordeao("controles_leiteiros")}
      {acordeao("pesagens_corporais")}
      {acordeao("qualidade_leite")}
      {acordeao("secagens")}
    </div>
  );
}
