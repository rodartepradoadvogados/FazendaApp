"""Rebaixa "gestante" do texto de categoria quando a prenhez deixa de valer SEM parto.

`Animal.categoria_completa`/`categoria_abrev` são texto importado do GERAL.csv do Ideagri. Lançar protocolo,
inseminação ou diagnóstico nunca os reescreve; só parto/aborto (`lactacao.sincronizar_categoria_do_animal`) tiravam a
marca de "gestante". Decisão do dono (Jairo): também rebaixar quando o toque NEGATIVO (ou a reconfirmação negativa) do
serviço vigente chega, ou quando uma PERDA de prenhez é lançada. Esta é a única porta para isso: os endpoints de
diagnóstico/reconfirmação/perda/edição de serviço chamam `rebaixar_gestante_se_prenhez_acabou` logo antes do commit.

Conservador por desenho — só mexe no texto quando TODAS as condições valem:
  * o texto ainda tem marca de gestação ("gestante" / "ges.");
  * existe serviço no ciclo atual (posterior ao último parto/aborto) e o MAIS RECENTE deles está encerrado: exame
    efetivo NEGATIVO (`diagnostico_efetivo_do_servico`: o de data mais recente entre toque e reconfirmação) ou perda
    de prenhez registrada;
  * NENHUM serviço do ciclo segue positivo vigente (`servico_esta_positivo_vigente` + exame efetivo POSITIVO).
INDEFINIDO / serviço em aberto / sem serviço NÃO rebaixam. Não restaura o texto se o exame for depois desfeito
(Exclusões): o estado vivo (`estado_reprodutivo` em GET /animais/) é quem acompanha esse caso.
"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from fazenda.models import Animal, Parto, Servico
from fazenda.rules.estado_reprodutivo import diagnostico_efetivo_do_servico
from fazenda.rules.lactacao import categoria_sem_gestacao
from fazenda.rules.perda_prenhez import servico_esta_positivo_vigente


def _tem_marca_de_gestacao(texto: str | None) -> bool:
    return bool(texto) and categoria_sem_gestacao(texto, apos_parto=False) != texto


def prenhez_acabou_sem_parto(servicos: list, ultimo_parto) -> bool:
    """Função pura: o ciclo atual (serviços posteriores ao último parto) termina em negativo/perda e não tem
    nenhum serviço positivo vigente?"""
    ciclo = [s for s in servicos if s.data_servico and (ultimo_parto is None or s.data_servico > ultimo_parto)]
    if not ciclo:
        return False
    if any(servico_esta_positivo_vigente(s) and diagnostico_efetivo_do_servico(s) == "POSITIVO" for s in ciclo):
        return False
    ultimo = max(ciclo, key=lambda s: s.data_servico)
    return ultimo.data_perda_prenhez is not None or diagnostico_efetivo_do_servico(ultimo) == "NEGATIVO"


def rebaixar_gestante_se_prenhez_acabou(
    session: Session, *, numero_matriz: str, fazenda_id: int | None = None,
) -> bool:
    """Tira a marca de gestação do texto da categoria quando a prenhez acabou sem parto (ver docstring do módulo).
    Devolve True se alterou o animal. Não dá commit — roda na transação do chamador, que já leu/gravou o serviço
    (o autoflush da sessão enxerga as mudanças ainda não comitadas)."""
    query = select(Animal).where(Animal.numero == numero_matriz)
    if fazenda_id is not None:
        query = query.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query).first()
    if animal is None or not (
        _tem_marca_de_gestacao(animal.categoria_completa) or _tem_marca_de_gestacao(animal.categoria_abrev)
    ):
        return False

    q_serv = select(Servico).where(Servico.numero_matriz == numero_matriz)
    q_parto = select(Parto).where(Parto.numero_matriz == numero_matriz)
    if fazenda_id is not None:
        q_serv = q_serv.where(Servico.fazenda_id == fazenda_id)
        q_parto = q_parto.where(Parto.fazenda_id == fazenda_id)
    ultimo_parto = max((p.data_parto for p in session.exec(q_parto).all() if p.data_parto), default=None)
    if not prenhez_acabou_sem_parto(list(session.exec(q_serv).all()), ultimo_parto):
        return False

    animal.categoria_completa = categoria_sem_gestacao(animal.categoria_completa, apos_parto=False)
    animal.categoria_abrev = categoria_sem_gestacao(animal.categoria_abrev, apos_parto=False)
    animal.atualizado_em = datetime.utcnow()
    session.add(animal)
    return True
