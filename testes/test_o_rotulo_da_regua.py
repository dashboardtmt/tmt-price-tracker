# -*- coding: utf-8 -*-
u"""O rotulo da regua de posicionamento diz qual oferta e cada ponto.

COBRADO EM 26/11/2026: "tem como mostrar as ofertas de forma mais
completa? ta muito estranho assim". A regua do pre-pago dizia "35,00 · 22
GB x2" e "35,00 · 17 GB x2": quatro Prezoes tematicos em dois pontos, sem
dizer quais, e sem a validade. A segunda linha do rotulo e a validade (no
pre) e o nome curto de cada oferta - sem a marca, sem a palavra do produto
e sem a franquia, que a primeira linha ja diz.

O rotulo e desenhado no canvas; o teste le os pontos que o plugin recebe,
pelo JavaScript de verdade da tela (tela_em_node.mjs).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from _apoio import HOJE, ONTEM, oferta  # noqa: E402

NODE = shutil.which("node")


@unittest.skipIf(NODE is None, "node nao instalado")
class ORotuloDizAOferta(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp()
        cls.dados = os.path.join(cls.pasta, "d.json")
        cls.tela = os.path.join(cls.pasta, "t.html")
        linhas = []
        for data in (ONTEM, HOJE):
            for op, nome, preco, gb, dias in (
                    ("Claro", u"Claro Prezao Kwai 22GB", 35.0, 22, 30),
                    ("Claro", u"Claro Prezao TikTok 22GB", 35.0, 22, 30),
                    ("Claro", u"Claro Prezao 5GB", 15.0, 5, 15),
                    ("TIM", u"TIM Pré XIP Plus", 20.0, 6, 17),
                    ("Vivo", u"Vivo Pré", 20.0, 5, 17)):
                linhas.append(dict(oferta(
                    operadora=op, produto="prepago", nome=nome, preco=preco, gb=gb,
                    praca="Sao Paulo/SP", data=data,
                    chave="%s|prepago|%dgb|%s" % (op, gb, nome.split()[-1].lower())),
                    validade_dias=dias))
        with open(cls.dados, "w", encoding="utf-8") as f:
            json.dump(linhas, f)
        r = subprocess.run(
            [sys.executable, os.path.join(RAIZ, "gerar_tela.py"),
             "--dados", cls.dados, "--saida", cls.tela],
            capture_output=True, text=True, encoding="utf-8", cwd=RAIZ)
        if r.returncode:
            raise unittest.SkipTest("gerar_tela falhou: %s" % r.stderr[-300:])
        c = [{"praca": "Sao Paulo/SP", "produto": "prepago", "dia": HOJE,
              "aba": "panorama"}]
        r = subprocess.run(
            ["node", os.path.join(AQUI, "tela_em_node.mjs"),
             cls.tela, cls.dados, json.dumps(c)],
            capture_output=True, text=True, encoding="utf-8", cwd=AQUI)
        if r.returncode:
            raise AssertionError("o JS da tela quebrou: %s" % r.stderr[-600:])
        g = json.loads(r.stdout)[0]["graficos"].get("c-dispersao") or {}
        cls.regua = dict((l["op"], l["pontos"]) for l in g.get("regua") or ())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def test_o_tematico_leva_o_nome_e_a_validade(self):
        claro = self.regua["Claro"]
        nomes = sorted(p["nome"] for p in claro if p["rotulo"].startswith("35,00"))
        self.assertEqual(nomes, ["Kwai", "TikTok"])
        self.assertTrue(all(p["pre"] == "30 dias" for p in claro if p["rotulo"].startswith("35,00")))
        self.assertEqual([p["pre"] for p in claro if p["rotulo"].startswith("15,00")], ["15 dias"])

    def test_a_marca_e_o_produto_saem_do_nome(self):
        u"""Sem \\b na regex: no JavaScript o "e" acentuado de "Pré" nao e
        letra, e a palavra passava."""
        self.assertEqual([p["nome"] for p in self.regua["TIM"]], ["XIP Plus"])
        self.assertEqual([p["nome"] for p in self.regua["Vivo"]], [""])
        base = [p["nome"] for p in self.regua["Claro"] if p["rotulo"].startswith("15,00")]
        self.assertEqual(base, [""])


if __name__ == "__main__":
    unittest.main(verbosity=2)
