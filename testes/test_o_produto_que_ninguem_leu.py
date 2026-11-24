# -*- coding: utf-8 -*-
u"""O PRODUTO QUE NINGUEM LEU NAO SAIU DA VITRINE.

Em 17/11/2026 a TIM trocou o card do Ultracombo por um componente com o
preco preenchido pelo JavaScript. O coletor nao reconheceu nada, AVISOU
("nenhum card de combo reconhecido - a pagina mudou"), e a rodada fechou
como sucesso porque toda praca trouxe alguma oferta. A mensagem disse
que os dois Ultracombos sairam da vitrine nas 20 pracas; a pagina
mostrava os dois, no preco da vespera.

Medido nos 49 dias publicados: um produto inteiro zerou numa praca
coletada 23 vezes, e todas eram leitura. Escolha de quem le, em
17/11/2026: produto zerado vira COLETA INCOMPLETA na manchete, e nao
saida.

O QUE ESTE ARQUIVO PRENDE:
  - o produto zerado nao rende "saiu da vitrine";
  - ele sai na manchete, com a operadora, o produto e quantas pracas;
  - a oferta que sai de verdade, num produto que foi lido, continua
    saindo;
  - o classificador trocando o balde (a NuCel de movel para controle)
    nao e produto zerado;
  - o PDF traz a lista.
"""
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))

import robo                                                   # noqa: E402
from _apoio import HOJE, ONTEM, dados, montar, oferta         # noqa: E402

try:
    import pypdf
    import relatorio
except Exception:                                             # pragma: no cover
    relatorio = None

ANTES = ["2026-10-18", "2026-10-19"]


def pracas(n=3):
    from coletores.pracas import PRACAS, rotulo
    return [rotulo(p) for p in PRACAS][:n]


def tim(nome, produto, preco, data, onde, gb=None, mbps=None):
    chave = "TIM|%s|%s|simples" % (produto, ("%sgb" % gb) if gb and not mbps
                                   else "%smbps_%sgb" % (mbps, gb) if gb
                                   else "%smbps" % mbps)
    return [oferta(operadora="TIM", produto=produto, nome=nome, preco=preco,
                   gb=gb, mbps=mbps, praca=p, data=data, chave=chave)
            for p in onde]


def combo(data, onde):
    return (tim("TIM Ultracombo 7 600MEGA + 65GB", "combo", 89.99, data,
                onde, gb=65, mbps=600)
            + tim("TIM Ultracombo 6 1GIGA + 70GB", "combo", 139.99, data,
                  onde, gb=70, mbps=1000))


def controle(data, onde, nome="TIM Controle Smart", gb=45, preco=58.99):
    return tim(nome, "controle", preco, data, onde, gb=gb)


def com_historia(fn, onde):
    linhas = []
    for dia in ANTES + [ONTEM]:
        linhas += fn(dia, onde)
    return linhas


class OComboDe17DeNovembro(unittest.TestCase):

    def setUp(self):
        self.onde = pracas(3)
        # ontem e antes: combo e controle; hoje: so o controle
        self.ontem = (com_historia(combo, self.onde)
                      + com_historia(controle, self.onde))
        self.hoje = controle(HOJE, self.onde)

    def test_nao_sai_da_vitrine(self):
        t = montar(self.ontem, self.hoje)
        self.assertNotIn("saiu da vitrine", t)
        self.assertNotIn("Ultracombo", t)

    def test_sai_na_manchete(self):
        t = montar(self.ontem, self.hoje)
        self.assertIn(u"COLETA INCOMPLETA — TIM sem ler combo em 3 "
                      u"praças.", t)

    def test_o_levantamento_diz_onde(self):
        d = dados(self.ontem, self.hoje)
        self.assertEqual(d["nao_lidos"], [{"operadora": "TIM",
                                           "produto": "combo",
                                           "pracas": sorted(self.onde)}])
        self.assertEqual(d["saidas"], [])

    @unittest.skipIf(relatorio is None, "reportlab ou pypdf ausente")
    def test_o_pdf_traz_a_lista(self):
        d = dados(self.ontem, self.hoje)
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "r.pdf")
            relatorio.gerar(d, {}, caminho)
            texto = " ".join(p.extract_text() or ""
                             for p in pypdf.PdfReader(caminho).pages)
        texto = " ".join(texto.split())
        self.assertIn("Cobertura da coleta", texto)
        self.assertIn("sem nenhuma oferta lida em 3", texto)
        self.assertIn(self.onde[0].split("/")[0], texto)


