"""
Motor do Sanitário Preventivo v2 (caixas de vacina/exame/vermífugo).

Funções públicas:
  - motor.avaliar(cx, animal, ref=None) -> list[Situacao]   (PURA, a função única)
  - motor.situacao_atual(cx, animal, ref=None) -> Situacao  (PURA)
  - motor.ok_na_data / motor.motivo_inelegivel              (PURAS)
  - motor.simular_pura(caixas, animais, data, ...) / motor.simular(session, ...)  (não gravam)
  - motor.recalcular(session, fazenda_id, animal_ids=None, caixa_ids=None, ...)  (upsert, sem commit)
  - ganchos.animal_mudou(session, fazenda_id, animal_ids=|numeros=, evento=)
  - job.executar_diaria / job.fechar_dias_vencidos / job.tick
  - definicao.criar_caixa / nova_versao / ativar_do_catalogo / criar_padrao_fabrica
  - consulta.resumo_30d / membros / situacao_do_animal       (só leitura)
"""
