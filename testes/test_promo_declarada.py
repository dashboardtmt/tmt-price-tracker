# -*- coding: utf-8 -*-
u"""Por quanto tempo o preco vale, quando a fonte diz.

Duas operadoras declaram isso e as duas estavam sendo lidas pela metade.

BRISANET - a nota de varios degraus guardava o do MEIO. Mes e valor eram
lidos por dois re.search independentes, o primeiro de cada:

    "No 13o mes o valor sera R$ 109,90"
        -> 12 meses, R$ 109,90                          certo

    "Do 7o ao 12o mes R$ 89,90. No 13o mes o valor sera R$ 109,90"
        -> 6 meses, R$ 89,90                            o degrau do meio

Nenhum dos dois numeros e absurdo, e e por isso que nao da para pegar
por contradicao: medi as 2.871 linhas da Brisanet na serie e nao ha
nenhuma inconsistencia entre meses, preco de hoje e preco depois. Em
24/10/2026 as dez notas de Fortaleza tem um degrau so - a guarda entra
latente, e a leitura das dez nao muda.

TIM FIT - a janela de 12 meses nao era lida. Medido nas quatro etiquetas
da Anatel em 24/10/2026:

    Anual 2.0    "R$30 por mes, durante 12 meses (R$360 no ano)"
    Anual 1.0    "R$20 por mes, durante 12 meses (R$240 no ano)"
    Mensal 2.0   "R$45 por mes"
    Mensal 1.0   "R$35 por mes"

As quatro gravavam meses_desconto = None, e preco_cheio igual ao
promocional - o que AFIRMA que nao ha desconto num preco que o documento
diz que dura doze meses. O FIT e a linha de defesa da TIM e o tracker a
acompanha para ver o PISO do mercado: com os R$ 30 da Anual entrando
como preco de regime, o piso aparecia 33% abaixo do que ela cobra sem
compromisso - o Mensal equivalente custa R$ 45.
"""
import unittest

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import brisanet, tim_fit  # noqa: E402


class ANotaDaBrisanetTemVariosDegraus(unittest.TestCase):

    def test_um_degrau_so_le_como_antes(self):
        self.assertEqual(
            brisanet.fim_da_promocao(u"No 13º mês o valor será R$ 109,90"),
            (12, 109.90))

    def test_o_ordinal_com_espaco_tambem(self):
        """A Brisanet escreve "No 13 º mês" em algumas notas."""
        self.assertEqual(
            brisanet.fim_da_promocao(u"No 13 º mês o valor será R$ 124,80"),
            (12, 124.80))

    def test_dois_degraus_valem_o_ultimo(self):
        """O de regime, nao o intermediario."""
        self.assertEqual(
            brisanet.fim_da_promocao(
                u"Do 7º ao 12º mês R$ 89,90. No 13º mês o valor "
                u"será R$ 109,90"),
            (12, 109.90))

    def test_tres_degraus_tambem(self):
        self.assertEqual(
            brisanet.fim_da_promocao(
                u"Do 1º ao 6º mês R$ 79,90, do 7º ao 12º mês R$ 89,90. "
                u"No 13º mês R$ 109,90"),
            (12, 109.90))

    def test_a_ordem_na_frase_nao_decide(self):
        """Vale o maior mes, nao o ultimo escrito: nota fora de ordem
        continua dando o degrau de regime."""
        self.assertEqual(
            brisanet.fim_da_promocao(
                u"No 13º mês R$ 109,90; do 7º ao 12º mês R$ 89,90"),
            (12, 109.90))

    def test_mes_sem_preco_nao_perde_o_mes(self):
        """Nota que nao pareia cai na leitura antiga em vez de jogar
        fora o que dava."""
        self.assertEqual(
            brisanet.fim_da_promocao(u"No 13º mês o preço sobe"),
            (12, None))

    def test_preco_sem_mes_nao_perde_o_preco(self):
        self.assertEqual(
            brisanet.fim_da_promocao(u"R$ 99,90 a partir do ano que vem"),
            (None, 99.90))

    def test_nota_vazia(self):
        self.assertEqual(brisanet.fim_da_promocao(""), (None, None))
        self.assertEqual(brisanet.fim_da_promocao(None), (None, None))

    def test_o_degrau_nao_atravessa_o_ponto(self):
        """O par tem de estar na MESMA oracao: sem isso o mes de um
        degrau casaria com o preco do seguinte."""
        self.assertEqual(
            brisanet.fim_da_promocao(u"No 13º mês acaba. R$ 500,00 de multa"),
            (12, 500.0))


