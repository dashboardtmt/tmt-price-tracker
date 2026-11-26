# -*- coding: utf-8 -*-
u"""Tres campos da Vivo que o card diz e o tracker nao gravava (26/11/2026,
auditoria contra o site).

- O LITE ANUNCIA O BONUS: o regulamento registra 30 e 40 GB, e o card diz
  "30 GB + 5 GB de bonus 12 meses" - 35 e 45 GB anunciados, 30 e 40 de
  contrato, como nas outras operadoras.
- A FIBRA COM DISNEY+ ACABA EM 12 MESES: "R$ 100/mes - Apos 1 ano: R$ 120/mes".
- O PRE DIZ "VALE SAUDE FARMA" (desconto em farmacia), e o tracker escrevia
  "Vale Saude Sempre", a telemedicina do Controle Saude.

As fixtures do Lite sao recortes reais de 26/11/2026: os tres cards que
dizem bonus e os regulamentos dos quatro codigos que eles linkam.
"""
import io
import json
import os
import sys
import unittest
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import apps, vivo  # noqa: E402

FIX = os.path.join(AQUI, "fixtures")
LITE = io.open(os.path.join(FIX, "vivo_lite_bonus_2026-11-26.html"), encoding="utf-8").read()
REGS = json.load(io.open(os.path.join(FIX, "vivo_lite_regulamentos_2026-11-26.json"), encoding="utf-8"))


class OBonusDoLite(unittest.TestCase):

    def setUp(self):
        guarda = vivo.buscar
        self.html = LITE
        vivo.buscar = lambda op, url, **kw: (200, self.html)
        self.addCleanup(setattr, vivo, "buscar", guarda)
        for cod, reg in REGS.items():
            vivo._cache_regulamento[cod] = reg
            self.addCleanup(vivo._cache_regulamento.pop, cod, None)

    def ler(self):
        ofertas, erro = vivo.ler_lite(None, date(2026, 11, 26), [])
        self.assertIsNone(erro)
        return dict((o["nome_oferta"], o) for o in ofertas)

    def test_a_franquia_anunciada_e_a_do_card(self):
        de = self.ler()
        self.assertEqual(
            sorted((n, o["preco_promocional"], o["franquia_anunciada_gb"], o["franquia_contratual_gb"])
                   for n, o in de.items()),
            [("Vivo Lite + YouTube Premium Lite", 40.0, 45, 40),
             ("Vivo Lite Anual II", 30.0, 35, 30),
             ("Vivo Lite Mensal II", 45.0, 35, 30),
             ("Vivo Lite Mensal III", 55.0, 45, 40)])

    def test_card_sem_bonus_deixa_o_regulamento(self):
        self.html = LITE.replace("de bônus", "de internet")
        de = self.ler()
        self.assertEqual(de["Vivo Lite Anual II"]["franquia_anunciada_gb"], 30)
        self.assertIsNone(de["Vivo Lite Anual II"]["franquia_contratual_gb"])

    def test_bonus_de_outro_contrato_nao_vale(self):
        u"""O card diz 30 + 5 e o regulamento do codigo diz 40: o card fala
        de outra oferta, e o bonus nao entra."""
        self.html = LITE.replace("30 GB + 5 GB", "20 GB + 5 GB")
        de = self.ler()
        self.assertEqual(de["Vivo Lite Anual II"]["franquia_anunciada_gb"], 30)


