# -*- coding: utf-8 -*-
"""O que os coletores leem das vitrines, e o que nao podem ler.

CADA TESTE AQUI E UM DEFEITO QUE EXISTIU, com o texto real que o causou.
Nenhum toca a rede: todos usam o trecho de vitrine que foi capturado
quando o defeito apareceu.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import apps, armazenamento, brisanet, claro, vivo   # noqa: E402


class PrecoDeBeneficioNaoEPrecoDePlano(unittest.TestCase):
    """07/10/2026: tres cards de Claro Controle em Porto Alegre gravados
    a R$ 24,60. A serie mostra 99,90, 69,90 e 59,90 nos outros quinze
    dias. R$ 24,60 e o preco avulso do Disney+, citado pela propria
    Claro no card - e a leitura pegava o primeiro "R$" do texto.
    """

    def _preco(self, txt):
        # CHAMA O QUE RODA EM PRODUCAO. Este metodo reimplementava os
        # dois passos da leitura - sem_degustacao e a regex - e com isso
        # testava uma copia: quebrar a linha do coletor deixava a suite
        # verde. Agora e a mesma funcao que a rodada diaria usa.
        return claro.preco_do_card(txt)[0]

    def test_o_card_sem_preco_nenhum_se_distingue_do_card_de_beneficio(self):
        """O segundo item da resposta decide se a rodada emite aviso:
        card sem "R$" nenhum e card comum (aparelho, banner); card cujo
        unico "R$" estava na frase do beneficio e dado perdido, e isso
        precisa aparecer no log da coleta."""
        self.assertEqual(claro.preco_do_card("Claro Pós sem preço"),
                         (None, False))
        self.assertEqual(claro.preco_do_card(
            "Claro Controle Disney+: 3 meses por conta da Claro. "
            "Após, R$24,60 por mês."), (None, True))

    def test_preco_do_plano_antes_do_beneficio(self):
        self.assertEqual(self._preco(
            "Claro Controle 35GB R$ 99,90 /mes Disney+: 3 meses por conta "
            "da Claro. Após, R$24,60 por mês."), "99,90")

    def test_beneficio_antes_do_preco_do_plano(self):
        # era aqui que quebrava: a frase do beneficio vinha primeiro no
        # markup e o primeiro "R$" era o dela
        self.assertEqual(self._preco(
            "Claro Controle 35GB Disney+: 3 meses por conta da Claro. "
            "Após, R$24,60 por mês. R$ 99,90 /mes"), "99,90")

    def test_card_so_com_preco_de_beneficio_nao_vira_oferta(self):
        self.assertIsNone(self._preco(
            "Claro Controle 35GB Disney+: 3 meses por conta da Claro. "
            "Após, R$24,60 por mês."))


class NivelDeBundleConcordaComAListaDeApps(unittest.TestCase):
    """Medido ao vivo em 20/10/2026: a "Vivo Pos com Amazon" saia com
    "Amazon Prime" em apps_rotulo e nivel 0 no campo ao lado - que na
    tela e "so internet e ligacoes". Um streaming nomeado ao lado da
    frase que diz que nao ha streaming.

    A causa: o nivel lia o TEXTO do card e a lista de apps sai do NOME da
    oferta. O card da Vivo as vezes vem so com marcacao, e ai o texto nao
    nomeia app nenhum. A decisao 43 dizia que os dois campos saem da
    mesma leitura; estava meio implementada.
    """

    def test_app_no_nome_e_card_vazio(self):
        # o card de verdade, reduzido: marcacao, sem nome de app
        card = ('unique-card__bordered unique-card--original data-settings='
                '{"name": "","id": "","price": ""}')
        self.assertEqual(vivo.nivel_bundle(card), 0)
        self.assertEqual(vivo.nivel_bundle(card, ["amazon"]), 2)

    def test_app_de_catalogo_no_nome_vale_um(self):
        self.assertEqual(vivo.nivel_bundle("", ["vale_saude"]), 1)

    def test_dois_streamings_no_nome(self):
        self.assertEqual(vivo.nivel_bundle("", ["netflix", "disney"]), 3)

    def test_o_texto_continua_contando_quando_diz_mais(self):
        """max(): o nome ACRESCENTA informacao, nunca tira. O texto pode
        citar streaming que o nome nao cita."""
        self.assertEqual(
            vivo.nivel_bundle("Netflix e Disney+ inclusos", ["vale_saude"]), 3)

    def test_tv_vence_tudo(self):
        self.assertEqual(
            vivo.nivel_bundle("com Vivo TV inclusa", ["netflix"]), 4)

    def test_oferta_sem_app_fica_em_zero(self):
        self.assertEqual(vivo.nivel_bundle("so internet e ligacoes", []), 0)
        self.assertEqual(vivo.nivel_bundle("so internet e ligacoes", None), 0)


class BannerDeCampanhaNaoEhNome(unittest.TestCase):
    """De 06 a 12/10/2026 a Claro rodou o "Claro Day" e o banner colou na
    frente do card. 834 capturas viraram "Claro Day Claro Pos", e com
    outro nome a oferta vira outra identidade - a serie morria no dia 06
    e ressuscitava no dia 12.
    """

    def test_banner_sai_do_nome_e_vai_para_campanha(self):
        self.assertEqual(claro._sem_campanha("Claro Day Claro Pós"),
                         ("Claro Pós", "Claro Day"))
        self.assertEqual(claro._sem_campanha("Semana do Consumidor Claro Pós"),
                         ("Claro Pós", "Semana do Consumidor"))

    def test_nome_que_comeca_na_marca_nao_tem_banner(self):
        self.assertEqual(claro._sem_campanha("Claro Pós"), ("Claro Pós", None))
        self.assertEqual(claro._sem_campanha("Claro Multi 600 Mega Especial"),
                         ("Claro Multi 600 Mega Especial", None))

    def test_vazio_nao_quebra(self):
        self.assertEqual(claro._sem_campanha(""), ("", None))
        self.assertEqual(claro._sem_campanha(None), (None, None))


class OfertasDeMesmoNomeSeDistinguem(unittest.TestCase):
    """Duas "Claro Pos 50GB" ao mesmo tempo, R$ 124,90 e R$ 164,90. O
    nome e lido ate o primeiro numero de franquia, entao o "Geforce" - a
    unica coisa que as separa - era jogado fora, e a serie do 50 GB
    alternava entre os dois precos.
    """

    def test_qualificador_depois_da_franquia_entra_no_nome(self):
        self.assertEqual(claro._qualificador_do_card(
            "Claro Pós 50GB Geforce Até 2 linhas Linhas no Plano"), "Geforce")
        self.assertEqual(claro._qualificador_do_card(
            "Claro Pós 50GB Gaming Plus Até 2 linhas"), "Gaming Plus")

    def test_texto_estrutural_nao_e_qualificador(self):
        self.assertIsNone(claro._qualificador_do_card(
            "Claro Pós 50GB Até 2 linhas Linhas no Plano - Você"))
        self.assertIsNone(claro._qualificador_do_card(
            "Claro Pós 50GB R$ 124,90 /mês"))


class BrisanetMandaNumeroSemUnidade(unittest.TestCase):
    """119 linhas por dia sem velocidade. A API manda plan_speed como
    numero puro - "500", "700" - e a funcao exigia unidade no texto.
    Sem velocidade nao ha R$/Mbps, e a chave de continuidade cai para
    degrau 0: 500, 600, 700 e 1000 Mbps na mesma serie.
    """

    def test_numero_puro_e_mbps(self):
        for v, esperado in (("500", 500), ("700", 700), ("1000", 1000),
                            (500, 500)):
            self.assertEqual(brisanet.mbps(v), esperado)

    def test_com_unidade_continua_valendo(self):
        self.assertEqual(brisanet.mbps("1 GIGA"), 1000)
        self.assertEqual(brisanet.mbps("600 Mega"), 600)
        self.assertEqual(brisanet.mbps("500 MB"), 500)

    def test_numero_pequeno_demais_nao_e_chute(self):
        # "1" tanto pode ser 1 Mbps quanto 1 Giga. Gravar 1 erraria por
        # mil vezes; campo vazio ja e tratado.
        self.assertIsNone(brisanet.mbps("1"))
        self.assertIsNone(brisanet.mbps("5"))

    def test_gb_do_movel_vem_do_nome(self):
        self.assertEqual(brisanet.gb_movel("AGO26 500MB + 20GB"), 20)
        self.assertEqual(brisanet.gb_movel("AGO26 700MB + 50GB"), 50)
        self.assertIsNone(brisanet.gb_movel("500MB + HBO PCA"))

    def test_giga_da_fibra_nao_vira_franquia_de_movel(self):
        # em "1GB ESSENCIAL + 20GB" o primeiro GB e a fibra
        self.assertEqual(brisanet.gb_movel("[OUT] 1GB ESSENCIAL + 20GB"), 20)
        self.assertIsNone(brisanet.gb_movel("[OUT] 12M 1GB ESSENCIAL"))


class CodigoAnatelForaDoPadrao(unittest.TestCase):
    """A vitrine da Vivo publicou "IV202600045258" - falta o V inicial.
    Consultar o regulamento com ele devolve 400, e eram 100 requisicoes
    perdidas por dia reportadas como "regulamento falhou".
    """

    def test_codigo_torto_e_reconhecido(self):
        self.assertTrue(vivo.codigo_malformado("IV202600045258"))

    def test_codigo_bom_passa(self):
        for c in ("VIV202600045256", "VIV202603035925", "VIV202604037365"):
            self.assertFalse(vivo.codigo_malformado(c))

    def test_vazio_nao_e_malformado(self):
        self.assertFalse(vivo.codigo_malformado(""))
        self.assertFalse(vivo.codigo_malformado(None))


class ChaveDeContinuidade(unittest.TestCase):
    """A chave identifica a SERIE, nao a oferta. Mas duas ofertas com a
    mesma chave, praca e nome ficam indistinguiveis para o comparador - e
    uma sobrescreve a outra.
    """

    def _chave(self, **campos):
        base = {"operadora": "Vivo", "produto": "combo", "nome_oferta": "",
                "degrau_mbps": 700, "franquia_anunciada_gb": None,
                "nivel_bundle": 0}
        base.update(campos)
        return armazenamento.chave_continuidade(base)

    def test_familia_com_tv_registrada_separa_da_sem_tv(self):
        com = self._chave(nome_oferta="Vivo Família 2 + TV",
                          nome_regulamento="VT Família 2 700 Mega + TV A com SVA")
        sem = self._chave(nome_oferta="Vivo Família 2 + TV",
                          nome_regulamento="VT Família 2 700 Mega com SVA")
        self.assertNotEqual(com, sem)

    def test_sem_registro_a_chave_nao_muda(self):
        # a Vivo Total Ultra + TV online tem registro sem a palavra TV:
        # trocar a serie dela seria quebrar continuidade por vocabulario
        a = self._chave(nome_oferta="Vivo Total Ultra + TV online")
        b = self._chave(nome_oferta="Vivo Total Ultra + TV online",
                        nome_regulamento="VT Ultra 700 Mega com SVA")
        self.assertEqual(a, b)

    def test_o_ciclo_de_pagamento_separa(self):
        anual = self._chave(nome_oferta="TIM Controle FIT Anual 2.0",
                            operadora="TIM", produto="btl")
        mensal = self._chave(nome_oferta="TIM Controle FIT Mensal 2.0",
                             operadora="TIM", produto="btl")
        self.assertNotEqual(anual, mensal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
