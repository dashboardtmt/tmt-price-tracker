# -*- coding: utf-8 -*-
u"""O relatorio tem de ter o que a mensagem manda ler nele.

A VARREDURA DE 11/11/2026 achou duas promessas vazias do mesmo tipo. A
primeira o usuario pegou sozinho: a mensagem dizia "ganhou 1 servico
incluso" e o PDF nao dizia qual. A segunda estava escondida melhor. Desde
10/11 a mensagem escreve "e mais N trocas de velocidade pelo mesmo preco
no relatorio", e o evento chegava ao PDF dentro de dados - mas nenhum
bloco o desenhava. Em 27/10 o relatorio dizia so que a Claro 750 Mega
tinha caido de preco; as tres trocas de velocidade do dia existiam so na
mensagem.

E O PARAGRAFO DA CONFERENCIA FALAVA COM O CODIGO, nao com quem le: saia
"composicao (a assinatura SVA nao esta na janela crua); grades (a escada
olha a serie inteira, nao dois dias)" - nome de variavel e anotacao sem
acento, num PDF que circula fora da equipe.

Mede no PDF de verdade, gerado pelo caminho de producao e lido de volta.
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

PRACAS = ["Sao Paulo/SP", "Rio de Janeiro/RJ"]


def claro(nome, preco, mbps, data, produto):
    return [oferta(operadora="Claro", produto=produto, nome=nome,
                   preco=preco, gb=None, mbps=mbps, praca=p, data=data)
            for p in PRACAS]


def _pdf(d):
    caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
    relatorio.gerar(d, {}, caminho)
    return " ".join(" ".join((pg.extract_text() or "").split())
                    for pg in pypdf.PdfReader(caminho).pages)


@unittest.skipIf(relatorio is None, "reportlab ou pypdf ausente")
class ATrocaDeVelocidadeNoRelatorio(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def _quatro_trocas(self):
        u"""Quatro ofertas trocando de velocidade pelo mesmo preco: a
        mensagem mostra tres e manda a quarta para o relatorio."""
        ontem, hoje = [], []
        for i, (preco, de, para) in enumerate(((99.90, 600, 750),
                                                (119.90, 500, 600),
                                                (139.90, 700, 800),
                                                (159.90, 800, 1000))):
            ontem += claro("Claro Fibra %d Mega Linha %d" % (de, i), preco,
                           de, ONTEM, "fibra")
            hoje += claro("Claro Fibra %d Mega Linha %d" % (para, i), preco,
                          para, HOJE, "fibra")
        return ontem, hoje

    def test_a_quarta_troca_esta_onde_a_mensagem_manda(self):
        ontem, hoje = self._quatro_trocas()
        t = montar(ontem, hoje)
        self.assertIn(u"e mais 1 troca de velocidade pelo mesmo preço no "
                      u"relatório", t)
        texto = _pdf(dados(ontem, hoje))
        self.assertIn(u"Mesmo preço, outra velocidade", texto)
        # as quatro, e nao so as tres da mensagem
        for nome in ("Linha 0", "Linha 1", "Linha 2", "Linha 3"):
            with self.subTest(oferta=nome):
                self.assertIn(nome, texto)

    def test_o_bloco_diz_antes_e_depois(self):
        ontem, hoje = self._quatro_trocas()
        texto = _pdf(dados(ontem, hoje))
        self.assertIn("800 Mega 1000 Mega", texto)

    def test_dia_sem_troca_diz_que_nao_houve(self):
        u"""Secao que some e secao vazia sao coisas diferentes para quem
        le: a frase de vazio diz que se olhou."""
        texto = _pdf(dados(claro("Claro Fibra 600 Mega", 99.90, 600, ONTEM,
                                 "fibra"),
                           claro("Claro Fibra 600 Mega", 99.90, 600, HOJE,
                                 "fibra")))
        self.assertIn(u"Nenhuma troca de velocidade pelo mesmo preço "
                      u"identificada.", texto)


@unittest.skipIf(relatorio is None, "reportlab ou pypdf ausente")
class ParaCadaCategoriaUmaFrase(unittest.TestCase):
    u"""O paragrafo "fora da conferencia" no idioma de quem le."""

    def test_toda_categoria_fora_tem_traducao(self):
        u"""Categoria nova no auditor sem entrada aqui cairia no texto
        cru - nome de variavel no PDF, calado."""
        self.assertEqual(set(auditor.FORA), set(relatorio.FORA_NO_RELATORIO))

    def test_o_pdf_nao_mostra_o_nome_interno(self):
        d = dict(dados([], []), nao_auditado=dict(auditor.FORA))
        texto = _pdf(d)
        self.assertIn(u"Fora da conferência, por desenho.", texto)
        # A ANOTACAO INTERNA NUNCA CHEGA AO PDF. Testar so o nome da
        # chave nao serve: "leitura" e palavra comum, e o titulo certo
        # ("Alterações atribuíveis à leitura (...)") a contem.
        for interno, motivo in auditor.FORA.items():
            with self.subTest(categoria=interno):
                self.assertNotIn(motivo, texto)
        for nome in ("composicao (", "grades (", "renomeadas (",
                     "voltaram ("):
            self.assertNotIn(nome, texto)
        self.assertNotIn(" nao ", texto)


if __name__ == "__main__":
    unittest.main()
