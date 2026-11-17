# -*- coding: utf-8 -*-
u"""O provador dividido em partes nao pode perder mutacao.

Desde 17/11/2026 o provador roda em oito jobs paralelos no CI, cada um
com uma em cada oito mutacoes. Inteiro, ele estourava o teto de 35
minutos e era cancelado sem relatar nada - e tres mutacoes ja tinham
deixado de ser pegas sem ninguem saber.

A divisao e o novo ponto de silencio: parte que pulasse um indice, ou
workflow pedindo 7 partes a um provador que divide em 8, deixaria
mutacao sem ser medida e o CI verde. Este arquivo prende as duas pontas.
"""
import io
import os
import re
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import provar_a_suite as P                                     # noqa: E402

WORKFLOW = os.path.join(os.path.dirname(AQUI), ".github", "workflows",
                        "testes.yml")


class AsPartesCobremTudo(unittest.TestCase):

    def test_a_uniao_e_a_lista_inteira_sem_repetir(self):
        for n in (1, 2, 3, 8):
            with self.subTest(partes=n):
                vistas = []
                for k in range(1, n + 1):
                    vistas += [id(m) for m in P.parte(P.MUTACOES, k, n)]
                self.assertEqual(sorted(vistas),
                                 sorted(id(m) for m in P.MUTACOES))

    def test_as_partes_saem_do_mesmo_tamanho(self):
        tamanhos = [len(P.parte(P.MUTACOES, k, 8)) for k in range(1, 9)]
        self.assertLessEqual(max(tamanhos) - min(tamanhos), 1)

    def test_parte_que_nao_existe_falha_alto(self):
        with self.assertRaises(ValueError):
            P.parte(P.MUTACOES, 9, 8)

    def test_o_argumento(self):
        self.assertEqual(P._parte_pedida(["--parte", "3/8"]), (3, 8))
        self.assertEqual(P._parte_pedida(["--parte=2/8"]), (2, 8))
        self.assertEqual(P._parte_pedida([]), (1, 1))


class OWorkflowPedeAsPartesQueExistem(unittest.TestCase):
    u"""A matriz e o divisor do comando tem de ser o mesmo numero."""

    def test_matriz_e_divisor_concordam(self):
        with io.open(WORKFLOW, encoding="utf-8") as f:
            t = f.read()
        matriz = re.search(r"parte:\s*\[([\d,\s]+)\]", t)
        comando = re.search(r"--parte \$\{\{ matrix\.parte \}\}/(\d+)", t)
        self.assertTrue(matriz and comando, "o provador saiu da matriz")
        partes = [int(x) for x in matriz.group(1).split(",")]
        n = int(comando.group(1))
        self.assertEqual(partes, list(range(1, n + 1)))


if __name__ == "__main__":
    unittest.main()
