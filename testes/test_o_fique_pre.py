# -*- coding: utf-8 -*-
u"""O Fique Pre da Unifique, pelo cookie da cidade (27/11/2026).

Ficou fora porque "o preco e montado por JavaScript". Nao era: sem o cookie
do seletor a pagina do pre vem sem card, e com ele o HTML servido ja traz o
card - 5 GB, validade de 20 dias, R$ 24,90, WhatsApp* ilimitado. A fixture
e o texto real da pagina de Blumenau em 26/11/2026.
"""
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import unifique  # noqa: E402

PRE = io.open(os.path.join(AQUI, "fixtures", "unifique_fique_pre_2026-11-26.txt"),
              encoding="utf-8").read()


class OFiquePre(unittest.TestCase):

    def test_o_card_do_pre(self):
        self.assertEqual(
            [(o["nome_oferta"], o["preco_promocional"], o["franquia_anunciada_gb"], o["validade_dias"])
             for o in unifique.extrair_pre(PRE)],
            [(u"Fique Pré 5 GB", 24.9, 5, 20)])

    def test_o_detalhe_sem_preco_nao_repete_o_card(self):
        u"""O "Mais detalhes" repete o plano sem preco."""
        self.assertEqual(PRE.count(u"PLANO PRÉ-PAGO"), 2)
        self.assertEqual(len(unifique.extrair_pre(PRE)), 1)


class OCaminhoDeProducao(unittest.TestCase):

    def setUp(self):
        guarda = unifique.buscar
        self.cookies = []

        def buscar(url, cookie=None):
            if url == unifique.PAGINA_PRE:
                self.cookies.append(cookie)
                # sem a cidade, a pagina vem sem card
                return (200, PRE) if cookie else (200, u"Blumenau - SC Planos de Celular Pré-pago")
            if url == unifique.rota_da_cidade("Blumenau", "SC"):
                return 200, u"Blumenau - SC Internet Fibra"      # a cidade atendida
            return 404, ""
        unifique.buscar = buscar
        self.addCleanup(setattr, unifique, "buscar", guarda)

    def test_o_coletor_grava_o_pre_com_o_whatsapp(self):
        d = unifique.coletar("Blumenau", "SC", verbose=False)
        pre = [o for o in d["ofertas"] if o["produto"] == "prepago"]
        self.assertEqual([(o["nome_oferta"], o["preco_promocional"], o["validade_dias"]) for o in pre],
                         [(u"Fique Pré 5 GB", 24.9, 20)])
        self.assertTrue(pre[0]["whatsapp"])

    def test_a_cidade_vai_no_cookie(self):
        unifique.coletar("Blumenau", "SC", verbose=False)
        self.assertEqual(self.cookies, [unifique.cookie_da_cidade("Blumenau", "SC")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
