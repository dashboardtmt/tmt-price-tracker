# -*- coding: utf-8 -*-
u"""A fibra da TIM lida dos cards que o cliente ve.

A auditoria contra o site de 26/11/2026 achou a escada de fibra lendo as
janelas de comparacao escondidas: um "700 MEGA a R$ 99,99" gravado em 19
pracas que nenhuma pagina mostra, e o card "600MEGA Paramount+ a R$ 109,99"
faltando em 9. O card visivel (<tim-card-pricing-offer field-regioes>) traz
a velocidade anunciada, os logos dos apps, o preco e o riscado "De".

A fixture sao os 11 cards distintos das paginas de SP e PE de 26/11/2026,
mais um trecho real da janela escondida de PE com o 700 MEGA fantasma.
"""
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import tim  # noqa: E402

HTML = io.open(os.path.join(AQUI, "fixtures", "tim_fibra_cards_2026-11-26.html"),
               encoding="utf-8").read()


class _ComPagina(unittest.TestCase):

    def setUp(self):
        guarda = (tim.buscar, tim.PAUSA)
        self.html = HTML

        def buscar(op, url, *a, **k):
            return (200, self.html) if "ultrafibra" in url else (200, "")
        tim.buscar = buscar
        tim.PAUSA = 0

        def volta():
            tim.buscar, tim.PAUSA = guarda
        self.addCleanup(volta)

    def ler(self, uf):
        return tim.ler_fibra_por_card(None, tim.FIBRA % uf.lower(), uf)


class OCardVisivel(_ComPagina):

    def test_sao_paulo_tem_os_oito_cards_da_pagina(self):
        ofertas, erro = self.ler("SP")
        self.assertIsNone(erro)
        self.assertEqual(
            [(o["nome_oferta"], o["preco_promocional"], o["preco_cheio"]) for o in
             sorted(ofertas, key=lambda o: o["preco_promocional"])],
            [("TIM Ultrafibra 400 Mega", 79.99, 119.99),
             ("TIM Ultrafibra 1GIGA", 99.99, 189.99),
             ("TIM Ultrafibra 700MEGA Paramount+", 109.99, 149.99),
             ("TIM Ultrafibra 700MEGA Globoplay", 119.99, 159.99),
             ("TIM Ultrafibra 800MEGA YouTube Premium", 129.99, 169.99),
             ("TIM Ultrafibra 1GIGA Paramount+", 149.99, 199.99),
             ("TIM Ultrafibra 1GIGA Max", 159.99, 219.99),
             ("TIM Ultrafibra 2GIGA Paramount+ + Max + Globoplay", 369.99, 419.99)])

    def test_recife_tem_o_600_paramount_que_faltava(self):
        ofertas, _ = self.ler("PE")
        precos = {o["nome_oferta"]: o["preco_promocional"] for o in ofertas}
        self.assertEqual(precos["TIM Ultrafibra 600MEGA Paramount+"], 109.99)
        self.assertEqual(precos["TIM Ultrafibra 500MEGA"], 89.99)
        self.assertNotIn("TIM Ultrafibra 400 Mega", precos)

    def test_o_fantasma_da_janela_nao_entra(self):
        u"""A escada antiga le o 700 MEGA a 99,99 da janela escondida; o card
        nao existe."""
        antiga, _ = tim.ler_escada_de_fibra(None, tim.FIBRA % "pe", "PE")
        self.assertIn(("TIM Ultrafibra 700 MEGA", 99.99),
                      [(o["nome_oferta"], o["preco_promocional"]) for o in antiga])
        ofertas, _ = self.ler("PE")
        self.assertFalse([o for o in ofertas
                          if o["degrau_mbps"] == 700 and o["preco_promocional"] == 99.99])

    def test_a_velocidade_e_a_anunciada_no_card(self):
        u"""O nome interno do card de SP diz "600 MEGA PARAMOUNT"; o card
        anuncia 700MEGA (600 + 100 de bonus), e e o que o cliente compra."""
        ofertas, _ = self.ler("SP")
        p = [o for o in ofertas if "Paramount" in o["nome_oferta"] and o["preco_promocional"] == 109.99][0]
        self.assertEqual(p["degrau_mbps"], 700)
        self.assertIn(u"bônus", p["composicao"])

    def test_os_apps_saem_dos_logos(self):
        ofertas, _ = self.ler("SP")
        dois = [o for o in ofertas if o["degrau_mbps"] == 2000][0]
        for app in ("paramount", "max", "globoplay"):
            self.assertIn(app, dois["apps"])

    def test_mesmo_nome_a_dois_precos_sai_dito(self):
        um = HTML.split("<tim-card-pricing-offer")[1].split("</tim-card-pricing-offer>")[0]
        outro = um.replace("Por R$ 79,99", "Por R$ 74,99")
        self.html = ("<tim-card-pricing-offer" + um + "</tim-card-pricing-offer>"
                     "<tim-card-pricing-offer" + outro + "</tim-card-pricing-offer>")
        ofertas, erro = self.ler("SP")
        self.assertIsNone(ofertas)
        self.assertIn("mais de um preco", erro)

    def test_pagina_sem_card_e_erro(self):
        self.html = "<html>nada</html>"
        ofertas, erro = self.ler("SP")
        self.assertIsNone(ofertas)
        self.assertIn("falhou", erro)


class OCaminhoDeProducao(_ComPagina):
    u"""coletar() inteiro: e ele que grava, e e nele que a hub sai da fibra."""

    def test_o_coletor_grava_os_cards_com_o_riscado(self):
        saida = tim.coletar("Sao Paulo", "SP", verbose=False)
        fibra = sorted((o["nome_oferta"], o["preco_promocional"], o["preco_cheio"])
                       for o in saida["ofertas"] if o["produto"] == "fibra")
        self.assertEqual(len(fibra), 8)
        self.assertIn(("TIM Ultrafibra 1GIGA", 99.99, 189.99), fibra)

    def test_a_fibra_da_hub_nao_entra_mais(self):
        u"""A hub repetia degraus com outro nome ("com Modem Wi-fi gratis")."""
        guarda = tim.ler_ofertas

        def hub(op, url, uf):
            return ([{"nome_oferta": u"TIM Ultrafibra com Modem Wi-fi grátis",
                      "destaque": "400 MEGA", "preco_promocional": 79.99,
                      "franquia_anunciada_gb": None, "validade_dias": None}], None)
        tim.ler_ofertas = hub
        self.addCleanup(setattr, tim, "ler_ofertas", guarda)
        saida = tim.coletar("Sao Paulo", "SP", verbose=False)
        nomes = [o["nome_oferta"] for o in saida["ofertas"] if o["produto"] == "fibra"]
        self.assertNotIn(u"TIM Ultrafibra com Modem Wi-fi grátis", nomes)
        self.assertEqual(len(nomes), 8)


if __name__ == "__main__":
    unittest.main()
