"""Retentativa para as requisicoes dos coletores.

POR QUE EXISTE. Em 07/10/2026 a coleta movel da Claro falhou com erro de
conexao e voltou a responder 200 nas tres tentativas seguintes, feitas
segundos depois. Um soluco de rede de dois segundos custava o produto
inteiro daquela operadora no dia, e a recuperacao dependia do repique -
que agora so roda quando a coleta falha, e portanto so corrige o dia
inteiro, nao o soluco pontual.

O QUE SE RETENTA, E O QUE NAO. Insistir em cima de uma recusa e pior que
desistir: repetir um 403 de anti-bot aumenta a chance de bloqueio mais
longo, e repetir um 404 nao muda nada porque a ausencia e real.

    retenta        falha de conexao, timeout, e 5xx (defeito do servidor)
    nao retenta    2xx e 3xx (deu certo), 4xx (recusa ou ausencia reais)

A espera cresce entre as tentativas, para nao bater na mesma janela de
instabilidade - e porque a Vivo ja bloqueou o acesso durante a
investigacao quando as requisicoes vieram em rajada.
"""

import time

# Esperas entre as tentativas, em segundos. Tres tentativas no total: a
# primeira, uma 2s depois e uma 5s depois. Mais que isso atrasaria a
# coleta inteira sem ganho - o que cai por mais de 7 segundos costuma
# estar fora por minutos, e aí o caso é do repique.
ESPERAS = (2, 5)


def transitoria(status):
    """O status merece outra tentativa?"""
    # 0 e o codigo que os coletores usam quando a requisicao nem chegou a
    # ter resposta: timeout, conexao recusada, DNS
    return status == 0 or status >= 500


def insistir(fazer, descricao="", esperas=ESPERAS, avisos=None):
    """Chama fazer() ate dar certo ou acabarem as tentativas.

    `fazer` devolve (status, corpo), como as funcoes de requisicao dos
    coletores. Devolve o mesmo par.

    Quando uma retentativa acontece, registra em `avisos` se a lista for
    passada: instabilidade que se repete todo dia e sinal de que a fonte
    mudou de comportamento, e isso nao pode ficar invisivel so porque a
    segunda tentativa salvou o dia.
    """
    status, corpo = fazer()
    for i, espera in enumerate(esperas, start=1):
        if not transitoria(status):
            return status, corpo
        time.sleep(espera)
        status, corpo = fazer()
        if not transitoria(status) and avisos is not None:
            avisos.append("%s: respondeu na tentativa %d (a anterior falhou)"
                          % (descricao or "requisicao", i + 1))
    return status, corpo
