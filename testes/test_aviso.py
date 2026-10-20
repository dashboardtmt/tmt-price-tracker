# -*- coding: utf-8 -*-
"""O que o aviso diario precisa enxergar, e o que nao pode inventar.

Os detectores sao o produto do tracker: se eles nao virem um movimento,
ele nao existiu para quem le. Cada teste aqui corresponde a um movimento
real que o sistema deixou passar, ou a um alarme falso que ele deu.

Nada toca a rede nem o banco: as ofertas sao montadas aqui.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
from coletores import armazenamento                           # noqa: E402


def oferta(operadora="Vivo", produto="prepago", nome="Vivo Pré",
           preco=30.0, gb=25, mbps=None, praca="Sao Paulo/SP",
           chave=None, sva=None):
    return {
        "operadora": operadora, "produto": produto, "praca": praca,
        "nome_oferta": nome, "preco_promocional": preco,
        "franquia_anunciada_gb": gb, "degrau_mbps": mbps,
        "destaque": "%s GB" % gb if gb else "%s Mbps" % mbps,
        "nivel_bundle": 0, "assinatura_sva": sva,
        "chave": chave or "%s|%s|%s|simples" % (
            operadora, produto, ("%sgb" % gb) if gb else ("%smbps" % mbps)),
    }


def indexar(linhas):
    return {robo._identidade(l): l for l in linhas}


class EscadaPeloPreco(unittest.TestCase):
    """15/10/2026: a Vivo trocou o pre-pago de R$ 30 de 25 GB para 20 GB.
    Mesmo preco, um quinto a menos de internet.
    """

    def test_mesmo_preco_menos_entrega_e_evento(self):
        hoje = indexar([oferta(gb=5, preco=20.0), oferta(gb=15, preco=25.0),
                        oferta(gb=20, preco=30.0)])
        ontem = indexar([oferta(gb=5, preco=20.0), oferta(gb=15, preco=25.0),
                         oferta(gb=25, preco=30.0)])
        ev, sup = robo._grades_reorganizadas(hoje, ontem)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["saltos"], [(30.0, 25, 20)])
        self.assertIn(("Vivo", "prepago"), sup)

    def test_a_frase_diz_a_direcao_e_o_tamanho(self):
        self.assertIn("-20%", robo._mudou_a_entrega(25, 20))
        self.assertIn("+25%", robo._mudou_a_entrega(20, 25))
        self.assertEqual(robo._mudou_a_entrega(20, 20), "")


class EscadaPelaEntrega(unittest.TestCase):
    """"25 GB custava R$ 30 e passa a custar R$ 35" e o mesmo fato por
    outro angulo, e e o que aparece quando a operadora mexe no preco em
    vez da franquia."""

    def test_mesma_entrega_outro_preco_e_evento(self):
        hoje = indexar([oferta(gb=25, preco=35.0)])
        ontem = indexar([oferta(gb=25, preco=30.0)])
        ev, _ = robo._grades_reorganizadas(hoje, ontem)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["precos"], [(25, 30.0, 35.0)])


class NaoDesisteQuandoUmDegrauEhNovo(unittest.TestCase):
    """O detector antigo exigia que a lista INTEIRA de precos fosse
    identica nos dois dias, e abandonava a comparacao se um degrau novo
    aparecesse - que e exatamente o que a Vivo fez em 20/10."""

    def test_degrau_novo_nao_cancela_os_outros(self):
        hoje = indexar([oferta(gb=20, preco=30.0), oferta(gb=25, preco=35.0)])
        ontem = indexar([oferta(gb=25, preco=30.0)])
        ev, _ = robo._grades_reorganizadas(hoje, ontem)
        # o R$30 mudou de 25 para 20 GB; o R$35 e novo e nao atrapalha
        self.assertTrue(any(e["saltos"] == [(30.0, 25, 20)] for e in ev))


class OfertaQueSomeNaoEPrecoQueSobe(unittest.TestCase):
    """17->18/10: o "Vivo Total Essencial" de R$ 100 faltou numa praca e
    o mais barato de 500 Mega virou o "Total Pro" de R$ 160. O detector
    acusou alta de 60% onde nao houve mudanca de preco."""

    def test_troca_de_ocupante_do_degrau_nao_e_reajuste(self):
        hoje = indexar([oferta(produto="combo", nome="Vivo Total Pro",
                               preco=160.0, gb=None, mbps=500)])
        ontem = indexar([
            oferta(produto="combo", nome="Vivo Total Essencial",
                   preco=100.0, gb=None, mbps=500),
            oferta(produto="combo", nome="Vivo Total Pro",
                   preco=160.0, gb=None, mbps=500,
                   chave="Vivo|combo|500mbps|outro")])
        ev, _ = robo._grades_reorganizadas(hoje, ontem)
        self.assertEqual(ev, [])


class ColisaoAvisaMasNaoCancela(unittest.TestCase):
    """Duas ofertas com a mesma chave, praca e nome ficam
    indistinguiveis: uma sobrescreve a outra. Sao 20 por dia na Vivo.

    A trava que eu criei mandava o recado pelo canal de erro, e erro
    cancela a comparacao inteira - 20 ofertas apagaram as outras 1.640.
    """

    def test_identidade_colidida_e_denunciada(self):
        a = oferta(produto="combo", nome="Vivo Família 2 + TV", preco=290.0,
                   gb=None, mbps=700)
        b = dict(a, preco_promocional=390.0)
        self.assertEqual(robo._identidade(a), robo._identidade(b))

    def test_a_safra_no_nome_nao_quebra_o_pareamento(self):
        # a NuCel carimba o mes no nome: "[SET] OFT..." vira "[OUT] OFT..."
        a = oferta(operadora="NuCel", nome="[SET] OFT NC PF PROMO 12M 700M")
        b = oferta(operadora="NuCel", nome="[OUT] OFT NC PF PROMO 12M 700M")
        self.assertEqual(robo._identidade(a), robo._identidade(b))


class ComposicaoEmPortugues(unittest.TestCase):
    """"saiu: 040059 / entrou: 100023" nao diz nada a quem le: os codigos
    SVA nao tem dicionario publico."""

    def test_cada_caso_tem_frase_propria(self):
        self.assertEqual(robo._trocou(["a"], ["b"]),
                         "trocou 1 serviço incluso")
        self.assertEqual(robo._trocou(["a", "b"], []),
                         "perdeu 2 serviços inclusos")
        self.assertEqual(robo._trocou([], ["a"]),
                         "ganhou 1 serviço incluso")

    def test_concordancia_no_caso_assimetrico(self):
        # "sairam 2 e entraram 1" nao existe
        frase = robo._trocou(["a", "b"], ["c"])
        self.assertIn("entrou 1", frase)
        self.assertNotIn("entraram 1", frase)


class CategoriaTemNome(unittest.TestCase):
    """"Vivo - Familia 2 + TV" nao diz se aquilo e combo, fibra ou
    pos-pago, e o nome da oferta nem sempre entrega."""

    def test_cada_produto_tem_nome_de_gente(self):
        self.assertEqual(robo._categoria({"produto": "prepago"}), "Pré-pago")
        self.assertEqual(robo._categoria({"produto": "btl"}), "Below-the-line")
        self.assertEqual(robo._categoria({"produto": "movel"}), "Pós-pago")

    def test_produto_desconhecido_nao_quebra(self):
        self.assertEqual(robo._categoria({"produto": "xpto"}), "xpto")
        self.assertEqual(robo._categoria({}), "—")


if __name__ == "__main__":
    unittest.main(verbosity=2)
