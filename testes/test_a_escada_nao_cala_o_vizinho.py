# -*- coding: utf-8 -*-
u"""A escada que desliza nao cala a oferta de outro nome.

O QUE PASSOU CALADO EM 13/11/2026. A Claro deslizou a escada do Controle
- R$ 59,90 foi de 45 para 50 GB - e, no mesmo dia, o Claro Controle
Geforce foi de R$ 99,90 com 35 GB para R$ 69,90 com 55 GB, em 17 pracas:
corte de 30% com 57% mais franquia. A mensagem falou da escada e nao
disse uma palavra sobre o Geforce.

A supressao da escada existe por um motivo real: com os degraus andando,
parear por nome casa o "Claro Controle" de um degrau com o "Claro
Controle" de outro e inventa reajuste. Mas ela valia para o PRODUTO
inteiro, e calava tambem a oferta de outro nome que mudou por conta
propria. Medido nos 48 dias: a supressao por produto calou uma
remodelada so - esta, e verdadeira. Agora vale para o nome que deslizou.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _apoio import HOJE, ONTEM, dados, montar, oferta, sem_declaracao  # noqa: E402

PRACAS = ["Sao Paulo/SP", "Rio de Janeiro/RJ", "Curitiba/PR"]


def claro(nome, preco, gb, data):
    return [oferta(operadora="Claro", produto="controle", nome=nome,
                   preco=preco, gb=gb, praca=p, data=data,
                   chave="Claro|controle|%dgb|com_apps" % gb)
            for p in PRACAS]


def dia_13_11():
    ontem = (claro("Claro Controle", 59.90, 45, ONTEM)
             + claro("Claro Controle", 69.90, 50, ONTEM)
             + claro("Claro Controle Geforce", 99.90, 35, ONTEM))
    hoje = (claro("Claro Controle", 59.90, 50, HOJE)
            + claro("Claro Controle", 69.90, 55, HOJE)
            + claro("Claro Controle Geforce", 69.90, 55, HOJE))
    return ontem, hoje


class AEscadaNaoCalaOVizinho(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def test_o_geforce_sai(self):
        t = montar(*dia_13_11())
        self.assertIn(u"Claro Controle Geforce", t)
        self.assertIn(u"99,90 → 69,90", t)
        self.assertIn(u"35 → 55 GB", t)

    def test_a_escada_continua_saindo(self):
        u"""O movimento da escada segue no bloco dela."""
        self.assertIn(u"59,90: 45 → 50 GB", montar(*dia_13_11()))

    def test_o_nome_que_deslizou_continua_calado(self):
        u"""A razao de a supressao existir: o "Claro Controle" de R$ 59,90
        (45 GB ontem) casaria com o de R$ 69,90 (55 GB hoje) e sairia
        como reajuste de +17% que nao houve."""
        d = dados(*dia_13_11())
        nomes = [(r["atual"].get("nome_oferta") or "")
                 for r in d.get("remodeladas") or []]
        self.assertEqual(nomes, [u"Claro Controle Geforce"])
        self.assertNotIn("+17%", montar(*dia_13_11()))


if __name__ == "__main__":
    unittest.main()
