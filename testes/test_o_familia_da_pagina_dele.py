# -*- coding: utf-8 -*-
u"""O TIM Black Familia, lido da pagina do proprio plano.

ATE 24/11/2026 os quatro planos vinham de um carrossel da pagina de
pos-pago que o cliente nao ve, e que a TIM nao atualiza: R$ 284,99 para
o Familia Plus, contra R$ 264,99 na pagina do plano, e sem franquia em
tres dos quatro. A pagina do Familia publica cada plano num
<tim-card-pricing-offer> com nome, franquia e preco total em atributo.

E NO PRIMEIRO DIA A DIFERENCA E A NOSSA LEITURA, nao a TIM baixando o
preco: robo.LEITURA_DE_OFERTA_MUDOU_EM tira da noticia o que os
detectores acham nas ofertas declaradas, e a mensagem diz isso numa
linha. Escolha de quem le, em 24/11/2026.
"""
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))

import robo                                                   # noqa: E402
from coletores import tim                                     # noqa: E402
from _apoio import HOJE, ONTEM, dados, montar, oferta         # noqa: E402

PAGINA = os.path.join(AQUI, "fixtures", "tim_black_familia_2026-11-24.html")


class OFamiliaDaPaginaDele(unittest.TestCase):

    def setUp(self):
        with io.open(PAGINA, encoding="utf-8") as f:
            self.html = f.read()
        guarda = (tim.buscar, tim.navegador, tim.PAUSA)
        html = self.html
        tim.buscar = lambda op, url, *a, **k: (
            (200, html) if "tim-black-familia" in url else (200, ""))
        tim.navegador = lambda: None
        tim.PAUSA = 0

        def volta():
            tim.buscar, tim.navegador, tim.PAUSA = guarda
        self.addCleanup(volta)

    def test_o_recorte_tem_o_preco_velho_do_json(self):
        u"""Sem o 88,00 no JSON o teste nao mede a escolha da fonte."""
        self.assertIn('"88,00"', self.html)
        self.assertIn("264,99", self.html)

    def test_le_os_quatro_planos_com_o_total_e_a_franquia(self):
        planos, erro = tim.ler_familia(None, tim.FAMILIA % "sp", "SP")
        self.assertIsNone(erro)
        lidos = dict((o["nome_oferta"], (o["preco_promocional"],
                                         o["franquia_anunciada_gb"],
                                         o["franquia_contratual_gb"]))
                     for o in planos)
        self.assertEqual(lidos[u"TIM Black Família Plus"], (264.99, 180, 100))
        self.assertEqual(lidos[u"TIM Black Família"], (219.99, 150, 80))
        self.assertEqual(lidos[u"TIM Black Família VIP"], (399.99, 250, 180))
        self.assertEqual(lidos[u"TIM Black Família Premium"], (314.99, 210, 120))

    def test_o_caminho_de_producao_grava_o_familia(self):
        r = tim.coletar("Sao Paulo", "SP", verbose=False)
        fam = dict((o["nome_oferta"], o) for o in r["ofertas"]
                   if u"Família" in o["nome_oferta"])
        self.assertEqual(fam[u"TIM Black Família Plus"]["preco_promocional"], 264.99)
        self.assertEqual(fam[u"TIM Black Família Plus"]["franquia_anunciada_gb"], 180)
        self.assertEqual(fam[u"TIM Black Família Plus"]["produto"], "movel")


class ALeituraDeclaradaSaiDaNoticia(unittest.TestCase):

    def setUp(self):
        guarda = robo.LEITURA_DE_OFERTA_MUDOU_EM
        robo.LEITURA_DE_OFERTA_MUDOU_EM = {HOJE: [{
            "quem": [("TIM", "movel", u"TIM Black Família")],
            "texto": u"o Família passou a ser lido da página dele"}]}
        self.addCleanup(setattr, robo, "LEITURA_DE_OFERTA_MUDOU_EM", guarda)

    def _dia(self):
        pracas = ["Sao Paulo/SP", "Rio de Janeiro/RJ"]
        ontem = [oferta(operadora="TIM", produto="movel",
                        nome=u"TIM Black Família Plus", preco=284.99, gb=None,
                        mbps=None, praca=p, data=ONTEM,
                        chave=u"TIM|movel|0gb|tim_black_familia_plus")
                 for p in pracas]
        hoje = [oferta(operadora="TIM", produto="movel",
                       nome=u"TIM Black Família Plus", preco=264.99, gb=180,
                       praca=p, data=HOJE, chave=u"TIM|movel|180gb|familia")
                for p in pracas]
        # e um TIM Black de verdade mudando de preco no mesmo dia
        ontem += [oferta(operadora="TIM", produto="movel", nome="TIM Black",
                         preco=129.99, gb=70, praca=p, data=ONTEM,
                         chave="TIM|movel|70gb|simples") for p in pracas]
        hoje += [oferta(operadora="TIM", produto="movel", nome="TIM Black",
                        preco=139.99, gb=70, praca=p, data=HOJE,
                        chave="TIM|movel|70gb|simples") for p in pracas]
        return ontem, hoje

    def test_o_preco_relido_nao_e_noticia_e_o_outro_e(self):
        ontem, hoje = self._dia()
        t = montar(ontem, hoje)
        self.assertNotIn("284,99", t)
        self.assertIn("A nossa leitura mudou hoje", t)
        self.assertIn("129,99", t, "o reajuste do TIM Black continua noticia")

    def test_a_lista_vai_para_o_levantamento(self):
        ontem, hoje = self._dia()
        d = dados(ontem, hoje)
        nomes = set(robo._quem_e(x["evento"])[2] for x in d["relidos"])
        self.assertEqual(nomes, {u"TIM Black Família Plus"})
        self.assertEqual(d["relidos_porque"], [u"o Família passou a ser lido da página dele"])

    def test_fora_do_dia_declarado_e_noticia(self):
        robo.LEITURA_DE_OFERTA_MUDOU_EM = {}
        ontem, hoje = self._dia()
        t = montar(ontem, hoje)
        self.assertIn("284,99", t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
