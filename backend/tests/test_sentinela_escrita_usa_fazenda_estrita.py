"""
Teste-sentinela: rota de ESCRITA não nasce mais com a dependência tolerante.

A sentinela irmã (test_sentinela_criacao_usa_fazenda_id_escrita.py) cobre um
caso: POST que CRIA linha nova (`session.add`) resolvendo `fazenda_id` pela
dependência tolerante. Ela não cobre o outro, que é onde os furos desta
auditoria continuam aparecendo: PUT/DELETE que ALTERAM uma linha existente
localizada por id.

Foi exatamente esse o furo do `fotos.py::excluir_foto` (PR #711): a rota
carregava a foto por `session.get(id)` e conferia a posse com
`if fazenda_id is not None and foto.fazenda_id != fazenda_id`. Com
`fazenda_id` nulo a condição não compara nada — qualquer foto era excluída
pelo id. A sentinela de criação não via isso, porque a rota não cria nada.

POR QUE UMA BASELINE, E NÃO UMA PROIBIÇÃO
Hoje 191 rotas de escrita usam `get_fazenda_atual_id`. Trocar todas de uma
vez não é possível com segurança: são 191 diffs em módulos de sessões
diferentes, e cada troca muda o código de resposta em ambiente sem
multi-fazenda provisionado. Proibir tudo agora só deixaria a suíte vermelha
e alguém acabaria removendo o teste.

Então esta sentinela é uma CATRACA: congela a lista atual e falha quando
aparece uma rota NOVA fora dela. O que já existe é dívida conhecida — a
`main` não fica pior do que está hoje, e cada correção futura pode (e deve)
tirar uma linha da lista.

A trava de porta (`auth.py::exigir_fazenda_selecionada`) recusa o token sem
"fid" antes da rota, então nada disto está aberto em produção. A dívida é de
defesa em profundidade: a guarda da rota não pode depender só da porta.

COMO REDUZIR A LISTA (é para reduzir, não para crescer): troque
`Depends(get_fazenda_atual_id)` por `Depends(get_fazenda_id_escrita)`, mova o
recorte por fazenda para DENTRO da consulta que carrega o registro (padrão
`agenda.py::_buscar_da_fazenda`), responda 404 e nunca 403, e apague a
entrada correspondente daqui.
"""
from __future__ import annotations

import ast
from pathlib import Path

_DIR_ROUTERS = Path(__file__).resolve().parent.parent / "fazenda" / "api" / "routers"
_VERBOS_DE_ESCRITA = {"post", "put", "patch", "delete"}

