# -*- coding: utf-8 -*-
u"""O tier do app que a vitrine da Vivo escreve chega a tela (27/11/2026).

Dois defeitos da auditoria contra o site de 26/11:

  - O NETFLIX SEM TIER. O card do Vivo Controle Netflix diz "Assinatura
    Netflix Padrao com anuncios" e o do Vivo Pos com Netflix, "Netflix
    Padrao inclusa". A primeira passada lia o tier; a segunda, depois do
    regulamento, refazia o rotulo so com o bruto_texto - o texto do card
    cortado em 600 caracteres, antes do tier - e o nome da Anatel, que nao
    o diz. O tier saia vazio, e a tela mostrava o Netflix sem plano e sem
    preco de referencia.

  - O GOOGLE ONE SEM O LITE. O card do Vivo Pre de R$ 35 diz "Armazenamento
    extra com Google One"; a propria pagina diz, num card de acesso rapido,
    "Armazenamento com o Google One Lite nas recargas a partir de R$ 35".

A fixture e um recorte real de 26/11/2026: os dois cards de Netflix e os
quatro do pre, com os titulos de acesso rapido da pagina do pre.
"""
import io
import json
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import vivo  # noqa: E402

FIX = json.load(io.open(os.path.join(AQUI, "fixtures", "vivo_tier_do_card_2026-11-26.json"),
                        encoding="utf-8"))


class _Coleta(unittest.TestCase):

    def setUp(self):
        guarda = {k: getattr(vivo, k) for k in (
            "navegador", "trocar_praca", "indice_catalogo", "ler_lite", "PAUSA",
            "PAGINAS_EXTRAS", "regulamento", "buscar")}
        self.addCleanup(lambda: [setattr(vivo, k, v) for k, v in guarda.items()])
        vivo.navegador = lambda: (None, None)
        vivo.trocar_praca = lambda op, c, u: True
        vivo.indice_catalogo = lambda op: ({}, [])
        vivo.ler_lite = lambda op, hoje, avisos=None: ([], None)
        vivo.PAUSA = 0
        vivo.PAGINAS_EXTRAS = ()
        self.paginas = {vivo.VITRINE[p]: FIX[p] for p in ("controle", "movel", "prepago")}
        vivo.buscar = lambda op, url, **k: (200, self.paginas.get(url, "<html></html>"))
        # o regulamento que a Anatel publica: o nome registrado nao diz o tier
        self.pedidos = []

        def regulamento(op, codigo):
            self.pedidos.append(codigo)
            return {"nomeOferta": "VIVO OFERTA SEM TIER NO NOME", "SMP": {}, "SCM": {}}
        vivo.regulamento = regulamento

    def ofertas(self):
        d = vivo.coletar("Sao Paulo", "SP", verbose=False)
        return dict(((o["produto"], o["nome_oferta"], o["preco_promocional"]), o)
                    for o in d["ofertas"])


class ONetflixDoCard(_Coleta):

    def test_a_fixture_tem_o_tier_depois_do_corte_de_600(self):
        # sem isto o teste passaria pelo motivo errado: tier dentro do corte
        de = self.ofertas()
        o = de[("controle", "Vivo Controle Netflix", 90.0)]
        self.assertNotIn(u"Padrão com anúncios", o["bruto_texto"])
        self.assertTrue(self.pedidos, "o regulamento tem de ter sido aplicado")

    def test_o_controle_netflix_tem_o_padrao_com_anuncios(self):
        o = self.ofertas()[("controle", "Vivo Controle Netflix", 90.0)]
        self.assertEqual(o["apps_planos"], {"netflix": u"Padrão com anúncios"})
        self.assertEqual(o["apps_rotulo"], u"Netflix (Padrão com anúncios)")

    def test_o_pos_com_netflix_tem_o_padrao(self):
        o = self.ofertas()[("movel", u"Vivo Pós com Netflix", 180.0)]
        self.assertEqual(o["apps_planos"], {"netflix": u"Padrão"})

    def test_o_nome_da_anatel_ainda_completa_o_que_o_card_nao_diz(self):
        self.paginas[vivo.VITRINE["controle"]] = FIX["controle"].replace(
            u"Padrão com anúncios", u"")
        vivo.regulamento = lambda op, codigo: {"nomeOferta": "VIVO CONTROLE NETFLIX PREMIUM",
                                              "SMP": {}, "SCM": {}}
        o = self.ofertas()[("controle", "Vivo Controle Netflix", 90.0)]
        self.assertEqual(o["apps_planos"], {"netflix": "Premium"})

    def test_o_card_vale_antes_da_anatel(self):
        vivo.regulamento = lambda op, codigo: {"nomeOferta": "VIVO CONTROLE NETFLIX PREMIUM",
                                              "SMP": {}, "SCM": {}}
        o = self.ofertas()[("controle", "Vivo Controle Netflix", 90.0)]
        self.assertEqual(o["apps_planos"], {"netflix": u"Padrão com anúncios"})


class OGoogleOneLiteDaPagina(_Coleta):

    def test_o_pre_de_35_tem_o_lite(self):
        o = self.ofertas()[("prepago", u"Vivo Pré", 35.0)]
        self.assertEqual(o["apps"], ["vale_saude", "google_one"])
        self.assertEqual(o["apps_planos"], {"vale_saude": "Farma", "google_one": "Lite"})
        self.assertEqual(o["apps_rotulo"], u"Vale Saúde (Farma) + Google One (Lite)")

    def test_a_frase_da_pagina_nao_poe_app_no_card(self):
        de = self.ofertas()
        self.assertEqual(de[("prepago", u"Vivo Pré", 30.0)]["apps"], ["vale_saude"])
        self.assertEqual(de[("prepago", u"Vivo Pré", 25.0)]["apps"], [])

    def test_a_frase_so_vale_a_partir_do_valor_dela(self):
        cards, _ = vivo.ler_vitrine(None, "prepago")
        por_preco = {c["preco"]: c.get("tiers_da_pagina") or "" for c in cards}
        self.assertIn("Google One Lite", por_preco[35.0])
        self.assertNotIn("Google One", por_preco[30.0])
        self.assertIn(u"Vale Saúde Farma", por_preco[30.0])
        self.assertEqual(por_preco[25.0], "")

    def test_sem_a_frase_o_card_continua_sem_tier(self):
        self.paginas[vivo.VITRINE["prepago"]] = FIX["prepago"].replace(
            "Google One Lite nas recargas", "Google One nas recargas")
        o = self.ofertas()[("prepago", u"Vivo Pré", 35.0)]
        self.assertNotIn("google_one", o["apps_planos"] or {})


if __name__ == "__main__":
    unittest.main()
