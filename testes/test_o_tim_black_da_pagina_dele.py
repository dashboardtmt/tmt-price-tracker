# -*- coding: utf-8 -*-
u"""O TIM Black, lido da pagina do proprio plano (27/11/2026).

ATE 26/11/2026 o Black, o Plus e os tres Express vinham do carrossel da
pagina de pos-pago, que a TIM nao atualiza: 70GB para o Black e 80GB para
o Plus, e os Express sem franquia ("ate 67 gigas", que e teto). A pagina
do Black publica os seis cards com a franquia em data-first-consume -
80, 110 e 125GB, e 77, 92 e 117GB nos Express - o mesmo caminho que o
Familia ja tinha desde 24/11.

As fixtures sao recortes reais de 26/11/2026: a pagina do Black (o
drupalSettings e os seis cards) e os cards velhos da pagina de pos-pago.
"""
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import tim  # noqa: E402

FIX = os.path.join(AQUI, "fixtures")
BLACK = io.open(os.path.join(FIX, "tim_black_2026-11-26.html"), encoding="utf-8").read()
POS = io.open(os.path.join(FIX, "tim_pos_cards_2026-11-26.html"), encoding="utf-8").read()


class _ComPaginas(unittest.TestCase):

    def setUp(self):
        guarda = (tim.buscar, tim.navegador, tim.PAUSA)
        self.black, self.pos = BLACK, POS

        def buscar(op, url, *a, **k):
            if url.endswith("/pos-pago/tim-black"):
                return (200, self.black)
            if url.endswith("/planos/pos-pago"):
                return (200, self.pos)
            return (200, "")
        tim.buscar = buscar
        tim.navegador = lambda: None
        tim.PAUSA = 0

        def volta():
            tim.buscar, tim.navegador, tim.PAUSA = guarda
        self.addCleanup(volta)


class APaginaDoBlack(_ComPaginas):

    def test_le_os_seis_planos_com_a_franquia_do_card(self):
        planos, erro = tim.ler_black(None, tim.BLACK % "sp", "SP")
        self.assertIsNone(erro)
        self.assertEqual(
            sorted((o["nome_oferta"], o["preco_promocional"], o["franquia_anunciada_gb"])
                   for o in planos),
            [("TIM Black", 129.99, 80),
             ("TIM Black A Express", 119.99, 77),
             ("TIM Black B Express", 144.99, 92),
             ("TIM Black C Express", 164.99, 117),
             ("TIM Black Plus", 149.99, 110),
             ("TIM Black Premium", 169.99, 125)])

    def test_o_contrato_so_quando_a_composicao_fecha(self):
        u"""O Premium da pagina do Black tem a composicao de um plano
        anterior (40 + 20 + 10 + 10 = 80, num card de 125GB): o contrato
        fica vazio, em vez de 40. O "5 0GB" do C Express e digitacao, e a
        conta fecha (27 + 40 + 50 = 117)."""
        planos, _ = tim.ler_black(None, tim.BLACK % "sp", "SP")
        contrato = dict((o["nome_oferta"], o["franquia_contratual_gb"]) for o in planos)
        self.assertEqual(contrato, {"TIM Black": 40, "TIM Black Plus": 50,
                                    "TIM Black Premium": None,
                                    "TIM Black A Express": 17,
                                    "TIM Black B Express": 22,
                                    "TIM Black C Express": 27})

    def test_o_familia_nao_entra_pela_pagina_do_black(self):
        u = u'<tim-card-pricing-offer field-regioes="sp" data-price="R$ 219,99/mês" '\
            u'data-first-consume="150GB" data-node-name="TIM Black Familia - 150GB"></tim-card-pricing-offer>'
        self.black = BLACK + u
        planos, _ = tim.ler_black(None, tim.BLACK % "sp", "SP")
        self.assertFalse([o for o in planos if "Fam" in o["nome_oferta"]])

    def test_pagina_sem_card_e_erro(self):
        self.black = "<html>nada</html>"
        planos, erro = tim.ler_black(None, tim.BLACK % "sp", "SP")
        self.assertEqual(planos, [])
        self.assertIn("TIM Black", erro)