class AEtiquetaDoFitDizPorQuantoTempo(unittest.TestCase):

    def _ler(self, preco_txt, nome=u"TIM CONTROLE FIT Anual 2.0"):
        t = u"%s\nPreço %s\nFranquia 20 GB\n" % (nome, preco_txt)
        o, erro = tim_fit.da_etiqueta(t)
        self.assertIsNone(erro, erro)
        return o

    def test_a_janela_de_doze_meses_entra(self):
        o = self._ler(u"R$30 por mês, durante 12 meses (R$360 no ano)")
        self.assertEqual(o["meses_desconto"], 12)
        self.assertEqual(o["preco_promocional"], 30.0)

    def test_preco_com_prazo_nao_e_preco_de_tabela(self):
        """A etiqueta da um preco so e diz que ele dura doze meses:
        chamar o mesmo numero de preco cheio afirma o que o documento
        nao diz (decisao 9)."""
        o = self._ler(u"R$30 por mês, durante 12 meses (R$360 no ano)")
        self.assertIsNone(o["preco_cheio"])

    def test_sem_janela_o_preco_e_o_preco(self):
        o = self._ler(u"R$45 por mês",
                      nome=u"TIM CONTROLE FIT Mensal 2.0")
        self.assertIsNone(o["meses_desconto"])
        self.assertEqual(o["preco_cheio"], 45.0)
        self.assertEqual(o["preco_promocional"], 45.0)

    def test_o_preco_depois_da_janela_fica_vazio(self):
        """A etiqueta nao diz quanto custa depois, e inventar seria pior
        que nao ter."""
        o = self._ler(u"R$30 por mês, durante 12 meses (R$360 no ano)")
        self.assertIsNone(o["preco_pos_promocao"])

    def test_o_total_anual_confere_a_leitura(self):
        """A redundancia que o documento publica e a chance mais barata
        de pegar leitura torta: 30 x 12 = 360."""
        o = self._ler(u"R$30 por mês, durante 12 meses (R$360 no ano)")
        self.assertIsNone(o.get("avisos_oferta"))

    def test_e_avisa_quando_o_total_anual_nao_fecha(self):
        o = self._ler(u"R$30 por mês, durante 12 meses (R$400 no ano)")
        self.assertTrue(o.get("avisos_oferta"), "o total anual nao fecha")
        # a ressalva tem duas formas desde 25/10/2026: o numero esta no
        # texto longo, que e o do relatorio
        curto, longo = tim_fit.apps._duas_formas(o["avisos_oferta"][0])
        self.assertEqual(curto, "o total do ano n\u00e3o fecha com pre\u00e7o x meses")
        self.assertIn("400", longo)

    def test_janela_sem_total_anual_nao_inventa_conferencia(self):
        o = self._ler(u"R$30 por mês, durante 12 meses")
        self.assertEqual(o["meses_desconto"], 12)
        self.assertIsNone(o.get("avisos_oferta"))

    def test_etiqueta_sem_preco_recusa(self):
        t = u"TIM CONTROLE FIT Anual 2.0\nFranquia 20 GB\n"
        o, erro = tim_fit.da_etiqueta(t)
        self.assertIsNone(o)
        self.assertIn("sem nome ou sem preco", erro)


if __name__ == "__main__":
    unittest.main(verbosity=2)