# Dívida congelada em 06/09/2026. NÃO ACRESCENTE LINHAS AQUI para fazer um
# teste passar: se a sua rota nova apareceu, ela precisa de
# `get_fazenda_id_escrita`, não de uma isenção.
#
# A segunda trava já se pagou antes mesmo deste arquivo entrar na main: a
# lista foi gerada quando `fotos.py::enviar_foto` e `::excluir_foto` ainda
# usavam a dependência tolerante, e o PR #711 corrigiu as duas enquanto este
# PR esperava CI. Ao trazer a main, `test_a_divida_congelada_nao_tem_entrada_morta`
# apontou as duas entradas mortas em vez de deixá-las apodrecendo aqui.
_DIVIDA_CONHECIDA: set[tuple[str, str]] = {
    ("agenda.py", "desmarcar_realizado"),
    ("alimentacao.py", "atualizar_alimento"),
    ("alimentacao.py", "atualizar_categoria_alimento"),
    ("alimentacao.py", "atualizar_categoria_estoque"),
    ("alimentacao.py", "atualizar_estoque_preferido"),
    ("alimentacao.py", "excluir_alimento"),
    ("alimentacao.py", "excluir_categoria_alimento"),
    ("alimentacao.py", "excluir_consumo"),
    ("alimentacao.py", "excluir_produto_tabela_nutricional"),
    ("alimentacao.py", "renomear_produto_tabela_nutricional"),
    ("aprovacoes.py", "desfazer"),
    ("aprovacoes.py", "editar"),
    ("aprovacoes.py", "rejeitar"),
    ("assistente.py", "atualizar_ensinamento"),
    ("assistente.py", "criar_ensinamento"),
    ("assistente.py", "excluir_ensinamento"),
    ("assistente.py", "perguntar"),
    ("cadastro/animais.py", "atualizar_ficha_animal"),
    ("cadastro/animais.py", "atualizar_grau_sangue"),
    ("cadastro/animais.py", "atualizar_raca"),
    ("cadastro/animais.py", "renumerar_animal"),
    ("cadastro/estoque.py", "atualizar_fornecedor"),
    ("cadastro/estoque.py", "atualizar_meta_estoque"),
    ("cadastro/genetica.py", "atualizar_estoque_semen"),
    ("cadastro/genetica.py", "excluir_estoque_semen"),
    ("cadastro/lida.py", "atualizar_lida"),
    ("cadastro/lida.py", "excluir_lida"),
    ("cadastro/pessoas.py", "atualizar_pessoa"),
    ("cadastro/pessoas.py", "atualizar_tipo_pessoa"),
    ("cadastro/pessoas.py", "excluir_anexo_pessoa"),
    ("cadastro/pessoas.py", "excluir_pessoa"),
    ("cadastro/protocolos_customizados.py", "atualizar_protocolo_customizado"),
    ("cadastro/protocolos_customizados.py", "excluir_protocolo_customizado"),
    ("cadastro/protocolos_sanitarios.py", "atualizar_protocolo_iatf_cadastrado"),
    ("cadastro/protocolos_sanitarios.py", "atualizar_protocolo_inducao"),
    ("cadastro/protocolos_sanitarios.py", "atualizar_protocolo_sanitario"),
    ("cadastro/protocolos_sanitarios.py", "excluir_protocolo_iatf_cadastrado"),
    ("cadastro/protocolos_sanitarios.py", "excluir_protocolo_inducao"),
    ("cadastro/protocolos_sanitarios.py", "excluir_protocolo_sanitario"),
    ("cadastro/rh_contratos.py", "atualizar_parcela_contrato"),
    ("cadastro/rh_contratos.py", "atualizar_parcela_empreitada"),
    ("cadastro/rh_contratos.py", "editar_diaria"),
    ("cadastro/rh_contratos.py", "encerrar_contrato"),
    ("cadastro/rh_contratos.py", "encerrar_diaria"),
    ("cadastro/rh_contratos.py", "excluir_parcela_contrato"),
    ("cadastro/rh_contratos.py", "excluir_parcela_empreitada"),
    ("cadastro/rh_contratos.py", "excluir_vale_avulso"),
    ("cadastro/rh_contratos.py", "reabrir_diaria"),
    ("cadastro/rh_contratos.py", "redistribuir_parcelas_contrato"),
    ("cadastro/rh_contratos.py", "redistribuir_parcelas_empreitada"),
    ("cadastro/rh_contratos.py", "responder_auditoria_diaria"),
    ("cadastro/rh_folha.py", "atualizar_decimo_terceiro"),
    ("cadastro/rh_folha.py", "atualizar_ferias"),
    ("cadastro/rh_folha.py", "atualizar_folha_pagamento"),
    ("cadastro/rh_folha.py", "atualizar_guia_folha_encargo"),
    ("cadastro/rh_folha.py", "atualizar_rescisao_simulacao"),
    ("cadastro/rh_folha.py", "editar_parcela_vale"),
    ("cadastro/rh_folha.py", "estornar_pagamento_folha"),
    ("cadastro/rh_folha.py", "excluir_comprovante_vale"),
    ("cadastro/rh_folha.py", "excluir_decimo_terceiro"),
    ("cadastro/rh_folha.py", "excluir_ferias"),
    ("cadastro/rh_folha.py", "excluir_folha_pagamento"),
    ("cadastro/rh_folha.py", "excluir_guia_folha_encargo"),
    ("cadastro/rh_folha.py", "excluir_parcela_vale"),
    ("cadastro/rh_folha.py", "excluir_rescisao_simulacao"),
    ("cadastro/rh_folha.py", "excluir_vale"),
    ("cadastro/rh_folha.py", "simular_rescisao"),
    ("cadastro/rh_vale_item.py", "desmarcar_item_como_vale"),
    ("cadastro/sanitario.py", "atualizar_agendamento_pesagem"),
    ("cadastro/sanitario.py", "atualizar_evento_sanitario"),
    ("cadastro/sanitario.py", "atualizar_exame"),
    ("cadastro/sanitario.py", "excluir_agendamento_pesagem"),
    ("cadastro/sanitario.py", "excluir_exame"),
    ("cadastro/servicos.py", "atualizar_metodo_servico"),
    ("cartao_credito.py", "atualizar_cartao"),
    ("cartao_credito.py", "criar_lancamento_cartao"),
    ("cartao_credito.py", "fechar_fatura_cartao"),
    ("central_protocolos.py", "cancelar"),
    ("central_protocolos.py", "desfazer_aplicacao"),
    ("central_protocolos.py", "editar_lancamento"),
    ("central_protocolos.py", "encerrar"),
    ("central_protocolos.py", "reabrir"),
    ("central_protocolos.py", "renomear"),
    ("chamados.py", "abrir_chamado"),
    ("chamados.py", "atualizar_status_chamado"),
    ("documentos.py", "enviar_documento"),
    ("documentos.py", "excluir_documento"),
    ("estoque.py", "atualizar_item_estoque"),
    ("estoque.py", "editar_movimento_estoque"),
    ("estoque.py", "excluir_item_estoque"),
    ("estoque.py", "mesclar_itens_estoque"),
    ("estoque.py", "restaurar_padrao_cowdata"),
    ("exclusoes.py", "aprovar_pendente"),
    ("exclusoes.py", "confirmar"),
    ("exclusoes.py", "impacto"),
    ("exclusoes.py", "rejeitar_pendente"),
    ("fazendas.py", "desvincular_usuario"),
    ("fazendas.py", "editar_vinculo_usuario"),
    ("fazendas.py", "vincular_usuario"),
    ("financeiro.py", "atualizar_centro_custo"),
    ("financeiro.py", "atualizar_conta_corrente"),
    ("financeiro.py", "atualizar_conta_gerencial"),
    ("financeiro.py", "atualizar_lancamento_recorrente"),
    ("financeiro.py", "atualizar_linha_dre"),
    ("financeiro.py", "atualizar_patrimonio"),
    ("financeiro.py", "atualizar_plano_manutencao"),
    ("financeiro.py", "atualizar_valor_mercado"),
    ("financeiro.py", "baixa_lote"),
    ("financeiro.py", "baixa_lote_detalhada"),
    ("financeiro.py", "baixar_patrimonio"),
    ("financeiro.py", "corrigir_depreciavel_patrimonio"),
    ("financeiro.py", "editar_lancamento"),
    ("financeiro.py", "enviar_recibo"),
    ("financeiro.py", "estornar_baixa_patrimonio"),
    ("financeiro.py", "estornar_lancamento"),
    ("financeiro.py", "excluir_anexo"),
    ("financeiro.py", "gerar_codigos_patrimonio"),
    ("financeiro.py", "importar_xml"),
    ("financeiro.py", "ler_documento_anexado"),
    ("financeiro.py", "pagar_lancamento"),
    ("financeiro.py", "vincular_evento_sanitario_reprodutivo"),
    ("financeiro.py", "vincular_lancamento_patrimonio"),
    ("financeiro.py", "vincular_produto_item"),
    ("formulacao_dietas.py", "aplicar_simulacao"),
    ("formulacao_dietas.py", "duplicar_simulacao"),
    ("formulacao_dietas.py", "excluir_simulacao"),
    ("formulacao_dietas.py", "salvar_simulacao"),
    ("indicadores.py", "relatorio_personalizado"),
    ("lotes.py", "atualizar_lote"),
    ("lotes.py", "preview_criterios"),
    ("manual_fazenda.py", "anexar_contrato_manejo"),
    ("manual_fazenda.py", "atualizar_parametros_manual"),
    ("manual_fazenda.py", "atualizar_sugestao_manual"),
    ("manual_fazenda.py", "excluir_sugestao_manual"),
    ("movimentacoes.py", "atualizar_motivo"),
    ("movimentacoes.py", "salvar_parametro_agendamento"),
    ("parametros.py", "atualizar_parametro"),
    ("pedidos.py", "atualizar_rastreio_pedido"),
    ("pedidos.py", "atualizar_status_pedido"),
    ("pedidos.py", "excluir_anexo_pedido"),
    ("pedidos.py", "excluir_pedido"),
    ("planejamento.py", "atualizar_cenario"),
    ("planejamento.py", "atualizar_item_cenario"),
    ("planejamento.py", "atualizar_item_orcamento"),
    ("planejamento.py", "excluir_cenario"),
    ("planejamento.py", "excluir_item_cenario"),
    ("planejamento.py", "excluir_item_orcamento"),
    ("portal.py", "delegar_tarefa"),
    ("portal.py", "enviar_email_portal"),
    ("portal.py", "enviar_mensagem"),
    ("portal.py", "solicitar_exportacao"),
    ("producao.py", "atualizar_entrega_leite"),
    ("producao.py", "atualizar_faixa_bonificacao_qualidade"),
    ("producao.py", "atualizar_pesagem"),
    ("producao.py", "criar_faixa_bonificacao_qualidade"),
    ("producao.py", "excluir_faixa_bonificacao_qualidade"),
    ("producao.py", "importar_pesagem_corporal_planilha"),
    ("producao.py", "importar_qualidade_leite_planilha"),
    ("producao.py", "sugestao_lote_evento"),
    ("protocolos_customizados.py", "cancelar_lancamento"),
    ("recria.py", "atualizar_categoria"),
    ("recria.py", "excluir_benchmark"),
    ("recria.py", "excluir_categoria"),
    ("recria.py", "excluir_cocho"),
    ("recria.py", "excluir_fase"),
    ("recria.py", "excluir_janela"),
    ("recria.py", "excluir_ocorrencia"),
    ("recria.py", "excluir_peso_alvo"),
    ("reproducao.py", "abrir_lactacao"),
    ("reproducao.py", "agenda_reprodutiva_card"),
    ("reproducao.py", "atualizar_parto"),
    ("reproducao.py", "atualizar_secagem"),
    ("reproducao.py", "atualizar_servico"),
    ("reproducao.py", "enviar_ultimo_diagnostico"),
    ("reproducao.py", "excluir_inducao_cio"),
    ("reproducao.py", "registrar_diagnostico"),
    ("reproducao.py", "registrar_perda_prenhez"),
    ("reproducao.py", "registrar_reconfirmacao"),
    ("reproducao.py", "remover_animal_iatf"),
    ("safra.py", "atualizar_safra"),
    ("sanidade.py", "atualizar_calendario"),
    ("sanidade.py", "editar_aplicacao"),
    ("sanidade.py", "editar_resultado_exame"),
    ("sanidade.py", "excluir_aplicacao"),
    ("sanidade.py", "excluir_calendario"),
    ("sanidade.py", "marcar_cura_aplicacao"),
    ("sanidade.py", "marcar_cura_mastite"),
    ("sanidade.py", "marcar_cura_protocolo"),}


