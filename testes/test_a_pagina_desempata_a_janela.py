# -*- coding: utf-8 -*-
u"""O 1 Giga da TIM: a pagina desempata a janela de comparacao.

ATE 24/11/2026 o "1GIGA" sem app da TIM ficava fora da serie em 19 das
20 pracas. A pagina de fibra publica o degrau a dois precos que valem na
mesma UF - R$ 129,99 e R$ 99,99 - e a regra de 03/11 era nao escolher.

O HTML diz qual vale: o de 99,99 e o card da pagina, e a faixa do topo
anuncia "Leve 1 GIGA por R$99,99" nas 28 UFs; o de 129,99 so existe
dentro da janela de comparacao escondida (coh-modal ... hidden), que
ficou com o preco de antes. Quando so UM dos precos aparece fora da
janela, vale esse. Se a pagina nao separa, o degrau continua fora.

Recorte real do Rio, 24/11/2026.
"""
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import tim                                     # noqa: E402

PAGINA = os.path.join(AQUI, "fixtures", "tim_fibra_rj_1giga_2026-11-24.html")


class APaginaDesempataAJanela(unittest.TestCase):

    def _ler(self, html, uf="RJ"):
        guarda = tim.buscar
        tim.buscar = lambda op, url, *a, **k: (200, html)
        try:
            return tim.ler_escada_de_fibra(None, "http://x", uf)
        finally:
            tim.buscar = guarda

    def setUp(self):
        with io.open(PAGINA, encoding="utf-8") as f:
            self.html = f.read()

    def test_o_recorte_tem_a_janela_e_os_dois_precos(self):
        self.assertIn('class="coh-modal ssa-component', self.html)
        self.assertIn("coh-modal-close-wrapper", self.html)
        self.assertIn("129,99", self.html)
        self.assertIn("99,99", self.html)

    def test_vale_o_preco_da_pagina(self):
        degraus, aviso = self._ler(self.html)
        giga = [o["preco_promocional"] for o in degraus
                if o["degrau_mbps"] == 1000 and not o.get("apps")]
        self.assertEqual(giga, [99.99])
        self.assertIsNone(aviso)

    def test_a_marca_interna_nao_vaza(self):
        degraus, _ = self._ler(self.html)
        for o in degraus:
            self.assertNotIn("_na_janela", o)

    def test_sem_a_janela_o_degrau_continua_fora(self):
        u"""Os dois precos na pagina: a pagina nao disse qual vale."""
        sem_janela = (self.html.replace('class="coh-modal ssa-component',
                                        'class="coh-container')
                      .replace("coh-modal-close-wrapper", "coh-container"))
        degraus, aviso = self._ler(sem_janela)
        self.assertFalse([o for o in degraus if o["degrau_mbps"] == 1000
                          and not o.get("apps")])
        self.assertIn("1000 Mbps a 99,99 e a 129,99", aviso)


if __name__ == "__main__":
    unittest.main(verbosity=2)
