# -*- coding: utf-8 -*-
"""O vigia tem de achar o que as varreduras acharam na mao.

Cada teste aqui reproduz um achado real do mes, com o numero real. Se o
vigia nao pegar isso, ele nao serve para nada - e nesse caso e melhor
nao existir do que dar falsa sensacao de cobertura.

E os testes de silencio importam tanto quanto: vigia que grita todo dia
vira ruido, e depois ninguem le nem quando ele acerta.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vigia                                                  # noqa: E402


def oferta(operadora="Vivo", produto="movel", nome="Vivo Pós", preco=150.0,
           gb=60, mbps=None, praca="Sao Paulo/SP", chave=None):
    return {"operadora": operadora, "produto": produto, "praca": praca,
            "nome_oferta": nome, "preco_promocional": preco,
            "franquia_anunciada_gb": gb, "degrau_mbps": mbps,
            "chave": chave or "%s|%s|x|simples" % (operadora, produto)}


def dia_normal(n=30, operadora="Vivo"):
    return [oferta(operadora=operadora, nome="Oferta %d" % i,
                   preco=100.0 + i, chave="%s|movel|%d|s" % (operadora, i))
            for i in range(n)]


def historico(dias=5, n=30, operadora="Vivo"):
    return {"2026-10-%02d" % (10 + i): dia_normal(n, operadora)
            for i in range(dias)}


def graves(lista):
    return [t for g, t in lista if g == "grave"]


def atencoes(lista):
    return [t for g, t in lista if g == "atencao"]


class PrecoFantasma(unittest.TestCase):
    """07/10: tres cards de Claro Controle gravados a R$ 24,60, que e o
    preco avulso do Disney+ citado no proprio card."""

    def test_o_preco_do_disney_virando_preco_do_plano(self):
        """R$ 24,60 nao e um preco impossivel - a Vivo Pre custa R$ 20.

        O que denunciava aquele valor era ser -75% do que a MESMA oferta
        custava no dia anterior. Limite fixo nunca pegaria; o detector
        de salto pega.

        E TEM DE SER GRAVE, nao atencao: atencao fica no relatorio, e um
        preco que nao e preco de plano precisa chegar a mensagem - foi
        o defeito que gerou este modulo, e ele passaria em silencio no
        canal onde alguem olha.
        """
        hist = historico()
        hoje = dia_normal()
        # a oferta que no historico custa R$ 100 aparece a R$ 24,60
        hoje[0]["preco_promocional"] = 24.60
        r = vigia.achados(hoje, hist)
        self.assertTrue(any("salto" in t for t in graves(r)), r)
        self.assertIn("salto", vigia.resumo(r))

    def test_preco_impossivel_de_verdade_e_grave(self):
        hoje = dia_normal() + [oferta(nome="Lixo", preco=0.99,
                                      chave="Vivo|movel|zz|s")]
        r = vigia.achados(hoje, historico())
        self.assertTrue(any("fora da faixa" in t for t in graves(r)))

    def test_preco_absurdo_para_cima_tambem(self):
        hoje = dia_normal() + [oferta(nome="Aparelho", preco=12999.0)]
        self.assertTrue(any("fora da faixa" in t for t in graves(vigia.achados(hoje, historico()))))

    def test_preco_normal_nao_e_denunciado(self):
        r = vigia.achados(dia_normal(), historico())
        self.assertEqual([t for t in graves(r) if "faixa" in t], [])


class EntregaSumida(unittest.TestCase):
    """119 linhas por dia da Brisanet sem velocidade: a API manda numero
    puro e a leitura exigia unidade."""

    def test_operadora_inteira_sem_entrega_e_grave(self):
        hoje = dia_normal() + [
            oferta(operadora="Brisanet", produto="fibra", nome="F%d" % i,
                   gb=None, mbps=None, chave="Brisanet|fibra|%d|s" % i)
            for i in range(12)]
        r = vigia.achados(hoje, historico())
        self.assertTrue(any("sem velocidade nem franquia" in t for t in graves(r)))

    def test_uma_ou_outra_sem_entrega_nao_alarma(self):
        hoje = dia_normal() + [oferta(nome="Avulsa", gb=None, mbps=None,
                                      chave="Vivo|movel|zz|s")]
        self.assertEqual([t for t in graves(vigia.achados(hoje, historico()))
                          if "sem velocidade" in t], [])


class OfertasIndistinguiveis(unittest.TestCase):
    """As duas "Vivo Familia 2 + TV" com a mesma chave, praca e nome:
    20 por dia que o comparador nunca viu."""

    def test_par_colidido_e_denunciado(self):
        a = oferta(nome="Vivo Família 2 + TV", preco=290.0, chave="Vivo|combo|700|familia")
        b = oferta(nome="Vivo Família 2 + TV", preco=390.0, chave="Vivo|combo|700|familia")
        r = vigia.achados(dia_normal() + [a, b], historico())
        self.assertTrue(any("indistinguiveis" in t for t in atencoes(r)))

    def test_dia_limpo_nao_denuncia(self):
        self.assertEqual([t for t in atencoes(vigia.achados(dia_normal(), historico()))
                          if "indistinguiveis" in t], [])


class VolumeDeOfertas(unittest.TestCase):
    """Operadora que some ou encolhe e coleta quebrada, nao mercado."""

    def test_operadora_que_sumiu_e_grave(self):
        hist = historico(operadora="Claro")
        r = vigia.achados(dia_normal(operadora="Vivo"), hist)
        self.assertTrue(any("Claro nao aparece hoje" in t for t in graves(r)))

    def test_queda_grande_e_atencao(self):
        r = vigia.achados(dia_normal(n=10), historico(n=30))
        self.assertTrue(any("contra 30 tipicos" in t for t in atencoes(r)))

    def test_variacao_pequena_nao_alarma(self):
        # vitrine muda; cair de 30 para 27 e vida normal
        r = vigia.achados(dia_normal(n=27), historico(n=30))
        self.assertEqual([t for t in atencoes(r) if "tipicos" in t], [])

    def test_crescer_nao_e_problema(self):
        r = vigia.achados(dia_normal(n=45), historico(n=30))
        self.assertEqual([t for t in atencoes(r) if "tipicos" in t], [])


class SaltoDePreco(unittest.TestCase):

    def test_preco_que_dobra_e_grave(self):
        hist = historico()
        hoje = dia_normal()
        hoje[0]["preco_promocional"] = 100.0 * 2
        r = vigia.achados(hoje, hist)
        self.assertTrue(any("salto" in t for t in graves(r)), r)

    def test_salto_de_reajuste_fica_no_relatorio(self):
        """+60% e muito, mas e um numero que operadora pratica - e o
        comparador ja reporta isso com nome e praca. Virar manchete
        todo mes gastaria a credibilidade da linha "Conferir"."""
        hoje = dia_normal()
        hoje[0]["preco_promocional"] = 160.0
        r = vigia.achados(hoje, historico())
        self.assertTrue(any("salto" in t for t in atencoes(r)), r)
        self.assertEqual([t for t in graves(r) if "salto" in t], [])

    def test_reajuste_pequeno_nao_vira_ruido(self):
        hoje = dia_normal()
        hoje[0]["preco_promocional"] = 110.0
        self.assertEqual([t for t in atencoes(vigia.achados(hoje, historico()))
                          if "salto" in t], [])


class DiaSemDado(unittest.TestCase):

    def test_sem_captura_nenhuma_e_grave(self):
        r = vigia.achados([], historico())
        self.assertEqual(graves(r), ["nenhuma captura hoje"])


class Silencio(unittest.TestCase):
    """Vigia que grita todo dia vira ruido."""

    def test_dia_normal_nao_produz_nada(self):
        self.assertEqual(vigia.achados(dia_normal(), historico()), [])

    def test_a_vaga_da_mensagem_vai_para_o_mais_grave(self):
        """RESSALVA 5 DO VEREDITO. A mensagem tem uma vaga, e qual achado
        a ocupava vinha da ordem em que "achados" os produz - ordem de
        codigo e nada mais. Por 18 dos 21 dias medidos o primeiro era a
        Brisanet sem velocidade, defeito de leitura ja corrigido que se
        repetia todo dia, e um achado novo entrava atras dele. Segundo
        plano e a posicao de onde o preco fantasma ja ficou calado."""
        r = vigia.resumo([
            ("grave", "Brisanet: 119 de 119 ofertas sem velocidade"),
            ("grave", "3 oferta(s) com preco fora da faixa de varejo"),
            ("grave", "Claro nao aparece hoje (tipico: 364 ofertas)")])
        self.assertTrue(r.startswith("Conferir: Claro nao aparece hoje"), r)
        self.assertIn("mais 2 ponto(s)", r)

    def test_e_a_ordem_nao_depende_de_como_chegou(self):
        baralhado = [
            ("grave", "nenhuma captura hoje"),
            ("grave", "Brisanet: 119 de 119 ofertas sem velocidade")]
        for ordem in (baralhado, list(reversed(baralhado))):
            self.assertTrue(vigia.resumo(ordem).startswith(
                "Conferir: nenhuma captura hoje"), ordem)

    def test_resumo_vazio_quando_nao_ha_grave(self):
        self.assertEqual(vigia.resumo([("atencao", "algo pequeno")]), "")
        self.assertIn("Conferir", vigia.resumo([("grave", "algo serio")]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
