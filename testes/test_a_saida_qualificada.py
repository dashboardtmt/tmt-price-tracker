# -*- coding: utf-8 -*-
u"""A saida que nao esvazia a prateleira, e a serie que pisca.

MEDIDO EM 04/11/2026 nas 24 saidas que a janela publicada produz, dois
sinais com dois casos cada - e a regra da casa e um caso real por
filtro:

  A. O DEGRAU CONTINUA NA VITRINE. A mensagem de hoje disse "Vivo Lite
     Anual III saiu da vitrine, estava a 40,00, em todas as 2 pracas", e
     nas MESMAS duas pracas entrou "Vivo Lite + YouTube Premium Lite"
     por R$ 40,00 pelos mesmos 40 GB. Em 24/10 a Brisanet trocou "SET26
     500MB + TELECINE" por "[NOV] 500MB + NETFLIX PCA", os dois a
     R$ 108,80. O filtro 5 compara NOME, e nenhum dos dois pares se
     parece o suficiente.

  B. A PROPRIA SERIE PISCA. A pagina do Vivo Lite rotaciona versao: a
     Mensal II esteve de 27 a 31/10, faltou em 01 e 02/11, voltou em
     03/11 em 18 pracas e saiu hoje. A MESMA oferta foi anunciada
     saindo duas vezes, em 01/11 e em 04/11.

NAO SUPRIME, QUALIFICA. A oferta saiu mesmo, e esconder a linha seria o
defeito oposto. O que era falso e a implicacao: que o ponto de preco
deixou a prateleira, e que a ausencia de hoje e a primeira.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
from _apoio import HOJE, ONTEM, banco, em_todas, oferta       # noqa: E402

# A janela do vigia olha sete dias, e a oferta precisa de tres para
# sair. ONTEM (20/10) entra separado: repetido aqui, a linha viraria
# duas iguais no mesmo dia e a oferta sairia do indice como
# indistinguivel - o cenario mediria a colisao, e nao a saida.
DIAS = ["2026-10-%02d" % d for d in range(15, 20)]


def lite(data, nome, preco, gb, pracas=None, chave=None):
    comum = dict(operadora="Vivo", produto="btl", nome=nome, preco=preco,
                 gb=gb, data=data,
                 chave=chave or "Vivo|btl|%dgb|simples" % gb)
    if pracas is None:
        return em_todas(**comum)
    return [oferta(praca=p, **comum) for p in pracas]


def viveu(nome, preco, gb, dias=DIAS, pracas=None):
    """A oferta em todos os dias da janela, para passar do filtro 3."""
    return [l for d in dias for l in lite(d, nome, preco, gb, pracas)]


def companhia(data=None):
    """Uma oferta da Vivo nas 20 pracas, em todos os dias.

    DOIS FILTROS DEPENDEM DELA. O filtro 1 so compara praca coletada
    HOJE pela mesma operadora: sem companhia, a praca onde a oferta
    saiu nem conta, e o cenario mede outra coisa. E o nome tem de ser
    DISTANTE dos outros: o filtro 5 descarta a saida quando algo
    parecido entra, e "Mensal II" contra "Mensal III" passa de 0,75.
    """
    nome, preco, gb = "Vivo Fibra Base 300", 99.9, 300
    if data:
        return lite(data, nome, preco, gb,
                    chave="Vivo|btl|300gb|simples_base")
    return [l for d in DIAS + [ONTEM, HOJE]
            for l in lite(d, nome, preco, gb,
                          chave="Vivo|btl|300gb|simples_base")]


class ODegrauQueContinuaNaVitrine(unittest.TestCase):

    def montar(self, entrante_pracas=None, preco_entrante=40.0):
        """A Anual III sai; a + YouTube Premium Lite fica no degrau."""
        banco(companhia()
              + viveu("Vivo Lite Anual III", 40.0, 40)
              + lite(ONTEM, "Vivo Lite Anual III", 40.0, 40)
              + lite(HOJE, "Vivo Lite + YouTube Premium Lite",
                     preco_entrante, 40, entrante_pracas,
                     chave="Vivo|btl|40gb|simples_youtube"))
        return robo.mudancas(HOJE, ONTEM)

    def test_a_saida_sai_e_a_substituta_vai_nomeada(self):
        m = self.montar()
        saidas = [s for s in m["saidas"]
                  if s["nome_oferta"] == "Vivo Lite Anual III"]
        self.assertEqual(len(saidas), 1, "a saida continua sendo anunciada")
        s = saidas[0]
        self.assertEqual(s["substituta"], "Vivo Lite + YouTube Premium Lite")
        self.assertIn("o degrau continua na vitrine", s["substituta_texto"])

    def test_a_mensagem_diz_as_duas_coisas(self):
        self.montar()
        texto, _ = robo.montar_mensagem(HOJE, ONTEM)
        self.assertIn("saiu da vitrine", texto)
        self.assertIn("o degrau continua na vitrine, agora como "
                      "\"Vivo Lite + YouTube Premium Lite\"", texto)

    def test_cobrir_parte_das_pracas_nao_e_substituicao(self):
        """Cobrir algumas e rotacao de praca, que e outro evento - a
        mesma razao do filtro 4."""
        m = self.montar(entrante_pracas=["Sao Paulo/SP", "Rio de Janeiro/RJ"])
        s = [x for x in m["saidas"]
             if x["nome_oferta"] == "Vivo Lite Anual III"][0]
        self.assertIsNone(s["substituta"])

    def test_preco_diferente_no_mesmo_degrau_nao_e_substituicao(self):
        """Mesmo degrau por outro preco e' movimento de preco, e tem
        detector proprio: chamar de substituicao esconderia o reajuste."""
        m = self.montar(preco_entrante=49.9)
        s = [x for x in m["saidas"]
             if x["nome_oferta"] == "Vivo Lite Anual III"][0]
        self.assertIsNone(s["substituta"])

    def test_a_oferta_nao_e_substituta_de_si_mesma(self):
        """Sem esta guarda, a safra no nome faria a oferta cobrir o
        proprio degrau e nenhuma saida da Brisanet sairia qualificada."""
        banco(companhia()
              + viveu("[OUT] 500MB + NETFLIX", 108.8, 500)
              + lite(ONTEM, "[OUT] 500MB + NETFLIX", 108.8, 500)
              + lite(HOJE, "[NOV] 500MB + NETFLIX", 108.8, 500,
                     chave="Vivo|btl|500gb|simples_nov"))
        m = robo.mudancas(HOJE, ONTEM)
        saidas = [s for s in m["saidas"]]
        # a safra sai da serie: para o detector e a MESMA oferta, e por
        # isso nem chega a haver saida
        self.assertEqual(saidas, [])


class ASerieQuePisca(unittest.TestCase):

    def test_buraco_na_janela_sai_dito(self):
        faltou = [d for d in DIAS if d not in ("2026-10-17", "2026-10-18")]
        banco(companhia()
              + viveu("Vivo Lite Mensal II", 45.0, 30, dias=faltou)
              + lite(ONTEM, "Vivo Lite Mensal II", 45.0, 30))
        m = robo.mudancas(HOJE, ONTEM)
        s = [x for x in m["saidas"]
             if x["nome_oferta"] == "Vivo Lite Mensal II"][0]
        self.assertTrue(s["piscou"])
        self.assertIn("não é a primeira", s["piscou_texto"])

    def test_serie_inteira_na_janela_nao_pisca(self):
        banco(companhia()
              + viveu("Vivo Lite Mensal II", 45.0, 30)
              + lite(ONTEM, "Vivo Lite Mensal II", 45.0, 30))
        m = robo.mudancas(HOJE, ONTEM)
        s = [x for x in m["saidas"]
             if x["nome_oferta"] == "Vivo Lite Mensal II"][0]
        self.assertFalse(s["piscou"])
        self.assertIsNone(s["piscou_texto"])

    def test_a_saida_limpa_nao_ganha_ressalva_nenhuma(self):
        banco(companhia()
              + viveu("Promo Relâmpago 750", 119.9, 750)
              + lite(ONTEM, "Promo Relâmpago 750", 119.9, 750))
        texto, _ = robo.montar_mensagem(HOJE, ONTEM)
        self.assertIn("saiu da vitrine", texto)
        self.assertNotIn("o degrau continua na vitrine", texto)
        self.assertNotIn("já faltou e voltou", texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
