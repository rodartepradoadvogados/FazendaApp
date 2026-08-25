"use client";
// Seção RESUMO — a "capa" da ficha: situação reprodutiva/produtiva atual +
// o quadro de 8 métricas por parto (`ficha.resumo_partos`), hoje só na ficha
// de mesa (FichaAnimal.tsx › QuadroResumoPartos). Zero cálculo novo — os
// campos já vêm prontos do backend; só reorganizados no padrão MobCard/
// Grade/ParDado que a ficha mobile já usa para Compra/Venda/Baixa.
import { formatDate } from "@/lib/api";
import { MobCard } from "@/components/mobile/ui";
import { Grade, ParDado, mostrarValor, criarAlternador, tituloCartao, type Ficha } from "./comumFicha";

function fmtKg(v: number | null): string {
  return v == null ? "—" : `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} kg`;
}

export function SecaoResumo({ ficha }: { ficha: Ficha }) {
  const a = ficha.animal;
  const proximoAlt = criarAlternador();
  // Mais recente primeiro (o quadro de mesa mostra do 1º parto em diante;
  // aqui invertido — é a lactação atual que interessa ver primeiro ao abrir
  // a ficha no curral).
  const partosOrdenados = [...(ficha.resumo_partos || [])].reverse();
  const maisRecente = partosOrdenados[0] || null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
      <MobCard alt={proximoAlt()}>
        <Grade cols={3}>
          <ParDado label="Situação reprodutiva" valor={mostrarValor(a.sit_rep)} />
          {/* "Situação produtiva" reaproveita a categoria AO VIVO (ex.: "Vaca em
              lactação"/"Vaca seca" — calculada em _categoria_ao_vivo no backend),
              não é um campo novo: é o mesmo texto que "Categoria" já mostra em
              Dados Gerais, só com outro rótulo aqui — não existe hoje um campo
              "situação produtiva" dedicado no payload da ficha. */}
          <ParDado label="Situação produtiva" valor={mostrarValor(a.categoria_completa || a.categoria_abrev)} />
          <ParDado label="DEL" valor={a.del_dias != null ? `${a.del_dias} dias` : "—"} />
          <ParDado label="Ordem de parto" valor={maisRecente ? `${maisRecente.ordem_parto}ª cria` : "—"} />
          <ParDado label="Dias de gestação" valor={ficha.precisao_parto?.dias_gestacao ?? "—"} />
          <ParDado label="Previsão de parto" valor={ficha.previsao_parto ? formatDate(ficha.previsao_parto) : "—"} />
        </Grade>
      </MobCard>

      {ficha.previsao_secagem && (
        <MobCard alt={proximoAlt()}>
          <p style={tituloCartao}>Próxima ação prevista</p>
          <div style={{ fontSize: "0.9rem", fontWeight: 700 }}>Secagem prevista — {formatDate(ficha.previsao_secagem)}</div>
        </MobCard>
      )}

      {!!partosOrdenados.length && (
        <>
          <div className="mob-secao" style={{ margin: "0.2rem 0 0" }}>Resumo por parto</div>
          {partosOrdenados.map((l) => (
            <MobCard key={l.ordem_parto} alt={proximoAlt()}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "0.6rem" }}>
                <span style={{ fontWeight: 800, fontSize: "0.9rem" }}>{l.ordem_parto}º cria — {formatDate(l.data_parto)}</span>
                <span style={{ fontSize: "0.72rem", fontWeight: 700, color: l.lactacao_encerrada ? "var(--mob-muted)" : "var(--mob-dourado-2)" }}>
                  {l.lactacao_encerrada ? "Encerrada" : "Em andamento"}
                </span>
              </div>
              <Grade>
                <ParDado label="Dias em lactação" valor={l.dias_em_lactacao} />
                <ParDado label="Produção total" valor={fmtKg(l.producao_total_kg)} />
                <ParDado label="Média/dia" valor={fmtKg(l.producao_media_dia_kg)} />
                <ParDado label="305 dias" valor={<>{fmtKg(l.producao_305_dias_kg)}{l.producao_305_dias_kg != null && l.producao_305_dias_estimada && <span style={{ fontSize: "0.68rem", color: "var(--mob-muted)", fontWeight: 500 }}> (estim.)</span>}</>} />
                <ParDado label="Tentativas p/ emprenhar" valor={l.tentativas_emprenhar ?? "—"} />
                <ParDado label="DEL na concepção" valor={l.del_concepcao ?? "—"} />
              </Grade>
            </MobCard>
          ))}
        </>
      )}

      {!partosOrdenados.length && (
        <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Este animal ainda não tem parto registrado.</p>
      )}
    </div>
  );
}
