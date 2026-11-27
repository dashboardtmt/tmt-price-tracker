# -*- coding: utf-8 -*-
u"""O FILTRO 8 DA SAIDA: a pagina do plano que falhou nao e o plano que saiu.

Desde 27/11/2026 o TIM Black e o Familia nao entram mais pelo carrossel
velho da pagina de pos-pago (tim._tem_pagina_propria). No dia em que a
pagina do plano falha, o plano simplesmente falta, e o coletor diz isso
no aviso da praca:

    Sao Paulo/SP: familia: nenhum card do TIM Black Familia reconhecido -
    a leitura falhou, e nao ha como afirmar que o plano saiu da praca

Os sete filtros de _ofertas_que_sairam olhavam so o dado. O filtro 7 (o
produto que ninguem leu) nao pega: o movel continua lido, pelo Black e
pelo pos. Medido no 27/11 com o coletor de hoje: o Familia sem leitura nas
20 pracas sairia como "TIM Black Familia, Plus, Premium e VIP sairam da
vitrine", 20 pracas cada.

O CAMINHO E O DE PRODUCAO, nas duas pontas: o aviso sai do leitor da TIM
(tim.ler_familia sobre uma pagina sem card) e ganha o nome da praca em
robo.coletar_operadora, como na rodada de verdade; a saida e lida em
robo.montar_mensagem. Se o texto do aviso mudar, o teste quebra aqui, em
vez de o filtro deixar de casar calado.
"""
import os
import sys
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))

import robo                                                   # noqa: E402
from _apoio import (COLETA_OK, HOJE, ONTEM, banco, dados,     # noqa: E402
                    montar, oferta, sem_declaracao)
from coletores import armazenamento, tim                      # noqa: E402
from coletores.pracas import PRACAS, rotulo                   # noqa: E402

ANTES = ["2026-10-18", "2026-10-19"]          # dentro da janela do vigia
TODAS = [rotulo(p) for p in PRACAS]

# os quatro Familia e o Black de Sao Paulo em 26/11/2026, no dado publicado
FAMILIA = ((u"TIM Black Família", 219.99, 150),
           (u"TIM Black Família Plus", 264.99, 180),
           (u"TIM Black Família Premium", 314.99, 210),
           (u"TIM Black Família VIP", 399.99, 250))
BLACK = ((u"TIM Black", 129.99, 70),)


def tim_movel(planos, dias, onde=TODAS):
    return [oferta(operadora="TIM", produto="movel", nome=nome, preco=preco,
                   gb=gb, praca=p, data=d,
                   chave="TIM|movel|%dgb|%s" % (gb, "familia" if "Fam" in nome
                                                else "simples"))
            for d in dias for p in onde for nome, preco, gb in planos]


def pagina_sem_card(op, url, *a, **kw):
    return 200, "<html><body><main>nada</main></body></html>"


def registro_da_tim(falha_em, iniciada_em=HOJE + "T06:00"):
    u"""A linha de "coletas" da TIM, montada pelo caminho de producao."""
    with mock.patch.object(tim, "buscar", pagina_sem_card):
        lidas, erro = tim.ler_familia(None, tim.FAMILIA % "sp", "sp")
    assert lidas == [] and erro, "a pagina sem card tem de virar aviso"

    class TimDeMentira(object):
        @staticmethod
        def coletar(cidade, uf, verbose=False):
            falhou = "%s/%s" % (cidade, uf) in falha_em
            return {"ofertas": [{"operadora": "TIM"}],
                    "avisos": ["familia: %s" % erro] if falhou else []}

    _o, registro, _e = robo.coletar_operadora(
        "TIM", TimDeMentira, PRACAS, simular=True, verbose=False,
        escrever=lambda _linha: None)
    registro.update(data_captura=HOJE, iniciada_em=iniciada_em)
    return registro


def coletas(*registros_da_tim):
    return [c for c in COLETA_OK if c["operadora"] != "TIM"] + list(registros_da_tim)


def o_dia(falha_em=TODAS):
    u"""Ontem os quatro Familia e o Black nas 20 pracas; hoje so o Black."""
    ontem = tim_movel(FAMILIA + BLACK, [ONTEM])
    hoje = tim_movel(BLACK, [HOJE])
    extras = tim_movel(FAMILIA + BLACK, ANTES)
    return ontem, hoje, extras, coletas(registro_da_tim(falha_em))


