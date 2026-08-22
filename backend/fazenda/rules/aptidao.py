"""
Aptidão para serviço reprodutivo — a trava que faltava nos pontos de entrada
de inseminação/cobertura/protocolo IATF.

## O buraco que este módulo fecha

Até aqui, NENHUM dos caminhos que criam um serviço validava aptidão. A única
checagem de `POST /reproducao/servico` era "o animal existe"; o lançamento em
lote e o protocolo IATF nem isso. Na prática dava para inseminar uma bezerra
de 4 meses, um macho, um animal baixado ou uma vaca já prenhe — e o pior
caso não é o erro óbvio, é o silencioso: reinseminar uma matriz que consta
como GESTANTE fazia o sistema **inventar sozinho** uma perda de prenhez
(`rules.perda_prenhez.detectar_e_registrar_perda_por_reinseminacao`),
reescrevendo o histórico reprodutivo dela sem ninguém ter afirmado que houve
aborto.

A trava do frontend não cobria isso: `IDADE_MIN_SERVICO = 13` estava
CRAVADO no código da tela (`components/lancamentos/_shared.ts`), divergia do
parâmetro real da fazenda (`idade_apta_min_meses`, hoje 15 meses), só
escondia as inaptas da lista — e o app de campo, o bot do Telegram e
qualquer chamada direta à API passavam por baixo dela.

## Semântica das duas severidades

  * **DURO** — o claramente errado: sexo masculino, animal baixado ou marcado
    a descartar, idade abaixo do mínimo. Devolve 409 e não há como
    prosseguir; se o dado estiver errado, corrige-se o cadastro.
  * **CONFIRMÁVEL** — o limítrofe e legítimo: novilha sem NENHUMA pesagem
    registrada, novilha com peso abaixo do mínimo, e matriz que consta como
    gestante vigente. Devolve 409 explicando a situação; o chamador reenvia
    com `forcar: true` para dizer "eu sei, é isso mesmo". A diferença em
    relação a antes é que a decisão passa a ser de uma PESSOA, e não uma
    inferência silenciosa do sistema.

## Lacunas assumidas de propósito

  * **Sem pesagem nenhuma, não se inventa peso.** O peso vem exclusivamente
    de `PesagemCorporal`, e muita fazenda não pesa novilha. Por isso "sem
    pesagem" é confirmável e não duro — mesma disciplina de
    `rules.estado_reprodutivo.classificar_animal`, que também se recusa a
    reprovar por um dado que nunca foi coletado.
  * **O critério de peso só vale para NULÍPARA.** Uma matriz que já pariu
    passou do estágio em que "atingiu peso de cobertura" quer dizer alguma
    coisa; cobrar pesagem dela seria ruído puro.
  * **Sem data de nascimento nem idade no cadastro, não se bloqueia por
    idade.** Não dá para afirmar que está abaixo do mínimo sem saber a
    idade; o animal passa, e a lacuna fica registrada aqui.

## Onde é aplicada

`POST /reproducao/servico`, `POST /reproducao/servico-lote` (via
`_registrar_um_servico`) e `POST /reproducao/protocolo-iatf` — os três
pontos de entrada de serviço/IA do backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlmodel import Session, select

from fazenda.models import Animal, PesagemCorporal, Servico
from fazenda.rules.parametros import idade_apta_min_meses, peso_apta_min
from fazenda.rules.perda_prenhez import servico_esta_positivo_vigente

# Conversão mês -> dia usada em todo o projeto (ver rules/indicadores.py,
# routers/recria.py): a idade mínima é comparada em DIAS, para não depender
# do arredondamento de "meses" do cadastro.
DIAS_POR_MES = 30.44

# ---------------------------------------------------------------------------
# Severidades
# ---------------------------------------------------------------------------
SEVERIDADE_DURA = "duro"
SEVERIDADE_CONFIRMAVEL = "confirmavel"

# Códigos de motivo — estáveis, para o frontend decidir se oferece o botão
# "confirmar mesmo assim" sem precisar interpretar o texto da mensagem.
MOTIVO_SEXO = "sexo"
MOTIVO_INATIVO = "inativo"
MOTIVO_A_DESCARTAR = "a_descartar"
MOTIVO_IDADE = "idade"
MOTIVO_SEM_PESAGEM = "sem_pesagem"
MOTIVO_PESO = "peso"
MOTIVO_GESTANTE = "gestante"


@dataclass(frozen=True)
class ParametrosAptidao:
    """Os dois parâmetros de aptidão da fazenda (Configurações > Parâmetros >
    Aptidão da novilha), lidos uma vez e passados adiante — a avaliação em si
    fica pura e testável sem banco."""

    idade_apta_min_meses: float
    peso_apta_min_kg: float

    @property
    def idade_apta_min_dias(self) -> int:
        return round(self.idade_apta_min_meses * DIAS_POR_MES)


@dataclass(frozen=True)
class ContextoAptidao:
    """O que se sabe do animal no momento do serviço, já resolvido do banco.

    `peso_kg` é o peso da pesagem MAIS RECENTE até a data do serviço;
    `tem_pesagem` distingue "pesou e está leve" de "nunca pesou" — os dois
    levam a mensagens diferentes, e confundi-los é o que faria o sistema
    reprovar uma novilha por um dado que ninguém coletou.
    """

    idade_dias: int | None = None
    peso_kg: float | None = None
    tem_pesagem: bool = False
    ja_pariu: bool = False
    servico_vigente: Any | None = None


@dataclass(frozen=True)
class AptidaoResultado:
    """Veredito da avaliação. `apta=True` quando nada impede o serviço."""

    apta: bool
    motivo: str | None = None
    mensagem: str | None = None
    severidade: str | None = None

    @property
    def confirmavel(self) -> bool:
        """True quando um `forcar=true` explícito destrava este bloqueio."""
        return self.severidade == SEVERIDADE_CONFIRMAVEL

    def bloqueia(self, forcar: bool = False) -> bool:
        """True quando o serviço NÃO pode ser gravado. `forcar` só destrava
        os bloqueios confirmáveis — nunca os duros."""
        if self.apta:
            return False
        return not (forcar and self.confirmavel)


APTA = AptidaoResultado(apta=True)


def parametros_aptidao() -> ParametrosAptidao:
    """Lê os parâmetros vigentes da fazenda. Ponto único — nenhum chamador
    deve cravar 13, 15 ou 300 no código (foi exatamente isso que fez a tela
    de Lançamentos divergir do resto do sistema)."""
    return ParametrosAptidao(
        idade_apta_min_meses=idade_apta_min_meses(),
        peso_apta_min_kg=peso_apta_min(),
    )


def avaliar_aptidao_servico(
    animal: Any, contexto: ContextoAptidao, params: ParametrosAptidao,
) -> AptidaoResultado:
    """Este animal pode receber uma inseminação/cobertura/protocolo?

    Função PURA — sem `Session`, sem HTTP. Devolve o PRIMEIRO impedimento
    encontrado, na ordem "mais grave primeiro": os bloqueios duros antes dos
    confirmáveis, para a mensagem mostrada ao usuário ser a que de fato
    exige ação (não adianta dizer "sem pesagem" de um animal que já foi
    baixado).
    """
    numero = _get(animal, "numero") or "?"

    # ── Duros ────────────────────────────────────────────────────────────
    sexo = (_get(animal, "sexo") or "").strip().upper()
    if _get(animal, "eh_semen") or sexo == "M":
        return AptidaoResultado(
            False, MOTIVO_SEXO,
            f"{numero} não é uma fêmea do rebanho — só matrizes recebem serviço reprodutivo.",
            SEVERIDADE_DURA,
        )
    if _get(animal, "ativo") is False:
        return AptidaoResultado(
            False, MOTIVO_INATIVO,
            f"{numero} está baixado(a) do rebanho — reative o cadastro antes de lançar o serviço.",
            SEVERIDADE_DURA,
        )
    if _get(animal, "a_descartar"):
        return AptidaoResultado(
            False, MOTIVO_A_DESCARTAR,
            f"{numero} está marcado(a) como 'a descartar' e sai de todas as ações reprodutivas. "
            "Desmarque em Rebanho > Baixa se a decisão mudou.",
            SEVERIDADE_DURA,
        )
    if contexto.idade_dias is not None and contexto.idade_dias < params.idade_apta_min_dias:
        idade_meses = round(contexto.idade_dias / DIAS_POR_MES, 1)
        return AptidaoResultado(
            False, MOTIVO_IDADE,
            f"{numero} tem {idade_meses} meses — abaixo da idade mínima de aptidão "
            f"({params.idade_apta_min_meses:g} meses, em Configurações > Parâmetros).",
            SEVERIDADE_DURA,
        )

    # ── Confirmáveis ─────────────────────────────────────────────────────
    # Gestante vem antes do peso: reinseminar uma matriz prenhe é a decisão
    # de maior consequência (o sistema grava uma perda de prenhez no serviço
    # anterior), então é ela que precisa aparecer na mensagem.
    if contexto.servico_vigente is not None and servico_esta_positivo_vigente(contexto.servico_vigente):
        data_servico = _get(contexto.servico_vigente, "data_servico")
        quando = f" (serviço de {data_servico.strftime('%d/%m/%Y')})" if isinstance(data_servico, date) else ""
        return AptidaoResultado(
            False, MOTIVO_GESTANTE,
            f"{numero} consta como GESTANTE{quando}. Lançar um serviço novo registra a perda da prenhez "
            "atual no serviço anterior. Confirme se é isso mesmo, ou lance a perda de prenhez com o motivo "
            "correto antes.",
            SEVERIDADE_CONFIRMAVEL,
        )
    # Peso só faz sentido para nulípara — ver a docstring do módulo.
    if not contexto.ja_pariu:
        if not contexto.tem_pesagem:
            return AptidaoResultado(
                False, MOTIVO_SEM_PESAGEM,
                f"{numero} não tem nenhuma pesagem registrada, então não dá para conferir o peso mínimo de "
                f"aptidão ({params.peso_apta_min_kg:g} kg). Lance a pesagem ou confirme o serviço mesmo assim.",
                SEVERIDADE_CONFIRMAVEL,
            )
        if contexto.peso_kg is not None and contexto.peso_kg < params.peso_apta_min_kg:
            return AptidaoResultado(
                False, MOTIVO_PESO,
                f"{numero} pesou {contexto.peso_kg:g} kg na última pesagem — abaixo do peso mínimo de "
                f"aptidão ({params.peso_apta_min_kg:g} kg, em Configurações > Parâmetros).",
                SEVERIDADE_CONFIRMAVEL,
            )

    return APTA


# ---------------------------------------------------------------------------
# Resolução do contexto a partir do banco
# ---------------------------------------------------------------------------
def _get(obj: Any, campo: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(campo)
    return getattr(obj, campo, None)


def contexto_aptidao(
    session: Session, animal: Animal, *, data: date, fazenda_id: int | None = None,
) -> ContextoAptidao:
    """Monta o `ContextoAptidao` do animal na data do serviço.

    O serviço vigente é o MAIS RECENTE até a data — e a pergunta "ele ainda
    vale como prenhez" fica com `rules.perda_prenhez.servico_esta_positivo_
    vigente`, a mesma função que o resto do sistema usa. Aqui não se repete
    o filtro `diagnostico == "POSITIVO"`, que esquecia `data_perda_prenhez`
    e mantinha gestante quem já tinha a perda registrada.

    Serviços anteriores ao último parto não contam: pertencem à lactação
    passada, já resolvida pelo parto.
    """
    from fazenda.models import Parto

    idade_dias: int | None = None
    if animal.data_nasc:
        idade_dias = (data - animal.data_nasc).days
    elif animal.idade_meses is not None:
        idade_dias = round(float(animal.idade_meses) * DIAS_POR_MES)

    query_pesagem = select(PesagemCorporal).where(PesagemCorporal.numero_matriz == animal.numero)
    if fazenda_id is not None:
        query_pesagem = query_pesagem.where(PesagemCorporal.fazenda_id == fazenda_id)
    pesagens = [p for p in session.exec(query_pesagem).all() if p.data_pesagem and p.data_pesagem <= data]
    ultima_pesagem = max(pesagens, key=lambda p: p.data_pesagem, default=None)

    query_parto = select(Parto).where(Parto.numero_matriz == animal.numero)
    if fazenda_id is not None:
        query_parto = query_parto.where(Parto.fazenda_id == fazenda_id)
    partos = [p for p in session.exec(query_parto).all() if p.data_parto and p.data_parto <= data]
    ultimo_parto = max((p.data_parto for p in partos), default=None)

    query_servico = select(Servico).where(Servico.numero_matriz == animal.numero)
    if fazenda_id is not None:
        query_servico = query_servico.where(Servico.fazenda_id == fazenda_id)
    servicos = [
        s for s in session.exec(query_servico).all()
        if s.data_servico and s.data_servico <= data
        and (ultimo_parto is None or s.data_servico > ultimo_parto)
    ]
    servico_vigente = max(servicos, key=lambda s: s.data_servico, default=None)

    return ContextoAptidao(
        idade_dias=idade_dias,
        peso_kg=ultima_pesagem.peso_kg if ultima_pesagem else None,
        tem_pesagem=ultima_pesagem is not None,
        ja_pariu=bool(partos),
        servico_vigente=servico_vigente,
    )


def avaliar_aptidao_no_banco(
    session: Session, animal: Animal, *, data: date, fazenda_id: int | None = None,
    params: ParametrosAptidao | None = None,
) -> AptidaoResultado:
    """Atalho: resolve o contexto e avalia. Usado pelos routers."""
    return avaliar_aptidao_servico(
        animal,
        contexto_aptidao(session, animal, data=data, fazenda_id=fazenda_id),
        params or parametros_aptidao(),
    )
