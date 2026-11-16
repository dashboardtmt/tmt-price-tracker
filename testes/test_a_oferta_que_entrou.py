# -*- coding: utf-8 -*-
u"""A oferta que entrou na vitrine - o espelho da que saiu.

PEDIDO DE QUEM LE, EM 16/11/2026, depois da varredura das mensagens: em
24/10 a Brisanet pos uma fibra de 800 MB a R$ 89,90 - mais rapida e mais
barata que a de 700 - e nem a mensagem nem o PDF disseram nada. O tracker
via o que mudava e o que saia; lancamento nao tinha detector.

A DEFINICAO INGENUA MENTE. "Serie que nao estava ontem" rende 86
lancamentos em 48 dias, e quase nenhum e. Cada classe abaixo prende um
filtro, com o caso real que o motivou:

  1. praca sem coleta ontem: a Claro Flex "entrava" em 07/11, depois de
     um dia de coleta falhada;
  2. volta dentro da janela: os combos da Brisanet sumiram de 31/10 a
     03/11 e voltaram em 04/11;
  3. renome: "Vivo Fibra" virou "Vivo Fibra Com Wi-Fi 6" em 14/11;
  4. cobertura: em 04/11 a fibra da TIM foi de 1 nome para 12, porque a
     coleta deixou de ler a pagina-hub;
  5. o universo e o do produto: a Claro Geforce saia "em 20 de 21",
     contando a praca da Claro Flex, onde a Claro nao vende Controle.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auditor                                                # noqa: E402
from _apoio import HOJE, ONTEM, dados, montar, oferta, sem_declaracao  # noqa: E402

try:
    import pypdf
    import relatorio
except ImportError:                                           # pragma: no cover
    relatorio = None

PRACAS = ["Sao Paulo/SP", "Rio de Janeiro/RJ", "Curitiba/PR"]
DENTRO_DA_JANELA = "2026-10-18"


def fibra(nome, preco, mbps, data, pracas=PRACAS, operadora="Vivo",
          produto="fibra", chave=None):
    return [oferta(operadora=operadora, produto=produto, nome=nome,
                   preco=preco, gb=None, mbps=mbps, praca=p, data=data,
                   chave=chave)
            for p in pracas]


def fundo(data, pracas=PRACAS):
    u"""A fibra que ja existia: o produto tem nome antes do lancamento, e
    a praca foi coletada nos dois dias."""
    return fibra("Vivo Fibra 500 Mega", 120.0, 500, data, pracas)


class OLancamentoSai(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def test_a_oferta_nova_sai_com_preco_e_entrega(self):
        t = montar(fundo(ONTEM),
                   fundo(HOJE) + fibra("Vivo Fibra 1 Giga", 150.0, 1000, HOJE))
        self.assertIn(u"Vivo Fibra 1 Giga", t)
        self.assertIn(u"entrou na vitrine a 150,00, com 1000 Mbps", t)
        self.assertIn(u"em todas as 3 praças", t)
        self.assertIn(u"1 mudança hoje", t)

    def test_entra_no_pdf(self):
        if relatorio is None:
            self.skipTest("reportlab ou pypdf ausente")
        d = dados(fundo(ONTEM),
                  fundo(HOJE) + fibra("Vivo Fibra 1 Giga", 150.0, 1000, HOJE))
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = " ".join(" ".join((p.extract_text() or "").split())
                         for p in pypdf.PdfReader(caminho).pages)
        self.assertIn(u"Ofertas que entraram na vitrine", texto)
        self.assertIn(u"Vivo Fibra 1 Giga", texto)


class OQueNaoELancamento(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def test_volta_dentro_da_janela_nao_entra(self):
        u"""Estava em 18/10, faltou em 20/10, voltou em 21/10."""
        t = montar(fundo(ONTEM),
                   fundo(HOJE) + fibra("Vivo Fibra 1 Giga", 150.0, 1000, HOJE),
                   extras=fibra("Vivo Fibra 1 Giga", 150.0, 1000,
                                DENTRO_DA_JANELA))
        self.assertNotIn("entrou na vitrine", t)

    def test_praca_sem_coleta_ontem_nao_entra(self):
        u"""Ontem ninguem olhou o Rio: o que aparece la hoje nao e novo."""
        ontem = fundo(ONTEM, pracas=["Sao Paulo/SP"])
        hoje = (fundo(HOJE, pracas=["Sao Paulo/SP"])
                + fibra("Vivo Fibra 1 Giga", 150.0, 1000, HOJE,
                        pracas=["Rio de Janeiro/RJ"]))
        t = montar(ontem, hoje)
        self.assertNotIn("entrou na vitrine", t)

    def test_renome_nao_entra(self):
        u"""O caso de 14/11: mesma chave, uma candidata de cada lado."""
        chave = "Vivo|fibra|500mbps|simples"
        t = montar(fibra("Vivo Fibra", 150.0, 500, ONTEM, chave=chave),
                   fibra("Vivo Fibra Com Wi-Fi 6", 150.0, 500, HOJE,
                         chave=chave))
        # o renome tem de ter saido, senao a ausencia da entrada nao mede
        self.assertIn("mudou de nome", t)
        self.assertNotIn("entrou na vitrine", t)

    def test_cobertura_nova_nao_e_lancamento(self):
        u"""O caso da TIM em 04/11: mais nomes novos que os que havia."""
        hoje = (fundo(HOJE)
                + fibra("Vivo Fibra 600 Mega", 110.0, 600, HOJE)
                + fibra("Vivo Fibra 700 Mega", 130.0, 700, HOJE))
        d = dados(fundo(ONTEM), hoje)
        self.assertEqual(d.get("entradas") or [], [])
        self.assertEqual(
            [(x["operadora"], x["produto"], x["novas"], x["havia"])
             for x in d.get("passou_a_ler") or []],
            [("Vivo", "fibra", 2, 1)])
        self.assertNotIn("entrou na vitrine", montar(fundo(ONTEM), hoje))


class OUniversoEODoProduto(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def test_praca_de_outro_produto_nao_entra_na_conta(self):
        u"""O caso da Claro Geforce: a Claro e coletada numa praca a mais,
        a da Claro Flex - que vende below-the-line, e nao fibra."""
        flex = [oferta(operadora="Vivo", produto="btl", nome="Vivo Lite",
                       preco=30.0, gb=30, praca="Brasil/BR", data=d)
                for d in (ONTEM, HOJE)]
        t = montar(fundo(ONTEM),
                   fundo(HOJE) + fibra("Vivo Fibra 1 Giga", 150.0, 1000, HOJE),
                   extras=flex)
        self.assertIn(u"em todas as 3 praças", t)
        self.assertNotIn(u"3 de 4", t)


class OAuditorConfereAEntrada(unittest.TestCase):

    def test_oferta_que_ja_estava_ontem_e_recusada(self):
        u"""O auditor re-deduz das linhas cruas: se a oferta estava ontem
        na praca, a entrada nao se sustenta ali."""
        ontem = fibra("Vivo Fibra 1 Giga", 150.0, 1000, ONTEM)
        hoje = fibra("Vivo Fibra 1 Giga", 150.0, 1000, HOJE)
        evento = {"operadora": "Vivo", "produto": "fibra",
                  "nome_oferta": "Vivo Fibra 1 Giga", "pracas": PRACAS}
        idx_h = auditor._indice(hoje, False)
        idx_o = auditor._indice(ontem, False)
        coletadas_ontem = {("Vivo", p) for p in PRACAS}
        boas, incertas = auditor._pracas_da_entrada(evento, idx_h, idx_o,
                                                    coletadas_ontem)
        self.assertEqual(boas, set())
        self.assertEqual(incertas, set())

    def test_entrada_de_verdade_passa(self):
        hoje = fibra("Vivo Fibra 1 Giga", 150.0, 1000, HOJE)
        evento = {"operadora": "Vivo", "produto": "fibra",
                  "nome_oferta": "Vivo Fibra 1 Giga", "pracas": PRACAS}
        boas, _ = auditor._pracas_da_entrada(
            evento, auditor._indice(hoje, False), auditor._indice([], False),
            {("Vivo", p) for p in PRACAS})
        self.assertEqual(boas, set(PRACAS))


if __name__ == "__main__":
    unittest.main()