class ASaidaDeVerdadeContinua(unittest.TestCase):
    u"""O filtro 7 tira a praca do produto nao lido, e so ela."""

    def test_a_oferta_que_sai_de_produto_lido_continua_saindo(self):
        onde = pracas(3)
        ontem = (com_historia(controle, onde)
                 + com_historia(lambda d, o: controle(
                     d, o, nome="TIM Controle Premium", gb=55, preco=84.99),
                     onde))
        hoje = controle(HOJE, onde)
        t = montar(ontem, hoje)
        self.assertIn("saiu da vitrine", t)
        self.assertIn("TIM Controle Premium", t)
        self.assertNotIn("COLETA INCOMPLETA", t)

    def test_a_praca_lida_conta_e_a_nao_lida_nao(self):
        u"""O combo sai de verdade em duas pracas e nao e lido na
        terceira: a saida vale onde houve leitura, e a terceira fica fora
        do universo, e nao conta como "continua la"."""
        onde = pracas(3)
        lidas, nao_lida = onde[:2], onde[2:]
        ontem = (com_historia(combo, onde) + com_historia(controle, onde)
                 + com_historia(lambda d, o: tim(
                     "TIM Ultracombo 9 2GIGA + 90GB", "combo", 199.99, d, o,
                     gb=90, mbps=2000), lidas))
        # nas duas pracas lidas o combo segue, sem o Ultracombo 9; na
        # terceira, nenhum combo
        hoje = combo(HOJE, lidas) + controle(HOJE, onde)
        d = dados(ontem, hoje)
        saiu = [s for s in d["saidas"] if "Ultracombo 9" in s["nome_oferta"]]
        self.assertEqual(len(saiu), 1)
        self.assertEqual(saiu[0]["pracas"], sorted(lidas))
        self.assertEqual([n["pracas"] for n in d["nao_lidos"]],
                         [sorted(nao_lida)])
        # e os dois que continuam nas lidas nao saem de lugar nenhum
        self.assertFalse([s for s in d["saidas"]
                          if "Ultracombo 9" not in s["nome_oferta"]])


class OBaldeTrocadoNaoEProdutoZerado(unittest.TestCase):
    u"""A NuCel de 07/10/2026: as ofertas passaram de movel para controle
    no classificador. O produto movel zerou, mas a serie continua na
    praca - e reclassificacao, e nao leitura falhada."""

    def test_reclassificacao_nao_vira_alerta(self):
        onde = ["Brasil/BR"]
        ontem = []
        for dia in ANTES + [ONTEM]:
            ontem += [oferta(operadora="NuCel", produto="movel",
                             nome="NuCel 35 GB", preco=45.0, gb=35,
                             praca=p, data=dia, chave="NuCel|movel|35gb|simples")
                      for p in onde]
        hoje = [oferta(operadora="NuCel", produto="controle",
                       nome="NuCel 35 GB", preco=45.0, gb=35, praca=p,
                       data=HOJE, chave="NuCel|controle|35gb|simples")
                for p in onde]
        d = dados(ontem, hoje)
        self.assertEqual(d["nao_lidos"], [])


class APracaQueCaiuInteiraNaoRepete(unittest.TestCase):
    u"""Praca sem linha nenhuma da operadora hoje ja e dita pelo
    pracas_ok, na manchete; o produto zerado e so o da praca lida."""

    def test_so_a_praca_coletada_entra(self):
        onde = pracas(3)
        ontem = com_historia(combo, onde) + com_historia(controle, onde)
        hoje = controle(HOJE, onde[:2])
        d = dados(ontem, hoje)
        self.assertEqual([n["pracas"] for n in d["nao_lidos"]],
                         [sorted(onde[:2])])


if __name__ == "__main__":
    unittest.main(verbosity=2)
