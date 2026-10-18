"use client";
// Dados reais da seleção de fêmeas das telas de Lançamentos › Reprodutivo: o veredito de aptidão do SERVIDOR para a data
// escolhida (GET /reproducao/aptidao-servico) + o estado reprodutivo ao vivo, juntos em linhas prontas para a tabela
// (ver lib/aptidaoServico.ts, onde mora a regra). Sem a resposta do servidor (carregando / falhou) a tabela cai no que a
// página já antecipava (`motivosInaptidao`), nunca fica vazia.
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchAptidaoServico, type AptidaoServicoApi } from "@/lib/api";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import { montarLinhas, type AnimalBase, type EstadoBase, type LinhaFemea } from "@/lib/aptidaoServico";

/** Veredito de aptidão do servidor para `data` (padrão hoje). Reconsulta quando a data muda (com um respiro) e sob demanda. */
export function useAptidaoServico(data: string, ativo = true) {
  const [api, setApi] = useState<AptidaoServicoApi | null>(null);
  const [falhou, setFalhou] = useState(false);
  const [rodada, setRodada] = useState(0);
  useEffect(() => {
    if (!ativo) return;
    let vivo = true;
    const t = setTimeout(() => {
      fetchAptidaoServico(data || undefined)
        .then((r) => { if (vivo) { setApi(r); setFalhou(false); } })
        .catch(() => { if (vivo) setFalhou(true); });
    }, 250);
    return () => { vivo = false; clearTimeout(t); };
  }, [data, rodada, ativo]);
  const recarregar = useCallback(() => setRodada((r) => r + 1), []);
  return { api, falhou, recarregar };
}

export function useLinhasFemeas(opts: {
  animais: readonly AnimalBase[];
  api: AptidaoServicoApi | null;
  motivosInaptidao?: ReadonlyMap<string, string>;
  bloquearEmProtocolo?: boolean;
  protocoloDestinoId?: number | null;
  dataReferencia?: string;
  preMarcadas?: ReadonlySet<string>;
  usarServidor?: boolean;
}): LinhaFemea[] {
  const { porNumero, rotuloDe } = useEstadosReprodutivos();
  const { animais, api, motivosInaptidao, bloquearEmProtocolo, protocoloDestinoId, dataReferencia, preMarcadas, usarServidor } = opts;
  return useMemo(
    () => montarLinhas({
      animais, estados: porNumero as ReadonlyMap<string, EstadoBase>, rotuloEstado: rotuloDe, api, motivosLocais: motivosInaptidao,
      bloquearEmProtocolo, protocoloDestinoId, dataReferencia, preMarcadas, usarServidor,
    }),
    [animais, porNumero, rotuloDe, api, motivosInaptidao, bloquearEmProtocolo, protocoloDestinoId, dataReferencia, preMarcadas, usarServidor],
  );
}
