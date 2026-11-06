# -*- coding: utf-8 -*-
u"""O card do Claro Flex, lido do texto que a pagina renderiza.

EM 06/11/2026 O FLEX VOLTOU VAZIO. "nenhum card reconhecido - o layout
do Flex mudou", nas quatro ofertas, e a mensagem do dia saiu com
"COLETA INCOMPLETA - Claro Flex em 0 de 1 pracas". O que mudou na
pagina foi UM CARACTERE: "Por R$ 34,90" virou "Por: R$ 34,90". O regex
exigia a palavra colada ao R$, nao achou, e as quatro ofertas sairam
da base.

E A SEGUNDA VEZ. Em 23/10/2026 "30GB do plano" virou "30GB plano" e a
franquia garantida inflou para a anunciada. O coletor nao tinha teste
nenhum: o parser dele so era exercitado pela propria pagina, uma vez
por dia, as 7h da manha, e o aviso chegava depois do estrago.

O QUE ESTE ARQUIVO PRENDE. As duas redacoes da pagina - a de antes e a
de hoje - leem as mesmas quatro ofertas, com o mesmo preco cheio e a
mesma franquia contratual. Endurecer o regex de novo quebra aqui, e
nao no Telegram.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import claro_flex                             # noqa: E402

# O texto de 06/11/2026, copiado do innerText da pagina ao vivo.
HOJE = (
    "Claro flex móvel Resolva tudo pelo app, sem burocracia, sem "
    "fidelidade. "
    "Ative agora com eSIM 40GB 30GB plano + 5GB bônus redes sociais + "
    "5GB bônus Apps inclusos no bônus para redes sociais App Ilimitado "
    "VIRAFLEX10 DESCONTO DE 10 REAIS NO PRIMEIRO MÊS De: R$ 44,90 "
    "Por: R$ 34,90 no primeiro mês Plano mensal Plano anual Quero esse "
    "Mais detalhes "
    "Ative agora com eSIM 45GB 35GB plano + 5GB bônus redes sociais + "
    "5GB bônus Apps inclusos no bônus para redes sociais App Ilimitado "
    "VIRAFLEX10 DESCONTO DE 10 REAIS NO PRIMEIRO MÊS De: R$ 59,90 "
    "Por: R$ 49,90 no primeiro mês Plano mensal Plano anual Quero esse "
    "Mais detalhes "
    "Ative agora com eSIM 50GB 40GB plano + 5GB bônus redes sociais + "
    "5GB bônus Apps inclusos no bônus para redes sociais App Ilimitado "
    "VIRAFLEX10 DESCONTO DE 10 REAIS NO PRIMEIRO MÊS De: R$ 69,90 "
    "Por: R$ 59,90 no primeiro mês Plano mensal Plano anual Quero esse "
    "Mais detalhes "
    "PASSAPORTE 60GB 60GB livre para você usar e navegar como quiser "
    "Mais de 40 países das Américas para você utilizar seu Flex. Apps "
    "Ilimitados VIRAFLEX20 DESCONTO DE 20 REAIS NO PRIMEIRO MÊS "
    "De: R$ 119,90 Por: R$ 99,90 no primeiro mês Plano mensal Plano "
    "anual Quero esse Mais detalhes")

# A mesma pagina antes de 06/11: "Por" sem dois-pontos.
ANTES = HOJE.replace("Por: R$", "Por R$")


class OFlexLeAsQuatroOfertas(unittest.TestCase):

    def test_a_redacao_de_hoje_le_as_quatro(self):
        """Com dois-pontos depois do "Por" - o caractere que zerou a
        coleta de 06/11."""
        ofertas = claro_flex.extrair(HOJE)
        self.assertEqual(len(ofertas), 4, [o["nome_oferta"] for o in ofertas])

    def test_a_redacao_antiga_continua_lendo(self):
        """O conserto aceita as duas, porque a pagina ja voltou atras
        uma vez: em 23/10 ela tirou o "do" de "30GB do plano"."""
        self.assertEqual(len(claro_flex.extrair(ANTES)), 4)

    def test_o_preco_que_entra_e_o_cheio(self):
        """Decisao 9: o preco com cupom e so o do primeiro mes, e nao
        pode ser o que a serie compara."""
        por_gb = {o["franquia_anunciada_gb"]: o
                  for o in claro_flex.extrair(HOJE)}
        self.assertEqual(por_gb[40]["preco_promocional"], 44.90)
        self.assertEqual(por_gb[40]["preco_primeiro_mes"], 34.90)
        self.assertEqual(por_gb[50]["preco_promocional"], 69.90)
        self.assertEqual(por_gb[60]["preco_promocional"], 119.90)

    def test_a_franquia_garantida_sai_do_card_e_nao_da_anunciada(self):
        """Dos 40 GB anunciados, 30 sao do plano: os outros 10 sao bonus
        de rede social e Claro Day, que podem cair."""
        por_gb = {o["franquia_anunciada_gb"]: o
                  for o in claro_flex.extrair(HOJE)}
        self.assertEqual(por_gb[40]["franquia_contratual_gb"], 30)
        self.assertEqual(por_gb[45]["franquia_contratual_gb"], 35)
        self.assertEqual(por_gb[50]["franquia_contratual_gb"], 40)

    def test_o_passaporte_nao_declara_bonus_e_sai_inteiro(self):
        """"60GB livre para voce usar" nao separa bonus: contratual
        igual a anunciada esta certo aqui, e so aqui."""
        por_gb = {o["franquia_anunciada_gb"]: o
                  for o in claro_flex.extrair(HOJE)}
        self.assertEqual(por_gb[60]["franquia_contratual_gb"], 60)
        self.assertIn("Passaporte", por_gb[60]["nome_oferta"])


if __name__ == "__main__":
    unittest.main()
