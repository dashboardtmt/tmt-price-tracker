# -*- coding: utf-8 -*-
u"""Toda mutacao do provador aponta para um trecho que existe.

DE 24 A 25/11/2026 A CAIXA DE QUEM LE ENCHEU DE "Run failed: Testes". A
suite estava verde; quem falhava era o provador, parte 7 de 8, sempre
pelo mesmo motivo: a mutacao B1 apontava para uma linha que o filtro 7
da saida tinha reescrito ("NAO APLIQUEI - o trecho mudou"). Sete commits
seguidos mandaram o mesmo e-mail, e daqui nao se via nada: a suite local
passava, e o provador so roda inteiro no Actions.

Este teste roda na suite comum, em milissegundos: ancora velha quebra
aqui, antes do push, e nao no e-mail.
"""
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import provar_a_suite as P                                    # noqa: E402


# NAO RODA DENTRO DO PROVADOR. Ele aplica a mutacao e roda a suite: a
# ancora da mutacao aplicada some do arquivo, e este teste "pegaria" toda
# mutacao - inclusive o controle. Em ce9440b foi exatamente isso.
@unittest.skipIf(os.environ.get("PROVADOR_ATIVO"),
                 "dentro do provador a ancora da mutacao aplicada some")
class AsAncorasDoProvador(unittest.TestCase):

    def test_toda_mutacao_encontra_o_seu_trecho(self):
        velhas = []
        cache = {}
        for m in P.MUTACOES:
            if m.arquivo not in cache:
                with io.open(os.path.join(P.BASE, m.arquivo), encoding="utf-8") as f:
                    cache[m.arquivo] = f.read()
            if m.de not in cache[m.arquivo]:
                velhas.append("%s (%s)" % (m.conta, m.arquivo))
        self.assertEqual(velhas, [], "mutacoes com ancora velha - reancore "
                         "antes do push, senao o provador do Actions falha")

    def test_o_teste_mede_algo(self):
        self.assertGreater(len(P.MUTACOES), 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
