# -*- coding: utf-8 -*-
u"""A faixa da campanha da Unifique nao e o nome do plano.

DE 19 A 23/11/2026 A UNIFIQUE GANHOU UMA FAIXA DE BLACK FRIDAY, entre o
nome e a velocidade de cada card:

    FIBRA IDEAL
    BLACK UNIFIQUE - 1o PAGAMENTO EM 2027
    500 Mega

O coletor le como nome o trecho em maiusculas colado na velocidade, e o
"o" sobrescrito cortava a leitura: sobrou "PAGAMENTO EM 2027" como nome
de quatro planos e "MAS VOCE CONTINUA ONLINE" ("FALTOU LUZ, ...") como
nome dos tres FIBRA + POWER. A mensagem de 19/11 disse que tres fibras
"mudaram de nome"; a de 20/11, que entrou UMA oferta chamada "MAS VOCE
CONTINUA ONLINE" - eram tres planos, com o mesmo nome errado. E em 24/11
o FIBRA ESSENCIAL saiu da vitrine sem nenhuma linha, porque "PAGAMENTO EM
2027" continuava existindo nos outros planos.

A faixa sai pela classe (campaign-plan-badge) antes de o texto ser lido.
O QUE ESTE ARQUIVO PRENDE, com o recorte da pagina real de 23/11:
  - os seis nomes da pagina, pelo caminho de producao (buscar + extrair);
  - preco e velocidade de cada um;
  - nenhuma frase da faixa no nome.
"""
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import unifique                               # noqa: E402

PAGINA = os.path.join(AQUI, "fixtures", "unifique_florianopolis_2026-11-23.html")


class _Resposta(object):
    status = 200

    def __init__(self, corpo):
        self.corpo = corpo

    def read(self):
        return self.corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class AFaixaNaoEONome(unittest.TestCase):

    def setUp(self):
        with io.open(PAGINA, "rb") as f:
            corpo = f.read()
        guarda = unifique.urllib.request.urlopen

        # desde 26/11/2026 a coleta le tambem o combo e o celular; a
        # fixture e so a pagina de fibra, e as outras rotas respondem 404
        def abrir(req, timeout=None):
            if "internet-fibra" in req.full_url:
                return _Resposta(corpo)
            raise unifique.urllib.error.HTTPError(req.full_url, 404, "nao", {}, None)
        unifique.urllib.request.urlopen = abrir
        self.addCleanup(setattr, unifique.urllib.request, "urlopen", guarda)

    def test_o_recorte_tem_a_faixa(self):
        u"""Sem a faixa no recorte, nada aqui seria medido."""
        with io.open(PAGINA, encoding="utf-8") as f:
            html = f.read()
        self.assertEqual(html.count("campaign-plan-badge"), 6)
        self.assertIn("1º PAGAMENTO EM 2027", html)

    def test_os_seis_planos_com_o_nome_da_pagina(self):
        r = unifique.coletar("Florianopolis", "SC", verbose=False)
        lidos = sorted((o["degrau_mbps"], o["preco_promocional"], o["nome_oferta"])
                       for o in r["ofertas"])
        self.assertEqual(lidos, [
            (500, 119.9, "FIBRA IDEAL"),
            (500, 134.9, "FIBRA + POWER"),
            (600, 129.9, "FIBRA COMPLETA"),
            (600, 144.9, "FIBRA + POWER"),
            (1000, 159.9, "FIBRA TURBO"),
            (1000, 174.9, "FIBRA + POWER"),
        ])
        # nenhum aviso da fibra; o combo e o celular respondem 404 aqui
        self.assertEqual([a for a in r["avisos"] if "nao vende" not in a], [])

    def test_nenhuma_frase_da_faixa_vira_nome(self):
        r = unifique.coletar("Florianopolis", "SC", verbose=False)
        for o in r["ofertas"]:
            for pedaco in ("PAGAMENTO", "CONTINUA ONLINE", "BLACK", "FALTOU"):
                self.assertNotIn(pedaco, o["nome_oferta"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
