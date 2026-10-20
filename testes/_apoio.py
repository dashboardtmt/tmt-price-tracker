# -*- coding: utf-8 -*-
"""Um banco de mentira que respeita as datas, para os testes da mensagem.

POR QUE EXISTE. A fixture anterior devolvia uma lista para a consulta de
hoje e outra para a de ontem, olhando so se a data aparecia no caminho -
e ignorava a data DE DENTRO de cada linha. Com isso duas coisas
quebravam em silencio:

  1. As linhas de "hoje" vinham com data_captura de ontem, entao o vigia
     - que filtra pela coluna - via o dia vazio e denunciava "nenhuma
     captura hoje". O teste do dia limpo passava com a mensagem
     contendo "Conferir: nenhuma captura hoje" dentro dela.
  2. Qualquer consulta nova que o robo passasse a fazer recebia a lista
     inteira, sem filtro: o teste nao media o codigo que roda em
     producao, media um atalho.

Aqui o filtro e aplicado de verdade, lendo os operadores do PostgREST
que o robo usa. Fixture que mente sobre o banco testa a fixture.
"""
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
from coletores import armazenamento                           # noqa: E402

HOJE, ONTEM = "2026-10-21", "2026-10-20"

# As nove rodadas de coletor, todas fechadas. Dia bom e o que a maioria
# dos testes precisa como fundo; o dia ruim cada teste monta o seu.
COLETA_OK = [{"data_captura": HOJE,
              "operadora": op, "pracas_ok": 20, "pracas_pedidas": 20,
              "ofertas": 180, "sucesso": True, "iniciada_em": HOJE + "T06:00"}
             for op in ("Vivo", "TIM", "Claro", "Brisanet", "Unifique",
                        "NuCel", "Starlink", "Claro Flex", "TIM FIT")]

FILTRO = re.compile(r"(\w+)=(eq|gte|lte|lt|gt)\.([^&]+)")


def _passa(linha, caminho):
    """Aplica os filtros do caminho a uma linha, como o PostgREST faria."""
    for campo, op, valor in FILTRO.findall(caminho):
        v = urllib.parse.unquote(valor)
        atual = linha.get(campo)
        atual = "" if atual is None else str(atual)
        if op == "eq" and atual != v:
            return False
        if op == "gte" and not atual >= v:
            return False
        if op == "lte" and not atual <= v:
            return False
        if op == "lt" and not atual < v:
            return False
        if op == "gt" and not atual > v:
            return False
    return True


def banco(capturas, coletas=None):
    """Instala o banco de mentira. Devolve as duas funcoes instaladas."""
    linhas = list(capturas)
    registros = COLETA_OK if coletas is None else list(coletas)

    def responder(caminho, pagina=None):
        if caminho.startswith("coletas"):
            return [c for c in registros if _passa(c, caminho)], None
        if caminho.startswith("capturas"):
            return [l for l in linhas if _passa(l, caminho)], None
        return [], None

    armazenamento.consultar_tudo = responder
    armazenamento.consultar = lambda caminho: responder(caminho)
    robo.armazenamento = armazenamento
    return responder


def montar(ontem, hoje, coletas=None, extras=()):
    """A mensagem do dia sobre duas listas de capturas. Devolve o texto."""
    banco(list(ontem) + list(hoje) + list(extras), coletas)
    texto, _dados = robo.montar_mensagem(HOJE, ONTEM)
    return texto


def dados(ontem, hoje, coletas=None, extras=()):
    """Os mesmos numeros, para quem precisa olhar o levantamento."""
    banco(list(ontem) + list(hoje) + list(extras), coletas)
    _texto, d = robo.montar_mensagem(HOJE, ONTEM)
    return d


def sem_declaracao(caso):
    """Limpa LEITURA_MUDOU_EM durante um teste.

    A data declarada manda em tudo - e isso esta certo em producao, onde
    ela diz que a leitura mudou naquele dia. Num teste das HEURISTICAS,
    ela esconderia o que se quer medir: o fixture usa 21/10/2026, que e
    justamente uma data declarada.
    """
    guarda = robo.LEITURA_MUDOU_EM
    robo.LEITURA_MUDOU_EM = {}
    caso.addCleanup(setattr, robo, "LEITURA_MUDOU_EM", guarda)


def oferta(operadora="Vivo", produto="movel", nome="Vivo Pós", preco=119.90,
           gb=50, mbps=None, praca="Sao Paulo/SP", chave=None, data=HOJE,
           sva=None):
    """Uma linha de captura como o banco a devolveria.

    data_captura e NOT NULL no esquema, e a coluna e o que o robo filtra:
    a fixture tem de preenche-la, senao o teste passa com um dado que o
    banco nunca produziria.
    """
    degrau = ("%sgb" % gb) if gb else ("%smbps" % mbps)
    return {"data_captura": data, "operadora": operadora, "produto": produto,
            "praca": praca, "nome_oferta": nome, "preco_promocional": preco,
            "franquia_anunciada_gb": gb, "degrau_mbps": mbps,
            "destaque": ("%s GB" % gb) if gb else ("%s Mbps" % mbps),
            "nivel_bundle": 0, "assinatura_sva": sva,
            "chave": chave or "%s|%s|%s|simples" % (operadora, produto, degrau)}


def em_todas(**kw):
    """A mesma oferta nas 20 pracas do painel."""
    from coletores.pracas import PRACAS, rotulo
    return [oferta(praca=rotulo(p), **kw) for p in PRACAS]