class OCaminhoDeProducao(_ComPaginas):
    u"""coletar() inteiro: e ele que decide entre a pagina do Black e o
    carrossel velho do pos-pago."""

    def _movel(self):
        r = tim.coletar("Sao Paulo", "SP", verbose=False)
        return dict((o["nome_oferta"], o) for o in r["ofertas"] if o["produto"] == "movel")

    def test_a_franquia_e_a_da_pagina_do_black_e_nao_a_do_carrossel(self):
        m = self._movel()
        self.assertEqual(m["TIM Black"]["franquia_anunciada_gb"], 80)
        self.assertEqual(m["TIM Black Plus"]["franquia_anunciada_gb"], 110)
        self.assertEqual(m["TIM Black Premium"]["franquia_anunciada_gb"], 125)
        for nome, gb in (("A", 77), ("B", 92), ("C", 117)):
            self.assertEqual(m["TIM Black %s Express" % nome]["franquia_anunciada_gb"], gb)

    def test_o_deezer_do_express_vem_do_card_do_pos(self):
        u"""Eleger a fonte por campo: franquia e preco da pagina do Black,
        o Deezer do card do pos-pago, que o JSON do Black nao nomeia."""
        m = self._movel()
        for nome in ("A", "B", "C"):
            self.assertEqual(m["TIM Black %s Express" % nome]["apps"], ["deezer"])
        self.assertFalse(m["TIM Black"].get("apps"))

    def test_sem_a_pagina_do_black_o_carrossel_nao_volta(self):
        u"""Ate 27/11/2026 o carrossel velho preenchia o buraco - e foi assim
        que o Familia Plus saiu a R$ 284,99 nas 20 pracas, com a TIM cobrando
        264,99. Pagina do plano que falha deixa o plano sem leitura, dito."""
        self.black = "<html>nada</html>"
        r = tim.coletar("Sao Paulo", "SP", verbose=False)
        m = dict((o["nome_oferta"], o) for o in r["ofertas"] if o["produto"] == "movel")
        self.assertNotIn("TIM Black", m)
        self.assertFalse([o for o in r["ofertas"] if o.get("pagina") == "pos-pago"
                          and "black" in o["nome_oferta"].lower()])
        self.assertTrue(any(a.startswith("black:") for a in r["avisos"]))


class AGradeSePartePorMovimento(unittest.TestCase):
    u"""A bancada da troca: "129,99: 70 -> 80 GB, +14% de internet pelo mesmo
    preco" saia como noticia, porque a grade e um evento por escada, sem
    nome, e a declaracao procura nome. Agora cada movimento leva o nome da
    oferta, e so o declarado sai."""

    def setUp(self):
        sys.path.insert(0, AQUI)
        import robo
        from _apoio import HOJE, ONTEM, dados, montar, oferta
        self.robo, self.dados, self.montar = robo, dados, montar
        guarda = robo.LEITURA_DE_OFERTA_MUDOU_EM
        robo.LEITURA_DE_OFERTA_MUDOU_EM = {HOJE: [{
            "quem": [("TIM", "movel", u"re:^tim black( plus| [abc] express)?$")],
            "texto": u"o Black passou a ser lido da página dele"}]}
        self.addCleanup(setattr, robo, "LEITURA_DE_OFERTA_MUDOU_EM", guarda)
        pracas = ["Sao Paulo/SP", "Rio de Janeiro/RJ"]

        def dia(data, black, plus, premium):
            return [oferta(operadora="TIM", produto="movel", nome=n, preco=p, gb=g,
                           praca=pr, data=data, chave="TIM|movel|%dgb|simples" % g)
                    for pr in pracas
                    for n, p, g in (("TIM Black", 129.99, black),
                                    ("TIM Black Plus", 149.99, plus),
                                    ("TIM Black Premium", 169.99, premium))]
        # o Black e o Plus relidos; o Premium mexendo de verdade
        self.ontem = dia(ONTEM, 70, 80, 125)
        self.hoje = dia(HOJE, 80, 110, 130)

    def test_o_relido_sai_e_o_premium_fica(self):
        t = self.montar(self.ontem, self.hoje)
        self.assertNotIn(u"70 → 80", t)
        self.assertNotIn(u"80 → 110", t)
        self.assertIn(u"125 → 130", t, "o Premium nao foi declarado")
        self.assertIn("A nossa leitura mudou hoje", t)

    def test_o_levantamento_conta_as_duas_ofertas(self):
        d = self.dados(self.ontem, self.hoje)
        nomes = sorted(set(self.robo._quem_e(x["evento"])[2] for x in d["relidos"]))
        self.assertEqual(nomes, ["TIM Black", "TIM Black Plus"])
        self.assertEqual(self.robo._ofertas_relidas(d["relidos"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
