// Baixa de um dia de protocolo na Central de Protocolos — regras puras,
// compartilhadas pelo site (app/protocolos/page.tsx › DetalheProtocolo) e pelo
// app (components/mobile/menu/Protocolos.tsx › DetalheProtocoloApp). Até
// 10/2026 o app mandava só {dia, animais, data_realizacao}: não mostrava o que
// aplicar no dia, não deixava escolher o frasco/lote e descartava os avisos de
// estoque. Ficar num lugar só garante que as duas telas montem o MESMO
// `medicamentos` para POST /central-protocolos/{origem}/{id}/baixa.
//
// Só `import type` aqui: o arquivo roda direto no `node --test` (sem o alias @/).
import type { HormonioProtocolo, MedicamentoIatf, DetalheCentralProtocolo } from "@/lib/api";

/** Escolha de frasco/lote por hormônio do dia: índice do hormônio → índice
 *  da opção em `h.opcoes` (não o estoque_id: com "incluir mesmo sem estoque"
 *  ligado, várias opções vêm com estoque_id null) ou id do lote de compra.
 *  "" = não escolhido. */
export type EscolhaPorHormonio = Record<number, number | "">;

/** Origens cujo detalhe traz `hormonios` por dia (o "qual medicamento/frasco?").
 *  Customizado e lida não têm medicamento: a baixa só marca a etapa. */
export function origemTemMedicamento(origem: string): boolean {
  return origem === "iatf" || origem === "inducao" || origem === "sanitario";
}

/** Hormônios/medicamentos cadastrados para o dia em baixa — vazio para as
 *  origens sem medicamento e para dia sem nada cadastrado (D11/inseminação). */
export function hormoniosDoDia(origem: string, det: Pick<DetalheCentralProtocolo, "dias"> | null | undefined, dia: number | null): HormonioProtocolo[] {
  if (!origemTemMedicamento(origem) || dia == null || !det) return [];
  return det.dias.find((d) => d.dia === dia)?.hormonios || [];
}

/** Índice da opção de frasco em uso: a escolhida, ou a única que existe
 *  (uma só opção já vem selecionada — mesmo comportamento da Agenda). */
export function opcaoEfetiva(h: HormonioProtocolo, escolha: number | "" | undefined): number | "" {
  return escolha ?? (h.opcoes?.length === 1 ? 0 : "");
}

/** Monta `medicamentos` do POST de baixa. Sem hormônio no dia devolve
 *  `undefined` (não manda o campo) — o backend cai nos medicamentos
 *  cadastrados no lançamento e abate o estoque por nome, como antes. */
export function montarMedicamentosBaixa(
  origem: string, hormonios: HormonioProtocolo[], frasco: EscolhaPorHormonio = {}, lote: EscolhaPorHormonio = {},
): MedicamentoIatf[] | undefined {
  if (!origemTemMedicamento(origem) || !hormonios.length) return undefined;
  return hormonios.map((h, idx) => {
    const optIdx = opcaoEfetiva(h, frasco[idx]);
    const opcao = optIdx === "" ? undefined : h.opcoes?.[optIdx];
    const loteId = lote[idx];
    return {
      produto: opcao?.nome ?? h.produto, estoque_id: opcao?.estoque_id ?? undefined,
      lote_id: loteId != null && loteId !== "" ? loteId : undefined,
      dose: h.dose, unidade: h.unidade, via: h.via,
    };
  }).filter((m) => m.produto);
}

/** Dia de inseminação do IATF (o último): não se dá baixa por aqui — isso só
 *  marcaria a etapa sem registrar o Servico (touro/sêmen). O backend recusa
 *  (400); as duas telas nem oferecem o dia. */
export function diaInseminacaoIatf(origem: string, dias: { dia: number }[]): number | null {
  return origem === "iatf" && dias.length > 1 ? Math.max(...dias.map((d) => d.dia)) : null;
}

/** Mensagem depois da baixa enviada: os avisos de estoque, quando houver. */
export function mensagemBaixa(resposta: { avisos?: string[] } | null | undefined): string {
  return resposta?.avisos?.length ? resposta.avisos.join(" ") : "Baixa registrada.";
}
