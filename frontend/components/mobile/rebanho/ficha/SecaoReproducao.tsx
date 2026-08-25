"use client";
// Seção REPRODUÇÃO — situação atual (topo, fixa) + acordeões de histórico.
// "Diagnósticos" não vira acordeão próprio: o diagnóstico de cada IA já vem
// embutido nas linhas de Serviços/IA (campo `diagnostico`), como sempre foi
// no mobile e na mesa — não existe uma lista separada no payload da ficha.
import { formatDate } from "@/lib/api";
import { MobCard } from "@/components/mobile/ui";
import { Grade, ParDado, Secao, secaoPorChave, type Ficha } from "./comumFicha";

export function SecaoReproducao({ ficha }: { ficha: Ficha }) {
  const a = ficha.animal;
  // Contador corrido de alternância de cor — reiniciado nesta seção (era um
  // contador único pela ficha inteira antes do redesenho em cards; agora
  // cada SecaoX cuida da própria sequência, senão a alternância perde o
  // sentido visual ao trocar de seção).
  let altContador = 0;
  const proximoAlt = (): 0 | 1 => (altContador++ % 2) as 0 | 1;

  function acordeao(chave: string) {
    const s = secaoPorChave(chave);
    const linhas = (ficha[chave] as Record<string, unknown>[]) || [];
    const altInicio = altContador;
    altContador += linhas.length;
    return <Secao key={chave} chave={chave} titulo={s.titulo} campos={s.campos} linhas={linhas} altInicio={altInicio} />;
  }

  const semNadaLancado = ["servicos", "protocolos_iatf", "partos", "inducao_lactacao", "protocolos_customizados"]
    .every((chave) => !((ficha[chave] as unknown[]) || []).length);

  return (
    <div>
      <MobCard alt={proximoAlt()} style={{ marginBottom: "0.85rem", borderLeft: "4px solid var(--cat-reproducao)" }}>
        <Grade>
          <ParDado label="Situação reprodutiva" valor={a.sit_rep != null && a.sit_rep !== "" ? String(a.sit_rep) : "—"} />
          <ParDado label="Ordem de parto" valor={(ficha.resumo_partos || []).length ? `${ficha.resumo_partos[ficha.resumo_partos.length - 1].ordem_parto}ª cria` : "—"} />
          <ParDado label="Dias de gestação" valor={ficha.precisao_parto?.dias_gestacao ?? "—"} />
          <ParDado label="Previsão de parto" valor={ficha.previsao_parto ? formatDate(ficha.previsao_parto) : "—"} />
        </Grade>
      </MobCard>

      {acordeao("servicos")}
      {acordeao("protocolos_iatf")}
      {acordeao("partos")}
      {acordeao("inducao_lactacao")}
      {acordeao("protocolos_customizados")}

      {semNadaLancado && (
        <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum lançamento reprodutivo registrado para este animal.</p>
      )}
    </div>
  );
}