def _rotas_de_escrita_com_dependencia_tolerante() -> set[tuple[str, str]]:
    """Varre os routers por AST — sem importar nada, para não precisar montar
    a aplicação nem um banco.

    `ast.AsyncFunctionDef` NÃO é subclasse de `ast.FunctionDef`: testar só
    por `FunctionDef` deixa toda rota `async def` invisível, que foi
    justamente o defeito encontrado na sentinela irmã (39 rotas POST fora do
    alcance dela sem ninguém perceber). Por isso as duas entram aqui.
    """
    achadas: set[tuple[str, str]] = set()
    for arquivo in sorted(_DIR_ROUTERS.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            verbos = {
                (d.func if isinstance(d, ast.Call) else d).attr
                for d in no.decorator_list
                if isinstance((d.func if isinstance(d, ast.Call) else d), ast.Attribute)
            }
            if not (verbos & _VERBOS_DE_ESCRITA):
                continue
            defaults = list(no.args.defaults) + [d for d in no.args.kw_defaults if d is not None]
            for default in defaults:
                if (
                    isinstance(default, ast.Call)
                    and getattr(default.func, "id", "") == "Depends"
                    and default.args
                    and isinstance(default.args[0], ast.Name)
                    and default.args[0].id == "get_fazenda_atual_id"
                ):
                    achadas.add((str(arquivo.relative_to(_DIR_ROUTERS)), no.name))
                    break
    return achadas


def test_nenhuma_rota_de_escrita_nova_com_dependencia_tolerante():
    """A catraca. Rota de escrita nova tem que nascer com o resolvedor
    estrito."""
    novas = _rotas_de_escrita_com_dependencia_tolerante() - _DIVIDA_CONHECIDA
    assert not novas, (
        "Rota(s) de ESCRITA nova(s) usando `Depends(get_fazenda_atual_id)`:\n"
        + "\n".join(f"  - {arq}::{fn}" for arq, fn in sorted(novas))
        + "\n\nEm escrita, `get_fazenda_atual_id` pode devolver None (token sem \"fid\") "
          "e o isolamento por fazenda se desliga: a linha nasce órfã, ou a checagem "
          "de posse `if fazenda_id is not None and ...` deixa de comparar qualquer "
          "coisa. Use `Depends(get_fazenda_id_escrita)` e faça o recorte por fazenda "
          "DENTRO da consulta que carrega o registro (ver agenda.py::_buscar_da_fazenda). "
          "Responda 404, nunca 403 — 403 confirma ao atacante que o id existe."
    )


def test_a_divida_congelada_nao_tem_entrada_morta():
    """Toda entrada da lista tem que corresponder a uma rota que existe.

    Sem isto, a lista vira lixo: uma rota renomeada ou removida deixa uma
    isenção órfã, e um dia alguém cria uma rota com aquele nome e ela nasce
    isenta sem que ninguém tenha decidido isso.
    """
    mortas = _DIVIDA_CONHECIDA - _rotas_de_escrita_com_dependencia_tolerante()
    assert not mortas, (
        "Entradas da dívida congelada que não correspondem mais a rota nenhuma "
        "(a rota foi corrigida, renomeada ou removida — apague estas linhas):\n"
        + "\n".join(f"  - {arq}::{fn}" for arq, fn in sorted(mortas))
    )
