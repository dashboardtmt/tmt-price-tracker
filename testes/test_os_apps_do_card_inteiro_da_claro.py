# -*- coding: utf-8 -*-
u"""Os apps do controle e do pos da Claro saem do card inteiro.

Auditoria contra o site de 26/11/2026: o card do pos mostra "Apps exclusivos
para voce: Skeelo +2", e o Skeelo faltava nos cinco planos de pos e no
Controle Geforce. Os apps saiam da composicao - os primeiros 400 caracteres
de um texto ja cortado em 12 mil de HTML -, e o Skeelo fica depois dos dois
cortes. O card vai so ate o seguinte; e ele inteiro que o cliente le.
"""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import claro  # noqa: E402

# um card como o do hub: o preco cedo, o seletor de linhas enchendo o HTML,
# e o app exclusivo bem depois dos 12 mil caracteres
ENCHIMENTO = '<div class="seletor-linhas" data-x="%s"></div>' % ("x" * 13000)
CARD = ('<div class="card-planos-custom" id="plan-23817"><h3>Claro Pós 80GB</h3>'
        '<p>80GB</p><p>R$ 124,90 /mês</p><p>WhatsApp ilimitado</p>' + ENCHIMENTO +
        '<p>Apps exclusivos para você</p><img alt="Skeelo"><span>Skeelo</span></div>')
PAGINA = "<html>" + CARD + '<div class="card-planos-fim"></div></html>'


class OsAppsDoCardInteiro(unittest.TestCase):

    def setUp(self):
        guarda = (claro.buscar, claro.PAUSA, claro.codigo_cidade)
        claro.buscar = lambda op, url, *a, **k: (200, PAGINA) if url == claro.PAGINAS["movel"] else (404, "")
        claro.PAUSA = 0
        claro.codigo_cidade = lambda op, c, u: ("x", "123", None)

        def volta():
            claro.buscar, claro.PAUSA, claro.codigo_cidade = guarda
        self.addCleanup(volta)

    def test_o_skeelo_depois_do_corte_entra(self):
        self.assertNotIn("Skeelo", CARD[:12000])
        d = claro.coletar("Sao Paulo", "SP", verbose=False)
        pos = [o for o in d["ofertas"] if o["produto"] == "movel"]
        self.assertTrue(pos)
        self.assertIn("skeelo", pos[0]["apps"])

    def test_o_texto_dos_apps_nao_e_gravado(self):
        d = claro.coletar("Sao Paulo", "SP", verbose=False)
        self.assertFalse([o for o in d["ofertas"] if "texto_apps" in o])


if __name__ == "__main__":
    unittest.main()
