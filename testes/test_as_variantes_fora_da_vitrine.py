# -*- coding: utf-8 -*-
u"""As variantes fora da vitrine principal (27/11/2026).

Os planos sem fidelidade da loja da Claro e as paginas "sem apps" da Vivo
e da Unifique entraram em 26/11, e no dia seguinte a grade do Controle
mostrou "Claro 15 GB a R$ 59,90" e "Vivo 10 GB a R$ 70" ao lado dos
planos de sempre - reais, mas lidos como erro. Escolha de quem le: a tela
mostra por padrao so a vitrine principal, e a opcao "Com os sem fidelidade
e sem apps" traz as variantes com o rotulo.

O reconhecimento e pelo sufixo que o coletor poe no nome, e roda de verdade
no node: e ali que mora o comportamento.
"""
import io
import json
import os
import re
import shutil
import subprocess
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
NODE = shutil.which("node")


def _molde():
    with io.open(os.path.join(RAIZ, "gerar_tela.py"), encoding="utf-8") as f:
        return f.read()


def _trecho(molde, inicio, fim):
    i = molde.index(inicio)
    return molde[i:molde.index(fim, i) + len(fim)]


@unittest.skipUnless(NODE, "sem node")
class OSufixoDaVariante(unittest.TestCase):

    def variantes(self, nomes):
        molde = _molde()
        js = (_trecho(molde, "const VARIANTE = ", ";\n")
              + _trecho(molde, "function variante(o){", "\n}\n")
              + "console.log(JSON.stringify(%s.map(n => variante({nome_oferta: n}))));"
              % json.dumps(nomes, ensure_ascii=False))
        r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, encoding="utf-8")
        if r.returncode:
            self.fail(r.stderr[-400:])
        return json.loads(r.stdout)

    def test_os_nomes_que_os_coletores_gravam(self):
        nomes = [u"Claro Controle sem fidelidade", u"Claro Controle sem fidelidade sem apps",
                 u"Claro Pós sem fidelidade", u"Vivo Controle sem apps", u"Vivo Pós Travel sem apps",
                 u"Vivo Total V 1 Giga sem apps", u"FIBRA ESSENCIAL sem apps",
                 u"Vivo Pré sem serviço digital"]
        self.assertEqual(self.variantes(nomes),
                         ["sem fidelidade", "sem fidelidade sem apps", "sem fidelidade",
                          "sem apps", "sem apps", "sem apps", "sem apps", u"sem serviço digital"])

    def test_o_padrao_corta_e_a_opcao_devolve(self):
        molde = _molde()
        js = ("let DADOS = [{nome_oferta: 'Claro Controle'}, {nome_oferta: 'Claro Controle sem fidelidade'},"
              " {nome_oferta: 'Vivo Controle sem apps'}, {nome_oferta: 'Vivo Controle'}];\n"
              + _trecho(molde, "const VARIANTE = ", ";\n")
              + _trecho(molde, "function variante(o){", "\n}\n")
              + _trecho(molde, "let DADOS_TODOS = null", ";\n")
              + _trecho(molde, "function recortarVariantes(){", "\n}\n")
              + "DADOS_TODOS = DADOS; recortarVariantes(); const a = DADOS.map(o => o.nome_oferta);"
              + "comVariantes = true; recortarVariantes(); const b = DADOS.length;"
              + "console.log(JSON.stringify([a, b]));")
        r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, encoding="utf-8")
        if r.returncode:
            self.fail(r.stderr[-400:])
        a, b = json.loads(r.stdout)
        self.assertEqual(a, ["Claro Controle", "Vivo Controle"])
        self.assertEqual(b, 4)

    def test_o_plano_da_vitrine_nao_e_variante(self):
        u"""Sufixo, e nao trecho: "Apps ilimitados" ou um app no meio do nome
        nao fazem variante."""
        nomes = [u"Claro Controle", u"Vivo Controle Amazon", u"TIM Black Família Plus",
                 u"Vivo Controle Apps ilimitados", u"Claro Pós Geforce", u"TIM Ultrafibra 1GIGA"]
        self.assertEqual(self.variantes(nomes), [""] * len(nomes))


class ATelaLigaECorta(unittest.TestCase):

    def setUp(self):
        self.molde = _molde()

    def test_o_corte_e_na_lista_inteira_e_o_filtro_sai_dela_toda(self):
        u"""derivar() guarda a lista inteira antes de cortar: os filtros de
        praca e de dia nao podem mudar quando a variante liga."""
        derivar = _trecho(self.molde, "function derivar(){", "\n}\n")
        self.assertLess(derivar.index("DADOS_TODOS = DADOS"), derivar.index("DIAS ="))
        self.assertLess(derivar.index("DIAS ="), derivar.index("recortarVariantes()"))

    def test_a_opcao_existe_e_liga(self):
        self.assertIn('<option value="variantes" data-t="e_variantes">', self.molde)
        escopo = _trecho(self.molde, "function escopo(v){", "\n}\n")
        self.assertIn('comVariantes = v === "variantes"', escopo)
        self.assertIn("recortarVariantes()", escopo)

    def test_a_grade_separa_a_variante_do_degrau(self):
        grade = _trecho(self.molde, "function porDegrau(dia){", "\n}\n")
        self.assertTrue(re.search(r'const k = o\.operadora \+ "\|" \+ e\.v \+ "\|" \+ vr;', grade))


if __name__ == "__main__":
    unittest.main()
