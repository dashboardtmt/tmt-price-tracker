# -*- coding: utf-8 -*-
u"""A franquia contratual quando a escada desliza.

O QUE SAIU EM 28/10 E 05/11/2026. A mensagem disse, nas 20 pracas:

  Controle - Vivo Controle
    a franquia contratual foi de 20 para 15 GB (-25%)

e, uma semana depois, a mesma frase sobre o Claro Controle. Nenhum
plano mexeu no contrato. O que houve foi a escada deslizando: cada
preco parado ganhou 5 GB de bonus - o Vivo de R$ 59 foi de 45 para 50
GB, o de R$ 75 de 50 para 55 -, e o contrato de cada um ficou onde
estava, 15 e 20.

A identidade da oferta carrega a chave, e a chave carrega o degrau
anunciado. "Vivo Controle de 50 GB" era o plano de R$ 75 ontem e o de
R$ 59 hoje: o detector comparou o contrato de um com o do outro e
publicou um corte de 25% no dia em que a operadora deu bonus em todos
os planos.

MEDIDO NOS 42 DIAS PUBLICADOS: 6 eventos contratuais, 2 com o preco do
par mexendo - estes dois, os dois falsos. A assinatura do deslize e o
preco de ontem continuar na vitrine hoje, no mesmo nome e na mesma
praca: o plano nao foi a lugar nenhum, so ganhou degrau.

O QUE ESTE ARQUIVO PRENDE: a escada que desliza nao vira corte de
contrato, e o plano que muda preco e contrato de verdade continua
saindo - esse caso mora em test_o_app_e_o_contrato.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _apoio import HOJE, ONTEM, dados, montar, oferta, sem_declaracao  # noqa: E402


def vivo(preco, gb, contrato, data):
    return oferta(operadora="Vivo", produto="controle", nome="Vivo Controle",
                  preco=preco, gb=gb, data=data, contratual=contrato,
                  chave="Vivo|controle|%dgb|com_apps" % gb)


class AEscadaQueDeslizaNaoCortaOContrato(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)
        # 28/10/2026, Sao Paulo: os dois planos de mesmo nome
        self.ontem = [vivo(59.0, 45, 15, ONTEM), vivo(75.0, 50, 20, ONTEM)]
        self.hoje = [vivo(59.0, 50, 15, HOJE), vivo(75.0, 55, 20, HOJE)]

    def test_nao_sai_corte_de_contrato(self):
        t = montar(self.ontem, self.hoje)
        self.assertNotIn("franquia contratual", t)
        self.assertNotIn("-25%", t)

    def test_o_evento_nao_nasce(self):
        u"""Nao basta a frase sumir: o evento nao pode existir, senao o
        PDF - que le a mesma lista - publica o corte na tabela."""
        d = dados(self.ontem, self.hoje)
        self.assertEqual(d.get("contratuais") or [], [])

    def test_a_escada_continua_dizendo_o_que_houve(self):
        u"""O movimento real - mais franquia pelo mesmo preco - segue no
        bloco de grade. A guarda tira o falso, nao o fato."""
        t = montar(self.ontem, self.hoje)
        self.assertIn(u"59,00: 45 → 50 GB", t)

    def test_contrato_que_muda_de_verdade_na_escada_parada_sai(self):
        u"""O controle: escada parada, o plano de R$ 59 troca 15 de
        contrato por 10. Com o preco igual a guarda nem e consultada -
        e o evento tem de sair."""
        hoje = [vivo(59.0, 45, 10, HOJE), vivo(75.0, 50, 20, HOJE)]
        t = montar(self.ontem, hoje)
        self.assertIn("a franquia contratual foi de 15 para 10 GB", t)


if __name__ == "__main__":
    unittest.main()
