# -*- coding: utf-8 -*-
u"""corrigir_nomes.py mexe na base de producao. Este arquivo prende as
tres travas dele: o filtro inteiro em todo pedido, nada gravado sem
--aplicar, e parada alta quando o que mudou nao e o que foi contado."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import corrigir_nomes as C                                     # noqa: E402


class OFiltroEInteiro(unittest.TestCase):

    def test_todo_pedido_leva_os_seis_campos(self):
        for c in C.CORRECOES:
            f = C.filtro(c)
            for campo in ("operadora=eq.", "data_captura=gte.",
                          "data_captura=lte.", "nome_oferta=eq.",
                          "degrau_mbps=eq.", "preco_promocional=eq."):
                self.assertIn(campo, f)

    def test_cada_linha_e_uma_oferta(self):
        chaves = [(c[0], c[3], c[4], c[5]) for c in C.CORRECOES]
        self.assertEqual(len(chaves), len(set(chaves)))

    def test_o_nome_certo_nao_e_faixa(self):
        for c in C.CORRECOES:
            for pedaco in ("PAGAMENTO", "CONTINUA ONLINE"):
                self.assertNotIn(pedaco, c[6])


class AsTravas(unittest.TestCase):

    def _banco(self, contagem, alteradas):
        pedidos = []

        def pedido(metodo, caminho, corpo=None):
            pedidos.append(metodo)
            if metodo == "PATCH":
                return [{"id": i} for i in range(alteradas)]
            n = contagem.pop(0) if contagem else 0
            return [{"id": i} for i in range(n)]
        guarda = C._pedido
        C._pedido = pedido
        self.addCleanup(setattr, C, "_pedido", guarda)
        return pedidos

    def test_sem_aplicar_nada_e_gravado(self):
        pedidos = self._banco([3] * len(C.CORRECOES), 3)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(C.main([]), 0)
        self.assertNotIn("PATCH", pedidos)

    def test_contagem_diferente_para_alto(self):
        self._banco([3] * len(C.CORRECOES), 2)
        saida = io.StringIO()
        with redirect_stdout(saida):
            self.assertEqual(C.main(["--aplicar"]), 1)
        self.assertIn("PAREI", saida.getvalue())

    def test_sobrou_nome_errado_para_alto(self):
        # conta 3 em cada, altera 3, e na conferencia ainda acha 1
        self._banco([3] * len(C.CORRECOES) + [1], 3)
        saida = io.StringIO()
        with redirect_stdout(saida):
            self.assertEqual(C.main(["--aplicar"]), 1)
        self.assertIn("ainda ha", saida.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
