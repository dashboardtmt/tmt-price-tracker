# -*- coding: utf-8 -*-
u"""coleta_avulsa.py: uma operadora, um produto, so as ofertas pedidas.

Grava so o que casa com produto E prefixo do nome; sem --gravar nao grava
nada; nao registra rodada na tabela de coletas.
"""
import os
import sys
import types
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import coleta_avulsa as C                                     # noqa: E402
import robo                                                    # noqa: E402
from coletores import armazenamento                           # noqa: E402


def oferta(nome, produto="prepago", praca="Sao Paulo/SP"):
    return {"operadora": "Claro", "produto": produto, "praca": praca,
            "nome_oferta": nome, "preco_promocional": 35.0,
            "capturado_em": "2026-11-25T17:00:00-03:00"}


class AColetaAvulsa(unittest.TestCase):

    def setUp(self):
        falso = types.SimpleNamespace(coletar=lambda cidade, uf, verbose=False: {
            "ofertas": [oferta("Claro Prezao Kwai 22GB", praca="%s/%s" % (cidade, uf)),
                        oferta("Claro Prezao 20GB", praca="%s/%s" % (cidade, uf)),
                        oferta("Claro Controle 50GB", "controle", "%s/%s" % (cidade, uf))],
            "avisos": []})
        self.gravadas, self.registros = [], []
        guarda = (dict(robo.COLETORES), robo.pracas_da_operadora,
                  armazenamento.gravar_capturas, armazenamento.registrar_coleta)
        robo.COLETORES["Falsa"] = falso
        robo.pracas_da_operadora = lambda nome, modulo, uma=None: [
            {"cidade": "Sao Paulo", "uf": "SP"}, {"cidade": "Recife", "uf": "PE"}]
        armazenamento.gravar_capturas = lambda o: (self.gravadas.extend(o), (len(o), None))[1]
        armazenamento.registrar_coleta = lambda r: (self.registros.append(r), (True, None))[1]

        def volta():
            robo.COLETORES.clear()
            robo.COLETORES.update(guarda[0])
            (robo.pracas_da_operadora, armazenamento.gravar_capturas,
             armazenamento.registrar_coleta) = guarda[1:]
        self.addCleanup(volta)

    def test_grava_so_o_produto_e_o_prefixo(self):
        self.assertEqual(C.main(["Falsa", "prepago", "Claro Prezao Kwai", "--gravar"]), 0)
        self.assertEqual(sorted(o["praca"] for o in self.gravadas), ["Recife/PE", "Sao Paulo/SP"])
        self.assertTrue(all(o["nome_oferta"] == "Claro Prezao Kwai 22GB" for o in self.gravadas))

    def test_sem_gravar_nao_grava(self):
        self.assertEqual(C.main(["Falsa", "prepago", "Claro Prezao Kwai"]), 0)
        self.assertEqual(self.gravadas, [])

    def test_nao_registra_rodada(self):
        C.main(["Falsa", "prepago", "Claro Prezao Kwai", "--gravar"])
        self.assertEqual(self.registros, [])

    def test_nada_casou_para_alto(self):
        self.assertEqual(C.main(["Falsa", "prepago", "Claro Prezao Inexistente", "--gravar"]), 1)
        self.assertEqual(self.gravadas, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
