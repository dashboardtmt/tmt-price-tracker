# -*- coding: utf-8 -*-
u"""A Brisanet inteira: as paginas de streaming, a fibra sem SVA e a nota do
modal.

Auditoria contra o site de 26/11/2026: o coletor lia duas consultas (internet
e combo) e a Brisanet vende em mais seis paginas de streaming (Sky+, Max,
Telecine, Netflix, Premiere, Globoplay) - 62 linhas por dia - e numa pagina
de fibra sem apps (35 linhas, com o unico 1 Giga dela). Nas paginas de
streaming o fim da promocao so esta no modal "Mais detalhes".
"""
import json
import os
import re
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import brisanet  # noqa: E402


def oferta(ident, nome, mbps, preco, cheio, nota=None, modal=None):
    return {"documentId": ident, "offer_name": nome, "plan_speed": mbps,
            "description": None, "additional_details": None,
            "price": {"price_note": nota, "price_note_modal_detail": modal,
                      "original_price": cheio, "discount_price": preco},
            "included_products": []}


RESPOSTAS = {
    "internetPage": {
        "Offers": [{"tab_name": "Internet", "offers": [
            oferta("f1", "[NOV] OFT NE PF 12M 500MB BLACK", "500", 79.9, 89.9)]}],
        "PageInternetSemSva": [{"tab_name": None, "offers": [
            oferta("s1", "Internet 1GB sem SVAS", "1000", None, 144.9),
            oferta("s2", "Internet 600MB sem SVAS", "600", None, 84.9,
                   nota=u"No 13º mês será reajustado para R$ 94,90")]}]},
    "comboPage": {"Offers": [{"tab_name": None, "offers": [
        oferta("c1", "[NOV] 600MB + 40GB", "600", 99.9, 119.89),
        oferta("c2", "[NOV] 700MB + SKY LIGHT", "700", 94.9, 109.8)]}]},
    "skyplusPage": {"Offers": [{"tab_name": "Combos", "offers": [
        oferta("c2", "[NOV] 700MB + SKY LIGHT", "700", 94.9, 109.8),
        oferta("k1", "[NOV] 600MB + SKY LIGHT", "600", 89.9, 104.8,
               modal=u"No 13º mês o valor será R$ 104,80")]}]},
    "maxPage": {"Offers": [{"tab_name": "Destaques", "offers": [
        oferta("m1", "[NOV] 600MB + 40GB + Max", "600", 129.79, 149.79,
               modal=u"No 13° mês o valor da oferta será R$ 149,79")]}]},
    "telecinePage": {"Offers": [{"tab_name": None, "offers": [
        oferta("t1", "NOV26 500MB + TELECINE", "500", 89.9, 113.8)]}]},
    "netflixPage": {"Offers": []},
    "premierePage": {"Offers": []},
    "globoPlayPage": {"Offers": []},
}


class _ComApi(unittest.TestCase):

    def setUp(self):
        self.falha = set()
        guarda = (brisanet.descobrir_token, brisanet.achar_cidade, brisanet.gql, brisanet.PAUSA)
        brisanet.descobrir_token = lambda: ("tok", None)
        brisanet.achar_cidade = lambda tok, c, u: ("cid", None)

        def gql(tok, q, variaveis=None):
            raiz = re.search(r"\{\s*(\w+)\s*\{", q).group(1)
            if raiz in self.falha:
                return None, "HTTP 502"
            blocos = re.findall(r"(\w+)\s*\{\s*tab_name", q)
            dado = RESPOSTAS.get(raiz) or {}
            return {raiz: {b: dado.get(b, []) for b in blocos}}, None
        brisanet.gql = gql
        brisanet.PAUSA = 0

        def volta():
            (brisanet.descobrir_token, brisanet.achar_cidade, brisanet.gql,
             brisanet.PAUSA) = guarda
        self.addCleanup(volta)

    def coletar(self):
        return brisanet.coletar("Fortaleza", "CE", verbose=False)


class ABrisanetInteira(_ComApi):

    def test_as_paginas_de_streaming_entram(self):
        nomes = {o["nome_oferta"] for o in self.coletar()["ofertas"]}
        for n in ("[NOV] 600MB + SKY LIGHT", "[NOV] 600MB + 40GB + Max",
                  "NOV26 500MB + TELECINE"):
            self.assertIn(n, nomes)

    def test_a_oferta_em_duas_paginas_entra_uma_vez(self):
        nomes = [o["nome_oferta"] for o in self.coletar()["ofertas"]]
        self.assertEqual(nomes.count("[NOV] 700MB + SKY LIGHT"), 1)

    def test_a_fibra_sem_sva_entra_como_fibra(self):
        por = {o["nome_oferta"]: o for o in self.coletar()["ofertas"]}
        giga = por["Internet 1GB sem SVAS"]
        self.assertEqual(giga["produto"], "fibra")
        self.assertEqual(giga["preco_promocional"], 144.9)
        self.assertEqual(giga["degrau_mbps"], 1000)
        self.assertEqual(por["Internet 600MB sem SVAS"]["preco_pos_promocao"], 94.9)

    def test_a_nota_do_modal_da_o_fim_da_promocao(self):
        por = {o["nome_oferta"]: o for o in self.coletar()["ofertas"]}
        sky = por["[NOV] 600MB + SKY LIGHT"]
        self.assertEqual((sky["meses_desconto"], sky["preco_pos_promocao"]), (12, 104.8))

    def test_pagina_que_falha_tira_o_produto_inteiro_da_praca(self):
        u"""A oferta que so mora na pagina que falhou sairia como saida da
        vitrine; o combo inteiro fica fora, dito, e a fibra continua."""
        self.falha = {"maxPage"}
        d = self.coletar()
        self.assertFalse([o for o in d["ofertas"] if o["produto"] == "combo"])
        self.assertTrue([o for o in d["ofertas"] if o["produto"] == "fibra"])
        self.assertTrue(any("fora da praca hoje" in a for a in d["avisos"]))


if __name__ == "__main__":
    unittest.main()
