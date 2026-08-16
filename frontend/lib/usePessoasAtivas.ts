"use client";
// Pessoas ativas (Pessoa.ativo !== false) para os seletores de "Responsável"
// em lançamentos — substitui a antiga lista estática RESPONSAVEIS (lib/constants.ts),
// que não refletia funcionários inativados em Cadastro de Pessoas. Mesmo
// padrão já usado em FormInducaoLactacao/PainelLancarBst/FormLida/etc.:
// busca fetchPessoas() e filtra + ordena por nome no cliente.
import { useEffect, useMemo, useState } from "react";
import { fetchPessoas } from "@/lib/api";

export type PessoaAtiva = {
  id: number;
  nome: string;
  tipos?: string[];
  ativo?: boolean;
  [key: string]: unknown;
};

export function usePessoasAtivas() {
  const [pessoas, setPessoas] = useState<PessoaAtiva[]>([]);

  useEffect(() => {
    fetchPessoas().then(setPessoas).catch(() => setPessoas([]));
  }, []);

  const pessoasAtivas = useMemo(
    () => pessoas.filter((p) => p.ativo !== false).sort((a, b) => (a.nome || "").localeCompare(b.nome || "")),
    [pessoas]
  );
  const nomes = useMemo(() => pessoasAtivas.map((p) => p.nome), [pessoasAtivas]);

  return { pessoas: pessoasAtivas, nomes };
}