class OFamiliaSemLeituraNaoSaiDaVitrine(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def test_o_27_11_nenhuma_saida_anunciada(self):
        u"""O caso real: a pagina do Familia falhou nas 20 pracas."""
        ontem, hoje, extras, col = o_dia()
        d = dados(ontem, hoje, coletas=col, extras=extras)
        self.assertEqual(d["saidas"], [])
        t = montar(ontem, hoje, coletas=col, extras=extras)
        self.assertNotIn("saiu da vitrine", t)
        self.assertNotIn(u"Família", t)

    def test_sem_o_aviso_as_quatro_sairiam(self):
        u"""O controle: o mesmo dado, com a coleta sem aviso, da as quatro
        saidas. Sem isto o teste de cima passaria por qualquer motivo -
        um filtro que calasse toda saida, por exemplo."""
        ontem, hoje, extras, _col = o_dia()
        d = dados(ontem, hoje, extras=extras)
        self.assertEqual(sorted(s["nome_oferta"] for s in d["saidas"]),
                         sorted(n for n, _p, _g in FAMILIA))
        self.assertTrue(all(len(s["pracas"]) == 20 for s in d["saidas"]))

    def test_a_praca_lida_continua_dando_a_saida(self):
        u"""O filtro e por praca: onde a pagina foi lida e o plano nao
        estava, a saida vale - so que de 18 pracas, e nao de 20."""
        falhou = TODAS[:2]
        ontem, hoje, extras, col = o_dia(falha_em=falhou)
        d = dados(ontem, hoje, coletas=col, extras=extras)
        self.assertEqual(len(d["saidas"]), 4)
        for s in d["saidas"]:
            self.assertEqual(len(s["pracas"]), 18)
            self.assertFalse(set(falhou) & set(s["pracas"]))

    def test_vale_o_ultimo_registro_da_operadora(self):
        u"""Em dia de repique vale a ultima rodada, como na manchete: se
        ela leu a pagina e o plano nao estava, o plano saiu. A lista vem
        como o banco a devolve, pelo order=iniciada_em.desc."""
        ontem, hoje, extras, _col = o_dia()
        col = coletas(registro_da_tim([], iniciada_em=HOJE + "T09:00"),
                      registro_da_tim(TODAS, iniciada_em=HOJE + "T06:00"))
        d = dados(ontem, hoje, coletas=col, extras=extras)
        self.assertEqual(len(d["saidas"]), 4)


class SemOsAvisosNenhumaSaida(unittest.TestCase):
    u"""A consulta de coletas cai: nao da para saber que pagina falhou, e a
    saida nao e anunciada - a manchete diz por que, e a frase do dia
    parado deixa de afirmar que olhou a saida."""

    def setUp(self):
        sem_declaracao(self)

    def _mensagem(self, linhas):
        responder = banco(linhas)

        def um(caminho):
            if caminho.startswith("coletas"):
                return None, "HTTP 503: Service Unavailable"
            return responder(caminho)

        armazenamento.consultar = um
        armazenamento.consultar_tudo = lambda c, pagina=None: um(c)
        return robo.montar_mensagem(HOJE, ONTEM)

    def test_a_saida_nao_sai_e_a_manchete_diz(self):
        ontem, hoje, extras, _col = o_dia()
        t, d = self._mensagem(ontem + hoje + extras)
        self.assertEqual(d["saidas"], [])
        self.assertIn(u"nenhuma saída de oferta é anunciada", t)
        self.assertNotIn(u"nome ou saída de oferta", t)
        self.assertIn(u"Nenhuma mudança de preço, composição ou nome.", t)

    def test_o_pdf_nao_afirma_que_nada_saiu(self):
        import tempfile
        import pypdf
        import relatorio
        ontem, hoje, extras, _col = o_dia()
        _t, d = self._mensagem(ontem + hoje + extras)
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = " ".join("".join(p.extract_text()
                                 for p in pypdf.PdfReader(caminho).pages).split())
        self.assertNotIn("Nenhuma oferta deixou a vitrine", texto)
        self.assertIn(u"Saídas não conferidas", texto)


class ORotuloDoAvisoCasaPeloComecoDoNome(unittest.TestCase):

    def test_sem_acento_e_por_palavra(self):
        falhas = robo._paginas_que_falharam([registro_da_tim(TODAS[:1])])
        rotulos = falhas[("TIM", TODAS[0])]
        self.assertEqual(rotulos, {"tim black familia"})
        self.assertEqual(robo._plano(u"TIM Black Família VIP"),
                         "tim black familia vip")
        self.assertNotIn(("TIM", TODAS[1]), falhas)


if __name__ == "__main__":
    unittest.main()
