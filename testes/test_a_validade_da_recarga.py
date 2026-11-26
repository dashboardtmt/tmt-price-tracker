# -*- coding: utf-8 -*-
u"""A validade da recarga do pre-pago, nas tres operadoras.

Ate 24/11/2026 a Claro entrava so com a recarga de 30 dias e Vivo e TIM
com todas - a entrada delas parecia R$ 20 contra R$ 30 da Claro. Escolha
de quem le: "Todas, com a validade". Cada recarga leva os dias que vale,
e a tela os mostra ao lado da franquia. Frases copiadas das paginas.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import tim, vivo                               # noqa: E402
from _apoio import HOJE, ONTEM, oferta                        # noqa: E402

NODE = shutil.which("node")
RAIZ = os.path.dirname(AQUI)


class ATim(unittest.TestCase):

    def test_a_frase_do_preco_da_a_validade(self):
        self.assertEqual(tim._validade(u"R$20 por 17 dias Sua recarga no app"), 17)
        self.assertEqual(tim._validade(u"R$ 30 por 30 dias"), 30)
        self.assertIsNone(tim._validade(u"Por apenas R$129,99/mês"))

    def test_o_pos_nao_ganha_validade(self):
        u"""O coletar so guarda a validade no pre-pago."""
        pagina = ('<script data-drupal-selector="drupal-settings-json">'
                  + json.dumps({"ofertas": [
                      {"field_subtitle": [{"value": u"TIM Pré XIP Plus"}],
                       "field_titulo": [{"value": "6GB"}],
                       "field_information_text": [{"value": "6GB da oferta"}],
                       "field_preco_card_oferta": [{"value": "20,00"}],
                       "field_preco_principal_7_1_3": [{"value": "<p>R$20 por 17 dias</p>"}]},
                      {"field_subtitle": [{"value": "TIM Black"}],
                       "field_titulo": [{"value": "70GB"}],
                       "field_information_text": [{"value": "70GB"}],
                       "field_preco_card_oferta": [{"value": "129,99"}],
                       "field_preco_principal_7_1_3": [{"value": "<p>por 30 dias de bonus</p>"}]}]})
                  + "</script>")
        guarda = (tim.buscar, tim.navegador, tim.PAUSA)
        tim.buscar = lambda op, url, *a, **k: (
            (200, pagina) if url.endswith("/planos/pre-pago") else (200, ""))
        tim.navegador = lambda: None
        tim.PAUSA = 0

        def volta():
            tim.buscar, tim.navegador, tim.PAUSA = guarda
        self.addCleanup(volta)
        r = tim.coletar("Sao Paulo", "SP", verbose=False)
        por = dict((o["nome_oferta"], o.get("validade_dias")) for o in r["ofertas"])
        self.assertEqual(por[u"TIM Pré XIP Plus"], 17)
        self.assertIsNone(por["TIM Black"])


class AVivo(unittest.TestCase):

    def setUp(self):
        self.guarda = {k: getattr(vivo, k) for k in (
            "navegador", "trocar_praca", "indice_catalogo", "ler_vitrine",
            "ler_lite", "PAUSA", "PAGINAS_EXTRAS")}
        self.addCleanup(lambda: [setattr(vivo, k, v) for k, v in self.guarda.items()])
        vivo.navegador = lambda: (None, None)
        vivo.trocar_praca = lambda op, c, u: True
        vivo.indice_catalogo = lambda op: ({}, [])
        vivo.ler_lite = lambda op, hoje, avisos=None: ([], None)
        vivo.PAUSA = 0
        # as paginas extras da vitrine (26/11/2026) ficam fora deste teste
        vivo.PAGINAS_EXTRAS = ()
        cards = {
            "prepago": [{"plano": u"Vivo Pré", "destaque": "25 GB", "preco": 35.0,
                         "codigo_anatel": None,
                         "texto": u"Vivo Pré 25 GB 25 GB para navegar Nas recargas "
                                  u"de Valor R$ 35 Por 30 dias Mais informações"},
                        {"plano": u"Vivo Pré", "destaque": "5 GB", "preco": 20.0,
                         "codigo_anatel": None,
                         "texto": u"Vivo Pré 5 GB Nas recargas de Valor R$ 20 Por 17 "
                                  u"dias Mais informações"}],
            "controle": [{"plano": "Vivo Controle", "destaque": "50 GB", "preco": 59.0,
                          "codigo_anatel": None,
                          "texto": u"Vivo Controle 50 GB bonus por 30 dias"}],
        }
        vivo.ler_vitrine = lambda op, p, *a: (cards.get(p, []), None)

    def test_a_validade_do_card_do_pre(self):
        r = vivo.coletar("Sao Paulo", "SP", verbose=False)
        pre = sorted((o["preco_promocional"], o["validade_dias"]) for o in r["ofertas"]
                     if o["produto"] == "prepago")
        self.assertEqual(pre, [(20.0, 17), (35.0, 30)])

    def test_o_controle_nao_ganha_validade(self):
        r = vivo.coletar("Sao Paulo", "SP", verbose=False)
        ctl = [o for o in r["ofertas"] if o["produto"] == "controle"]
        self.assertTrue(ctl)
        self.assertIsNone(ctl[0]["validade_dias"])


@unittest.skipIf(NODE is None, "node nao instalado")
class ATelaMostraOsDias(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp()
        cls.dados = os.path.join(cls.pasta, "d.json")
        cls.tela = os.path.join(cls.pasta, "t.html")
        linhas = []
        for data in (ONTEM, HOJE):
            linhas += [
                dict(oferta(operadora="TIM", produto="prepago",
                            nome=u"TIM Pré XIP Plus", preco=20.0, gb=6,
                            praca="Sao Paulo/SP", data=data,
                            chave="TIM|prepago|6gb|simples"), validade_dias=17),
                dict(oferta(operadora="TIM", produto="prepago",
                            nome=u"TIM Pré XIP Plus 16GB", preco=30.0, gb=16,
                            praca="Sao Paulo/SP", data=data,
                            chave="TIM|prepago|16gb|simples")),
            ]
        with open(cls.dados, "w", encoding="utf-8") as f:
            json.dump(linhas, f)
        r = subprocess.run(
            [sys.executable, os.path.join(RAIZ, "gerar_tela.py"),
             "--dados", cls.dados, "--saida", cls.tela],
            capture_output=True, text=True, encoding="utf-8", cwd=RAIZ)
        if r.returncode:
            raise unittest.SkipTest("gerar_tela falhou: %s" % r.stderr[-300:])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def test_a_entrega_diz_os_dias(self):
        c = [{"praca": "Sao Paulo/SP", "produto": "prepago", "dia": HOJE,
              "player": "TIM"}]
        r = subprocess.run(
            ["node", os.path.join(AQUI, "tela_em_node.mjs"),
             self.tela, self.dados, json.dumps(c)],
            capture_output=True, text=True, encoding="utf-8", cwd=AQUI)
        if r.returncode:
            self.fail("o JS da tela quebrou: %s" % r.stderr[-600:])
        html = json.loads(r.stdout)[0]["t-player"]
        linha = [l for l in html.split("<tr") if "TIM Pré XIP Plus</td>" in l][0]
        self.assertIn(u"· 17 dias", linha)
        sem = [l for l in html.split("<tr") if "16GB</td>" in l][0]
        self.assertNotIn("dias", sem)


if __name__ == "__main__":
    unittest.main(verbosity=2)