class OQueValeEOSite(unittest.TestCase):
    u"""O Vivo Fibra 500 Mega Lite e um card da vitrine com regulamento
    vencido em 11/07/2026. Decisao de quem le, 26/11/2026: "o que vale e
    sempre o site". No card, entra; fora dos cards, continua de fora."""

    VENCIDO = {"nomeOferta": "Vivo Fibra 500 Mega Lite.", "precoSemDescontos": "90",
               "dataFimOferta": "11/07/2026",
               "SCM": {"velocidade": {"download": "500", "unidadeDownload": "Mbps"}}, "SMP": {}}

    def setUp(self):
        guarda = vivo.buscar
        self.html = (u'<div class="unique-card "><p>Internet Fibra 500 Mbps Plano anual</p>'
                     u'<a href="VIV202603022618">Baixar condições da oferta</a></div>')
        vivo.buscar = lambda op, url, **kw: (200, self.html)
        self.addCleanup(setattr, vivo, "buscar", guarda)
        for cod in ("VIV202603022618", "VIV202699999999"):
            vivo._cache_regulamento[cod] = self.VENCIDO
            self.addCleanup(vivo._cache_regulamento.pop, cod, None)

    def test_o_card_vencido_entra(self):
        avisos = []
        ofertas, erro = vivo.ler_lite(None, date(2026, 11, 26), avisos)
        self.assertIsNone(erro)
        self.assertEqual([(o["nome_oferta"], o["produto"], o["degrau_mbps"], o["preco_promocional"])
                          for o in ofertas], [("Vivo Fibra 500 Mega Lite", "fibra", 500, 90.0)])
        self.assertTrue(any("gravados porque o card esta na vitrine" in a for a in avisos))

    def test_o_codigo_fora_do_card_continua_de_fora(self):
        self.html += u'<script>var x = "VIV202699999999";</script>'
        ofertas, _ = vivo.ler_lite(None, date(2026, 11, 26), [])
        self.assertNotIn("VIV202699999999", [o["codigo_anatel"] for o in ofertas])


class OPrecoDepoisDaPromocao(unittest.TestCase):
    u"""coletar() inteiro: e ele que monta a oferta a partir do card."""

    def setUp(self):
        self.guarda = {k: getattr(vivo, k) for k in (
            "navegador", "trocar_praca", "indice_catalogo", "ler_vitrine",
            "ler_lite", "PAUSA", "PAGINAS_EXTRAS", "regulamento")}
        self.addCleanup(lambda: [setattr(vivo, k, v) for k, v in self.guarda.items()])
        vivo.navegador = lambda: (None, None)
        vivo.trocar_praca = lambda op, c, u: True
        vivo.indice_catalogo = lambda op: ({}, [])
        vivo.ler_lite = lambda op, hoje, avisos=None: ([], None)
        vivo.regulamento = lambda op, codigo: None
        vivo.PAUSA = 0
        vivo.PAGINAS_EXTRAS = ()

        def ler(op, produto, url=None, sufixo=None):
            if produto != "fibra":
                return [], None
            texto = (u"Vivo Fibra 600 Mega 1 ano de Disney+ Padrão com anúncios Valor "
                     u"R$ 100 /mês Após 1 ano: R$ 120/mês Consultar Fibra")
            return [{"plano": "Vivo Fibra", "destaque": "600 Mega", "preco": 100.0,
                     "codigo_anatel": None, "codigos_anatel": None, "texto": texto},
                    {"plano": "Vivo Fibra", "destaque": "700 Mega", "preco": 150.0,
                     "codigo_anatel": None, "codigos_anatel": None,
                     "texto": u"Vivo Fibra 700 Mega Valor R$ 150 /mês"}], None
        vivo.ler_vitrine = ler

    def test_o_disney_mais_acaba_em_12_meses(self):
        d = vivo.coletar("Sao Paulo", "SP", verbose=False)
        f = dict((o["degrau_mbps"], o) for o in d["ofertas"] if o["produto"] == "fibra")
        self.assertEqual(f[600]["preco_pos_promocao"], 120.0)
        self.assertEqual(f[600]["meses_desconto"], 12)
        self.assertIsNone(f[700].get("preco_pos_promocao"))


class OValeSaudeDoPre(unittest.TestCase):

    CARD = (u"+ 10 GB de bônus trazendo seu número para a Vivo Vale Saúde Farma: "
            u"desconto em farmácias Armazenamento extra com Google One")

    def test_o_card_do_pre_diz_farma(self):
        lista = apps.apps_do_texto(self.CARD)
        self.assertEqual(apps.rotulo(lista, self.CARD), u"Vale Saúde (Farma) + Google One")

    def test_sem_o_card_dizer_nao_ha_tier(self):
        self.assertEqual(apps.rotulo(["vale_saude"], u"Vivo Controle Saúde 50GB"), u"Vale Saúde")

    def test_o_app_continua_um_so(self):
        u"""O rotulo muda, a lista nao: a chave da serie sai da lista."""
        self.assertEqual(apps.apps_do_texto(self.CARD), ["vale_saude", "google_one"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
