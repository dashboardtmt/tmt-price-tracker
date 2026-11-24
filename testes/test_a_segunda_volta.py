# -*- coding: utf-8 -*-
u"""A praca que levou recusa e refeita uma vez no fim da rodada.

Em 21 e 23/11/2026 a Vivo respondeu 403 em algumas pracas e as outras
passaram minutos depois. coletores/rede.py nao insiste em 4xx na hora -
repetir a recusa alonga o bloqueio -, a rodada fechava "20 de 20" e o
produto da praca se perdia no dia: 157 ofertas em 23/11.

A segunda volta e UMA tentativa, so das pracas recusadas, no fim da
rodada e depois de uma pausa. Fica a segunda se vier com menos recusas
e pelo menos as mesmas ofertas.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402

SP = {"cidade": "Sao Paulo", "uf": "SP"}
RJ = {"cidade": "Rio de Janeiro", "uf": "RJ"}


def oferta(nome, praca):
    return {"operadora": "Vivo", "nome_oferta": nome, "praca": praca}


class Fonte(object):
    u"""Um coletor de mentira: cada chamada de cada praca devolve o
    proximo resultado da fila daquela praca."""

    def __init__(self, filas):
        self.filas = filas
        self.chamadas = []

    def coletar(self, cidade, uf, verbose=False):
        praca = "%s/%s" % (cidade, uf)
        self.chamadas.append(praca)
        return self.filas[praca].pop(0)


INTEIRA = {"ofertas": [oferta("A", "Sao Paulo/SP"), oferta("B", "Sao Paulo/SP")],
           "avisos": []}
RECUSADA = {"ofertas": [oferta("A", "Sao Paulo/SP")],
            "avisos": ["vitrine combo: HTTP 403", "lite: HTTP 403"]}
RJ_OK = {"ofertas": [oferta("A", "Rio de Janeiro/RJ")], "avisos": []}


class ASegundaVolta(unittest.TestCase):

    def setUp(self):
        guarda = robo.PAUSA_SEGUNDA_VOLTA
        robo.PAUSA_SEGUNDA_VOLTA = 0
        self.addCleanup(setattr, robo, "PAUSA_SEGUNDA_VOLTA", guarda)

    def _rodar(self, filas):
        fonte = Fonte(filas)
        ofertas, registro, _ = robo.coletar_operadora(
            "Vivo", fonte, [SP, RJ], simular=True, verbose=False)
        return fonte, ofertas, registro

    def test_a_recusada_e_refeita_e_a_segunda_fica(self):
        fonte, ofertas, registro = self._rodar(
            {"Sao Paulo/SP": [dict(RECUSADA), dict(INTEIRA)],
             "Rio de Janeiro/RJ": [dict(RJ_OK)]})
        self.assertEqual(fonte.chamadas, ["Sao Paulo/SP", "Rio de Janeiro/RJ",
                                          "Sao Paulo/SP"])
        self.assertEqual(sorted(o["nome_oferta"] for o in ofertas
                                if o["praca"] == "Sao Paulo/SP"), ["A", "B"])
        self.assertFalse([a for a in registro["avisos"] if "HTTP 403" in a])
        self.assertTrue([a for a in registro["avisos"]
                         if "segunda volta: 2 recusa(s) na primeira, 0" in a])

    def test_sem_recusa_nao_ha_segunda_volta(self):
        fonte, _o, _r = self._rodar({"Sao Paulo/SP": [dict(INTEIRA)],
                                     "Rio de Janeiro/RJ": [dict(RJ_OK)]})
        self.assertEqual(fonte.chamadas, ["Sao Paulo/SP", "Rio de Janeiro/RJ"])

    def test_recusada_de_novo_fica_a_primeira_e_diz(self):
        _f, ofertas, registro = self._rodar(
            {"Sao Paulo/SP": [dict(RECUSADA), dict(RECUSADA)],
             "Rio de Janeiro/RJ": [dict(RJ_OK)]})
        self.assertEqual(len([o for o in ofertas
                              if o["praca"] == "Sao Paulo/SP"]), 1)
        self.assertTrue([a for a in registro["avisos"]
                         if "segunda volta nao melhorou" in a])
        self.assertTrue([a for a in registro["avisos"] if "HTTP 403" in a],
                        "a recusa da primeira continua dita")

    def test_segunda_com_menos_ofertas_nao_substitui(self):
        u"""Menos recusa e menos oferta nao e melhor: fica a primeira."""
        vazia = {"ofertas": [], "avisos": []}
        _f, ofertas, _r = self._rodar(
            {"Sao Paulo/SP": [dict(RECUSADA), vazia],
             "Rio de Janeiro/RJ": [dict(RJ_OK)]})
        self.assertEqual(len([o for o in ofertas
                              if o["praca"] == "Sao Paulo/SP"]), 1)

    def test_o_404_nao_e_recusa(self):
        u"""404 e ausencia real (a Unifique nao atende a cidade): refazer
        nao muda nada."""
        self.assertEqual(robo._recusas({"avisos": ["catalogo x: HTTP 404"]}), 0)
        self.assertEqual(robo._recusas(
            {"avisos": ["regulamento falhou: HTTP Error 403: Forbidden"]}), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
