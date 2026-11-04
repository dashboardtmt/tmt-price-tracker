# -*- coding: utf-8 -*-
u"""O portao que faltava: a mesma pagina lida por dois leitores.

O QUE ELE PRECISA ACERTAR, e por que cada caso esta aqui:

  PERDA BARRA. Em 04/11/2026 a regra da barra tirou o Paramount da
  Ultracombo 6 e o Aya Books da 7, nas 20 pracas, e nada no projeto
  percebeu antes da mensagem sair. O ensaio existe para esse caso, e o
  primeiro teste e' ele, com os nomes de campo de verdade.

  GANHO NAO BARRA. Melhorar a leitura ACRESCENTA. Se ganho barrasse, o
  portao impediria todo conserto - e o conserto do mesmo dia, que fez a
  Ultracombo 6 nomear tambem Deezer e Aya Ensinah, seria barrado por
  acertar.

  TROCA BARRA. A mesma pagina nao muda de preco sozinha: dois valores
  diferentes lidos do mesmo corpo sao leitura nova, e leitura nova de
  PRECO tem de ser deliberada.

  E COLETOR SEM TORNEIRA NAO PODE FICAR DE FORA CALADO. E a mesma regra
  de COLETORES x RAIAS: quem adiciona coletor e esquece o ensaio
  descobre aqui, e nao em marco olhando um grafico.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "ferramentas"))

import ensaio_da_coleta as ensaio                             # noqa: E402
import robo                                                   # noqa: E402


def oferta(**kw):
    base = {"operadora": "TIM", "produto": "combo",
            "praca": "Sao Paulo/SP",
            "nome_oferta": "TIM Ultracombo 6 1GIGA + 70GB",
            "degrau_mbps": 1000, "franquia_anunciada_gb": 70,
            "preco_promocional": 149.99, "apps": ["paramount"],
            "apps_rotulo": "Paramount+", "nivel_bundle": 3}
    base.update(kw)
    return base


class OQueBarraOPush(unittest.TestCase):

    def test_app_que_desaparece_e_perda(self):
        """O defeito de 04/11/2026, com os campos de verdade."""
        d = ensaio.comparar([oferta()],
                            [oferta(apps=[], apps_rotulo=None)])
        campos = sorted(p[1] for p in d["perdas"])
        self.assertEqual(campos, ["apps", "apps_rotulo"])
        self.assertEqual(d["trocas"], [])
        self.assertTrue(d["perdas"], "perda tem de barrar")

    def test_preco_diferente_na_mesma_pagina_e_troca(self):
        d = ensaio.comparar([oferta()], [oferta(preco_promocional=159.99)])
        self.assertEqual([p[1] for p in d["trocas"]], ["preco_promocional"])
        self.assertEqual(d["perdas"], [])

    def test_oferta_que_desaparece_e_perda(self):
        d = ensaio.comparar([oferta()], [])
        self.assertEqual(len(d["perdas"]), 1)
        self.assertEqual(d["perdas"][0][1], "a oferta inteira")

    def test_degrau_diferente_sai_como_sumiu_e_apareceu(self):
        """Mudar o degrau nao e' mudar um campo: e outra oferta, e dizer
        isso e mais honesto do que inventar pareamento."""
        d = ensaio.comparar([oferta()], [oferta(degrau_mbps=600)])
        self.assertEqual(len(d["perdas"]), 1)
        self.assertEqual(len(d["novas"]), 1)


class OQueNaoBarra(unittest.TestCase):

    def test_app_que_aparece_e_ganho(self):
        """O conserto do mesmo dia: a Ultracombo 6 passou a nomear
        tambem Deezer e Aya Ensinah. Barrar isso seria barrar o
        acerto."""
        d = ensaio.comparar(
            [oferta()],
            [oferta(apps=["paramount", "deezer", "aya_ensinah"])])
        self.assertEqual(d["perdas"], [])
        self.assertEqual(d["trocas"], [])
        self.assertEqual(len(d["ganhos"]), 1)

    def test_campo_vazio_dos_dois_lados_nao_e_nada(self):
        d = ensaio.comparar([oferta(codigo_anatel=None)],
                            [oferta(codigo_anatel=None)])
        self.assertEqual(d["perdas"] + d["trocas"] + d["ganhos"], [])

    def test_oferta_nova_e_informativa(self):
        d = ensaio.comparar([], [oferta()])
        self.assertEqual(d["perdas"], [])
        self.assertEqual(len(d["novas"]), 1)

    def test_lista_que_so_muda_de_ordem_nao_e_diferenca(self):
        d = ensaio.comparar([oferta(apps=["paramount", "deezer"])],
                            [oferta(apps=["deezer", "paramount"])])
        self.assertEqual(d["perdas"] + d["trocas"] + d["ganhos"], [])


class ONivelTemDirecao(unittest.TestCase):
    """A primeira rodada de verdade ensinou isto sobre o proprio ensaio.

    Em 04/11/2026, contra o commit anterior, o ensaio acusou "TROCA:
    nivel_bundle 1 -> 3" na TIM Ultracombo 6 - e aquilo era o ACERTO do
    dia: o nivel subiu porque os apps voltaram. Barrar ali seria barrar
    todo conserto que melhora a leitura.
    """

    def test_nivel_que_sobe_e_ganho(self):
        d = ensaio.comparar([oferta(nivel_bundle=1)],
                            [oferta(nivel_bundle=3)])
        self.assertEqual([g[1] for g in d["ganhos"]], ["nivel_bundle"])
        self.assertEqual(d["perdas"] + d["trocas"], [])

    def test_nivel_que_cai_e_perda(self):
        """A assinatura do defeito da barra: 3 que vira 1."""
        d = ensaio.comparar([oferta(nivel_bundle=3)],
                            [oferta(nivel_bundle=1)])
        self.assertEqual([p[1] for p in d["perdas"]], ["nivel_bundle"])

    def test_preco_nao_tem_direcao_e_barra_nos_dois_sentidos(self):
        """Preco nao e "quanto nos sabemos": e fato. Fato diferente lido
        do mesmo corpo barra subindo ou descendo."""
        for a, b in ((149.99, 159.99), (159.99, 149.99)):
            d = ensaio.comparar([oferta(preco_promocional=a)],
                                [oferta(preco_promocional=b)])
            self.assertEqual([t[1] for t in d["trocas"]],
                             ["preco_promocional"], "%s -> %s" % (a, b))


class AIdentidadeRepetida(unittest.TestCase):
    """Duas ofertas com a mesma identidade comparam como uma, e a ultima
    de cada par ganha o lugar. Na primeira rodada foram 112 ofertas
    gravadas e 110 comparadas, calado."""

    def test_colisao_que_a_mudanca_criou_barra(self):
        d = ensaio.comparar([oferta()],
                            [oferta(preco_promocional=149.99),
                             oferta(preco_promocional=159.99)])
        self.assertEqual(len(d["colididas"]), 1)

    def test_colisao_que_ja_existia_nao_barra(self):
        """A vitrine da Vivo chama duas ofertas de "Vivo Familia 2 + TV"
        no mesmo degrau desde sempre. Portao que sempre barra vira
        portao que ninguem respeita - a mesma razao pela qual _indexar
        manda colisao para o ponto cego, e nao para o canal de erro."""
        dois_lados = [oferta(preco_promocional=290.0),
                      oferta(preco_promocional=390.0)]
        d = ensaio.comparar(dois_lados, list(dois_lados))
        self.assertEqual(d["colididas"], [])
        self.assertEqual(len(d["herdadas"]), 1)

    def test_a_contagem_crua_sai_junto_da_comparada(self):
        d = ensaio.comparar([oferta(preco_promocional=1.0),
                             oferta(preco_promocional=2.0)], [oferta()])
        self.assertEqual(d["cruas"], (2, 1))
        self.assertEqual(d["lidas"], (1, 1))


class NenhumColetorFicaDeFora(unittest.TestCase):

    def test_todo_coletor_tem_torneira_ou_navegador(self):
        """A mesma guarda de COLETORES x RAIAS, para o ensaio.

        Coletor sem torneira roda buscando de verdade nas DUAS leituras,
        e ai o ensaio compara duas coletas em vez de duas leituras da
        mesma pagina - exatamente o que o cabecalho da ferramenta diz
        que nao serve.
        """
        cobertos = {t[0] for t in ensaio.TORNEIRAS} | set(ensaio.NAVEGADOR)
        de_producao = {m.__name__.rsplit(".", 1)[-1]
                       for m in robo.COLETORES.values()}
        self.assertEqual(de_producao - cobertos, set(),
                         "coletor de producao sem torneira no ensaio")

    def test_toda_torneira_declarada_e_realmente_instalada(self):
        """O LACO NAO SE MEDE SOZINHO. O provador reduziu a instalacao a
        TORNEIRAS[:1] - um coletor interceptado, os outros buscando de
        verdade nas duas leituras - e nenhum teste percebeu: o ensaio
        comparava duas coletas em vez de duas leituras da mesma pagina.
        """
        import types
        mods, originais = {}, {}
        for modulo, funcao in ensaio.TORNEIRAS:
            m = mods.setdefault(modulo, types.SimpleNamespace())
            originais[(modulo, funcao)] = lambda *a, **k: (200, "x")
            setattr(m, funcao, originais[(modulo, funcao)])
        instaladas = ensaio.instalar_torneiras(mods, {}, True)
        self.assertEqual(sorted(instaladas), sorted(ensaio.TORNEIRAS))
        for modulo, funcao in ensaio.TORNEIRAS:
            self.assertIsNot(getattr(mods[modulo], funcao),
                             originais[(modulo, funcao)],
                             "%s.%s ficou sem embrulho" % (modulo, funcao))

    def test_toda_praca_do_ensaio_tem_coletor_declarado(self):
        self.assertEqual(set(ensaio.PRACAS), set(ensaio.POR_PRACA))
        for praca, quais in ensaio.POR_PRACA.items():
            self.assertTrue(quais, "praca no ensaio sem coletor: %s" % praca)

    def test_o_ensaio_cobre_as_pracas_de_cada_coletor_regional(self):
        """A Brisanet nao vende em Sao Paulo e a Unifique so no Sul:
        praca unica deixaria os dois sem exercicio nenhum."""
        from coletores.pracas import pracas_de, rotulo
        for op, modulo in (("Brisanet", "brisanet"),
                           ("Unifique", "unifique")):
            onde = {rotulo(p) for p in pracas_de(op)}
            no_ensaio = {p for p, quais in ensaio.POR_PRACA.items()
                         if modulo in quais}
            self.assertTrue(no_ensaio & onde,
                            "%s nao e exercitada em praca onde existe" % op)


if __name__ == "__main__":
    unittest.main(verbosity=2)
