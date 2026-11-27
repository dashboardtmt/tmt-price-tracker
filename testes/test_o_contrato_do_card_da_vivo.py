# -*- coding: utf-8 -*-
u"""O contrato que o card da Vivo declara vence o regulamento que diz outro.

O CASO REAL, de 27/11/2026. O card da Vivo Total Essencial de 600 Mega diz
"60 GB de Vivo Pos" e, logo abaixo, "40 GB de Franquia + 20 GB de bonus":
40 de contrato. O tracker gravou 60, do regulamento do codigo
VIV202604066118 - que a Essencial divide com o Vivo Total Pro (R$ 160, 100
GB, "60 GB de franquia + 40 GB de bonus"), e que se chama "VT Pro 600Mega
com SVA + 60 GB". A guarda de aplicar_regulamento so recusava o documento
que declara MAIS do que o card anuncia; este declara o mesmo que o
anunciado (60) e passava, levando junto o preco de tabela do Pro (R$ 160)
e a multa dele.

O que vale e o site: com a frase no card, o contrato e o N dela, e o
regulamento que diz outro numero e de outra oferta - nenhum campo dele
vale, como na guarda que ja existia.

As fixtures sao recortes reais da pagina de combos de Sao Paulo de
27/11/2026: os dois cards que dividem o codigo, e o regulamento dele.
"""
import io
import json
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import armazenamento, vivo  # noqa: E402

FIX = os.path.join(AQUI, "fixtures")
CARDS = io.open(os.path.join(FIX, "vivo_total_essencial_e_pro_2026-11-27.html"),
                encoding="utf-8").read()
REGS = json.load(io.open(os.path.join(
    FIX, "vivo_total_essencial_regulamento_2026-11-27.json"), encoding="utf-8"))


class _ColetaDaPagina(unittest.TestCase):
    u"""coletar() inteiro sobre a pagina real: e ele que le o card, grava o
    contrato e chama o regulamento - o caminho de producao, e nao a peca."""

    def setUp(self):
        self.guarda = {k: getattr(vivo, k) for k in (
            "navegador", "trocar_praca", "indice_catalogo", "buscar",
            "ler_lite", "PAUSA", "PAGINAS_EXTRAS", "regulamento")}
        self.addCleanup(lambda: [setattr(vivo, k, v) for k, v in self.guarda.items()])
        vivo.navegador = lambda: (None, None)
        vivo.trocar_praca = lambda op, c, u: True
        vivo.indice_catalogo = lambda op: ({}, [])
        vivo.ler_lite = lambda op, hoje, avisos=None: ([], None)
        vivo.PAUSA = 0
        vivo.PAGINAS_EXTRAS = ()
        self.html = CARDS
        self.regs = dict(REGS)
        # so a pagina de combos tem card; as outras respondem vazias
        vivo.buscar = lambda op, url, *a, **k: (
            200, self.html if url == vivo.VITRINE["combo"] else "")
        vivo.regulamento = lambda op, codigo: self.regs.get(codigo)

    def ler(self):
        d = vivo.coletar("Sao Paulo", "SP", verbose=False)
        return dict((o["nome_oferta"], o) for o in d["ofertas"])


class AEssencialDaPurpleFriday(_ColetaDaPagina):

    def test_o_contrato_e_o_do_card(self):
        o = self.ler()[u"Vivo Total Essencial"]
        self.assertEqual(o["preco_promocional"], 130.0)
        self.assertEqual(o["franquia_anunciada_gb"], 60)
        self.assertEqual(o["franquia_contratual_gb"], 40)

    def test_nenhum_campo_do_regulamento_do_pro_vale(self):
        u"""Preco de tabela de R$ 160 e multa de R$ 1.400 sao do Pro."""
        o = self.ler()[u"Vivo Total Essencial"]
        for campo in ("preco_cheio", "fidelidade_meses", "multa_fidelidade",
                      "taxa_instalacao"):
            self.assertIsNone(o.get(campo), campo)
        self.assertIsNone(o.get("assinatura_sva"))

    def test_a_recusa_e_dita(self):
        o = self.ler()[u"Vivo Total Essencial"]
        longos = " ".join(a.get("longo", "") for a in o.get("avisos_oferta") or ())
        self.assertIn(u"o regulamento declara 60 GB de contrato e o card, 40 GB", longos)
        self.assertIn(u"o contrato gravado é o do card", longos)

    def test_a_chave_da_serie_nao_muda(self):
        u"""Mexer na leitura pode mudar a chave; esta nao muda - a serie da
        Essencial continua a mesma no dia seguinte."""
        o = self.ler()[u"Vivo Total Essencial"]
        self.assertEqual(armazenamento.chave_continuidade(o),
                         "Vivo|combo|600mbps_60gb|simples")

    def test_o_pro_continua_com_o_regulamento(self):
        u"""O documento e do Pro: o card dele diz 60 + 40, e tudo vale."""
        o = self.ler()[u"Vivo Total Pro"]
        self.assertEqual(o["franquia_anunciada_gb"], 100)
        self.assertEqual(o["franquia_contratual_gb"], 60)
        self.assertEqual(o["preco_cheio"], 160.0)
        self.assertEqual(o["fidelidade_meses"], 12)
        self.assertEqual(o["multa_fidelidade"], 1400.0)

    def test_card_sem_a_frase_deixa_o_regulamento(self):
        u"""Sem "N GB de franquia + M GB de bonus", nada muda: o contrato
        segue o regulamento, como antes."""
        self.html = CARDS.replace(u"40 GB de Franquia + 20 GB de bônus", u"")
        o = self.ler()[u"Vivo Total Essencial"]
        self.assertEqual(o["franquia_contratual_gb"], 60)
        self.assertEqual(o["preco_cheio"], 160.0)


class OCardQueSeContradizNaoDecide(unittest.TestCase):

    def test_um_par_so(self):
        self.assertEqual(vivo.contrato_do_card(
            u"40 GB de Franquia + 20 GB de bônus ... 40 GB de franquia + 20 GB de bonus",
            60), 40)

    def test_dois_pares_diferentes_nao_chutam(self):
        self.assertIsNone(vivo.contrato_do_card(
            u"40 GB de Franquia + 20 GB de bônus e 60 GB de franquia + 40 GB de bônus"))

    def test_a_soma_tem_de_fechar_com_o_anunciado(self):
        self.assertIsNone(vivo.contrato_do_card(
            u"40 GB de Franquia + 20 GB de bônus", 100))

    def test_sem_a_frase(self):
        self.assertIsNone(vivo.contrato_do_card(u"60 GB de Vivo Pós", 60))


if __name__ == "__main__":
    unittest.main()
