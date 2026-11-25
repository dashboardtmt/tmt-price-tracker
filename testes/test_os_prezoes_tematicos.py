# -*- coding: utf-8 -*-
u"""Os Prezoes tematicos da Claro, e o preco cheio da Starlink.

Em 25/11/2026 quem le abriu o site da Claro e viu ofertas de pre-pago de
R$ 35 que o tracker nunca teve: a pagina do Prezao tem duas abas, e so a
primeira era lida. Os cinco Prezoes tematicos (Kwai, TikTok, Uber, Shopee
e Free Fire) moram em /celular/planos-pre/ofertas-pre. A fixture e o texto
da pagina em 25/11/2026, como o coletor o ve depois de tirar as tags.

No mesmo dia, a Starlink publicava o preco cheio (189 e 249) ao lado do
promocional (132,30 e 174,30), e o coletor gravava o cheio vazio.
"""
import io
import json
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from coletores import armazenamento, claro, starlink           # noqa: E402
from test_o_prezao_soma import TABELA                         # noqa: E402

PAGINA = io.open(os.path.join(AQUI, "fixtures", "claro_prezao_tematicos_2026-11-25.txt"),
                 encoding="utf-8").read()


class _ComPaginas(unittest.TestCase):

    def paginas(self, por_url):
        guarda = (claro.buscar, claro.PAUSA)

        def buscar(op, url, *a, **k):
            for pedaco, resposta in por_url.items():
                if pedaco in url:
                    return resposta
            return 200, ""
        claro.buscar = buscar
        claro.PAUSA = 0

        def volta():
            claro.buscar, claro.PAUSA = guarda
        self.addCleanup(volta)


class OsCincoCards(_ComPaginas):

    def ler(self, pagina=PAGINA):
        self.paginas({"ofertas-pre": (200, pagina)})
        return claro.ler_prezao_tematico(None, claro.PREZAO_TEMATICOS)

    def test_os_cinco_como_a_pagina_mostra(self):
        ofertas, erro = self.ler()
        self.assertIsNone(erro)
        lidas = [(o["nome_oferta"], o["preco_promocional"], o["franquia_anunciada_gb"],
                  o["franquia_contratual_gb"], o["validade_dias"], o["whatsapp"])
                 for o in ofertas]
        self.assertEqual(lidas, [
            ("Claro Prezao Kwai 22GB", 35.0, 22, 17, 30, True),
            ("Claro Prezao Uber 17GB", 35.0, 17, 12, 30, True),
            ("Claro Prezao TikTok 22GB", 35.0, 22, 17, 30, True),
            ("Claro Prezao Free Fire 17GB", 34.99, 17, 12, 30, True),
            ("Claro Prezao Shopee 17GB", 35.0, 17, 12, 30, True),
        ])

    def test_o_card_vence_a_tabela_de_renovacao(self):
        u"""A tabela do pe da pagina poe o Free Fire na coluna de R$ 35,00;
        o card de contratar diz R$ 34,99."""
        ofertas, _ = self.ler()
        ff = [o for o in ofertas if "Free Fire" in o["nome_oferta"]][0]
        self.assertEqual(ff["preco_promocional"], 34.99)

    def test_a_validade_sai_da_tabela(self):
        u"""O card diz "/mes"; os dias vem da tabela. Mudando la, muda aqui
        - prova de que nao e o 30 de reserva."""
        ofertas, _ = self.ler(PAGINA.replace("17GB + 5GB Kwai/30 dias", "17GB + 5GB Kwai/28 dias"))
        kwai = [o for o in ofertas if "Kwai" in o["nome_oferta"]][0]
        self.assertEqual(kwai["validade_dias"], 28)

    def test_o_brinde_fica_na_composicao(self):
        ofertas, _ = self.ler()
        por = dict((o["nome_oferta"], o["composicao"]) for o in ofertas)
        self.assertIn("Voucher de R$10", por["Claro Prezao Uber 17GB"])
        self.assertIn("Cupom de R$15", por["Claro Prezao Shopee 17GB"])
        self.assertIn("Diamantes", por["Claro Prezao Free Fire 17GB"])

    def test_cada_tema_tem_a_sua_serie(self):
        u"""Kwai e TikTok entregam 22 GB; Uber, Shopee e Free Fire, 17. Sem o
        tema na variante, as cinco dividiriam duas chaves."""
        ofertas, _ = self.ler()
        chaves = [armazenamento.chave_continuidade(o) for o in ofertas]
        self.assertEqual(len(set(chaves)), 5)

    def test_pagina_sem_card_avisa(self):
        ofertas, erro = self.ler("<html>pagina nova</html>")
        self.assertIsNone(ofertas)
        self.assertIn("nenhum Prezao tematico", erro)


class NoColetar(_ComPaginas):
    u"""O caminho de producao: coletar() junta o Prezao e os tematicos."""

    def pre(self, r):
        return [o for o in r["ofertas"] if o["produto"] == "prepago"]

    def test_o_prezao_e_os_tematicos_juntos(self):
        self.paginas({"planos-pre/prezao": (200, TABELA), "ofertas-pre": (200, PAGINA)})
        r = claro.coletar("Sao Paulo", "SP", verbose=False)
        nomes = sorted(o["nome_oferta"] for o in self.pre(r))
        self.assertEqual(len(nomes), 9)
        self.assertIn("Claro Prezao 5GB", nomes)
        self.assertIn("Claro Prezao Kwai 22GB", nomes)
        self.assertTrue(all(o["operadora"] == "Claro" and o["praca"] == "Sao Paulo/SP"
                            for o in self.pre(r)))

    def test_tematicos_fora_do_ar_nao_derrubam_o_prezao(self):
        self.paginas({"planos-pre/prezao": (200, TABELA), "ofertas-pre": (500, "")})
        r = claro.coletar("Sao Paulo", "SP", verbose=False)
        self.assertEqual(len(self.pre(r)), 4)
        self.assertTrue(any("tematicos" in a for a in r["avisos"]))

    def test_prezao_fora_do_ar_nao_derruba_os_tematicos(self):
        self.paginas({"planos-pre/prezao": (500, ""), "ofertas-pre": (200, PAGINA)})
        r = claro.coletar("Sao Paulo", "SP", verbose=False)
        self.assertEqual(len(self.pre(r)), 5)
        self.assertTrue(any(a.startswith("prepago:") for a in r["avisos"]))


class OPrecoCheioDaStarlink(unittest.TestCase):

    def coletar(self, assinatura):
        corpo = json.dumps({"isAvailable": True, "subscriptions": [assinatura],
                            "kits": [], "isoCurrencyCode": "BRL"})
        guarda = (starlink._http, starlink.PAUSA)
        starlink._http = lambda url, *a, **k: (200, corpo)
        starlink.PAUSA = 0

        def volta():
            starlink._http, starlink.PAUSA = guarda
        self.addCleanup(volta)
        return starlink.coletar(verbose=False)["ofertas"][0]

    def test_na_promocao_o_cheio_e_gravado(self):
        o = self.coletar({"description": "Residencial: 100 Mbps", "price": 189,
                          "adjustedPrice": 132.3, "promoEndDate": "2026-11-30T23:59:00+00:00"})
        self.assertEqual((o["preco_promocional"], o["preco_cheio"]), (132.3, 189.0))

    def test_sem_promocao_o_cheio_fica_vazio(self):
        o = self.coletar({"description": "Residencial: 100 Mbps", "price": 189,
                          "adjustedPrice": 189})
        self.assertEqual((o["preco_promocional"], o["preco_cheio"]), (189.0, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
