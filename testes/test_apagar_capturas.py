# -*- coding: utf-8 -*-
u"""apagar_capturas.py: o filtro nunca sai incompleto, e o contado manda.

Um DELETE sem filtro no PostgREST apaga a tabela inteira. O script so
apaga o que a tabela declarada alcanca, e so quando o contado e o esperado.
"""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import apagar_capturas  # noqa: E402


class OFiltro(unittest.TestCase):

    def test_os_tres_campos_sempre(self):
        f = apagar_capturas.filtro(("TIM", "2026-11-27", "pos-pago", 156))
        self.assertIn("operadora=eq.TIM", f)
        self.assertIn("data_captura=eq.2026-11-27", f)
        self.assertIn("bruto-%3E%3Epagina=eq.pos-pago", f)

    def test_campo_vazio_e_erro_e_nao_filtro_largo(self):
        for c in (("", "2026-11-27", "pos-pago", 1), ("TIM", "", "pos-pago", 1),
                  ("TIM", "2026-11-27", "", 1)):
            with self.assertRaises(ValueError):
                apagar_capturas.filtro(c)


class OContadoManda(unittest.TestCase):

    def setUp(self):
        self.pedidos = []
        guarda = apagar_capturas._pedido

        def pedido(metodo, caminho, corpo=None):
            self.pedidos.append(metodo)
            if metodo == "GET":
                return self.linhas
            return [{"id": i} for i in range(len(self.linhas))]
        apagar_capturas._pedido = pedido
        self.addCleanup(lambda: setattr(apagar_capturas, "_pedido", guarda))

    def _linhas(self, n):
        return [{"id": i, "nome_oferta": "TIM Black", "preco_promocional": 129.99,
                 "franquia_anunciada_gb": 70, "praca": "Sao Paulo/SP"} for i in range(n)]

    def test_contado_diferente_do_esperado_nao_apaga(self):
        self.linhas = self._linhas(155)
        self.assertEqual(apagar_capturas.main(["--apagar"]), 1)
        self.assertNotIn("DELETE", self.pedidos)

    def test_sem_a_opcao_so_conta(self):
        self.linhas = self._linhas(156)
        self.assertEqual(apagar_capturas.main([]), 0)
        self.assertNotIn("DELETE", self.pedidos)


if __name__ == "__main__":
    unittest.main()
