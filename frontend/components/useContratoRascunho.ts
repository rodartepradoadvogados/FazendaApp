"use client";
// Rascunho do contrato na tela (Painel CowData > Fazendas, web e mobile):
// plano escolhido, módulos do "sob medida", regras de dependência vindas do
// servidor e o que mudaria ao salvar. A lógica pura mora em lib/planosContrato.ts.
import { useEffect, useState } from "react";
import {
  fetchDependenciasModulos, type CatalogoPlanos, type ContratoFazenda, type DependenciasModulos, type ModuloComercial, type PlanoNome,
} from "@/lib/api";
import {
  desmarcarModulo, marcados, marcarModulo, modulosRemovidos, validarSelecao, type SelecaoModulos,
} from "@/lib/planosContrato";

export function useContratoRascunho(catalogo: CatalogoPlanos | null, contrato: ContratoFazenda | null) {
  const [planoEscolhido, setPlanoEscolhidoBruto] = useState<string>("standard");
  const [modulosCustom, setModulosCustom] = useState<SelecaoModulos>({});
  const [regras, setRegras] = useState<DependenciasModulos | null>(null);
  const [regrasIndisponiveis, setRegrasIndisponiveis] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [pendenteRemocao, setPendenteRemocao] = useState<string[] | null>(null);

  useEffect(() => {
    fetchDependenciasModulos().then(setRegras).catch(() => setRegrasIndisponiveis(true));
  }, []);

  const deps = regras?.dependencias ?? {};
  const base = regras?.modulos_base ?? [];

  function escolherPlano(p: string) { setPlanoEscolhidoBruto(p); setAviso(null); }

  // Ao abrir uma fazenda: plano fechado → seleciona o plano; sob medida → só os
  // módulos ATIVOS (ct.modulos guarda também o histórico dos desativados;
  // marcá-los de novo na tela seria reativar sem querer). Rebanho NÃO é mais
  // forçado: um contrato só-financeiro não tem rebanho.
  function carregarDoContrato(ct: ContratoFazenda) {
    setAviso(null);
    if (ct.plano) { setPlanoEscolhidoBruto(ct.plano); return; }
    setPlanoEscolhidoBruto("custom");
    const mapa: SelecaoModulos = {};
    ct.modulos.filter((m) => m.ativo).forEach((m) => { mapa[m.modulo] = m.preco; });
    setModulosCustom(mapa);
  }

  // Trocar de um plano fechado para "Sob medida" herda os módulos do plano que
  // estava escolhido na tela (preço do contrato quando já existia).
  function selecionarSobMedida() {
    const semente: SelecaoModulos = {};
    const precoAtual = new Map((contrato?.modulos || []).filter((m) => m.ativo).map((m) => [m.modulo as string, m.preco]));
    const doPlano = planoEscolhido !== "custom" ? catalogo?.[planoEscolhido]?.modulos : undefined;
    if (doPlano) doPlano.forEach((m) => { semente[m] = precoAtual.get(m) ?? 0; });
    else precoAtual.forEach((preco, m) => { semente[m] = preco; });
    setModulosCustom(semente);
    setPlanoEscolhidoBruto("custom");
    setAviso(null);
  }

  function alternarModulo(modulo: string, marcar: boolean) {
    const r = marcar ? marcarModulo(modulosCustom, modulo, deps) : desmarcarModulo(modulosCustom, modulo, deps, base);
    setModulosCustom(r.proximo);
    setAviso(r.aviso);
  }

  function mudarPrecoModulo(modulo: string, preco: number) {
    setModulosCustom((s) => ({ ...s, [modulo]: preco }));
  }

  // Módulos que o rascunho entrega à fazenda (plano do catálogo ou sob medida).
  const modulosDoRascunho: string[] = planoEscolhido === "custom"
    ? marcados(modulosCustom)
    : (catalogo?.[planoEscolhido]?.modulos ?? []);

  const erroValidacao: string | null = planoEscolhido === "custom" ? validarSelecao(modulosCustom, deps, base) : null;

  // Só pede confirmação ao tirar módulo de contrato ATIVO (em contrato ainda
  // aguardando aprovação ninguém usa o módulo, não há o que "deixar de ver").
  function removidosAoSalvar(): string[] {
    if (contrato?.status !== "ativo") return [];
    const antes = (contrato.modulos || []).filter((m) => m.ativo).map((m) => m.modulo as string);
    return modulosRemovidos(antes, modulosDoRascunho);
  }

  function payload() {
    return planoEscolhido === "custom"
      ? {
        plano: null,
        modulos: marcados(modulosCustom).map((modulo) => ({ modulo: modulo as ModuloComercial, preco: modulosCustom[modulo] || 0 })),
        ciclo_pagamento: "mensal" as const,
      }
      : { plano: planoEscolhido as PlanoNome, modulos: [], ciclo_pagamento: "mensal" as const };
  }

  const consultorNoRascunho = planoEscolhido === "diamond" || (planoEscolhido === "custom" && modulosCustom.consultor != null);

  return {
    planoEscolhido, escolherPlano, modulosCustom, mudarPrecoModulo, alternarModulo, selecionarSobMedida, carregarDoContrato,
    aviso, regrasIndisponiveis, modulosDoRascunho, erroValidacao, removidosAoSalvar, payload, consultorNoRascunho,
    pendenteRemocao, setPendenteRemocao,
  };
}
