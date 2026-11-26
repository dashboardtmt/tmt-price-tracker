# -*- coding: utf-8 -*-
u"""A Starlink: os planos de viagem, o contrato do kit e o terabyte decimal.

Achados da auditoria contra o site de 26/11/2026:
  - os planos de viagem (Roam: 100 GB a R$ 339 e ilimitado a R$ 619) sao os
    unicos precos de pessoa fisica que a Starlink mostra sem endereco, e a
    API os serve no codigo 8 - o coletor lia so o 1 e o 6;
  - o kit de R$ 49 diz "Contrato de 12 meses obrigatorio", e a fidelidade
    saia vazia - vazio e "sem fidelidade";
  - 1 TB saia 1024 GB; a Starlink conta em decimal.
"""
import json
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import starlink  # noqa: E402

KIT_CONTRATO = {"productId": "br-mini-x-kit-contract", "name": "Mini X", "description": "Mini X",
                "longDescription": u"Contrato de 12 meses obrigatório. <b>30 dias para devolver.</b>",
                "price": "99", "adjustedPrice": "49"}
KIT_LIVRE = {"productId": "br-consumer-starlink-kit-mini-x", "name": "Mini X",
             "description": "Mini X", "longDescription": "Mini X", "price": "499",
             "adjustedPrice": "299"}
RESPOSTAS = {
    1: {"isAvailable": True, "kits": [KIT_CONTRATO, KIT_LIVRE], "subscriptions": [
        {"description": "Residencial: 100 Mbps", "price": "189", "adjustedPrice": "132.3"}]},
    6: {"isAvailable": True, "kits": [{"description": "Standard 4 X", "price": "2040",
                                       "adjustedPrice": "2040", "longDescription": "Standard 4 X"}],
        "subscriptions": [{"description": u"Prioritário Local 1 TB ", "price": "1235",
                           "adjustedPrice": "1235"}]},
    8: {"isAvailable": True, "kits": [KIT_LIVRE], "subscriptions": [
        {"description": "Viagem - 100 GB", "price": "339", "adjustedPrice": "339"},
        {"description": "Viagem - Ilimitado", "price": "619", "adjustedPrice": "619"}]},
}


class AStarlink(unittest.TestCase):

    def setUp(self):
        guarda = (starlink._http, starlink.PAUSA)

        def http(url, *a, **k):
            codigo = int(url.split("invitationTypeCode=")[1].split("&")[0])
            if codigo not in RESPOSTAS:
                return 200, json.dumps({"isAvailable": False})
            return 200, json.dumps(RESPOSTAS[codigo])
        starlink._http = http
        starlink.PAUSA = 0

        def volta():
            starlink._http, starlink.PAUSA = guarda
        self.addCleanup(volta)
        self.ofertas = {o["nome_oferta"]: o for o in starlink.coletar(verbose=False)["ofertas"]}

    def test_os_planos_de_viagem_entram(self):
        self.assertEqual(self.ofertas["Viagem - 100 GB"]["preco_promocional"], 339.0)
        self.assertEqual(self.ofertas["Viagem - 100 GB"]["franquia_anunciada_gb"], 100)
        self.assertEqual(self.ofertas["Viagem - Ilimitado"]["preco_promocional"], 619.0)
        self.assertEqual(self.ofertas["Viagem - 100 GB"]["familia"], "viagem")

    def test_o_kit_de_49_vem_com_o_contrato(self):
        r = self.ofertas["Residencial: 100 Mbps"]
        self.assertEqual(r["taxa_instalacao"], 49.0)
        self.assertEqual(r["fidelidade_meses"], 12)

    def test_kit_sem_contrato_nao_inventa_fidelidade(self):
        self.assertIsNone(self.ofertas["Viagem - 100 GB"]["fidelidade_meses"])
        self.assertEqual(self.ofertas["Viagem - 100 GB"]["taxa_instalacao"], 299.0)

    def test_o_terabyte_e_decimal_e_o_nome_sem_lixo_de_espaco(self):
        self.assertIn(u"Prioritário Local 1 TB", self.ofertas)
        self.assertEqual(self.ofertas[u"Prioritário Local 1 TB"]["franquia_anunciada_gb"], 1000)
        self.assertEqual(starlink.franquia("2 TB"), 2000)

    def test_o_global_fica_fora(self):
        u"""O 9 e o Prioritario Global, plano de empresa para uso fora do pais."""
        self.assertNotIn(9, starlink.FAMILIAS)


if __name__ == "__main__":
    unittest.main()
