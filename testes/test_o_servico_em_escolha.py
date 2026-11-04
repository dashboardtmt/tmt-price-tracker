# -*- coding: utf-8 -*-
u"""O servico que a vitrine inclui - e o que ela oferece A ESCOLHER.

Em 03/11/2026, as 18h34, o Mobile Time publicou que a Vivo pos o Google
One Lite (30 GB) na recarga de R$ 35 do pre-pago. O tracker gravava o
degrau certo - Vivo Pre 25 GB, R$ 35, codigo VIV202600042812, nas 20
pracas - e nao tinha como ver o servico novo. Medido em 04/11/2026:

  - A ASSINATURA SVA DO REGULAMENTO NAO MUDOU. O detector de composicao
    compara essa assinatura, e ela segue com os mesmos cinco codigos de
    03/11 (030012+030021+030032+040022+060016), com zero mencao a
    Google no regulamento da Anatel. Por aquele canal nao havia o que
    dizer.

  - O TEXTO DO CARD DE R$ 35 JA DIZIA. "Armazenamento extra com Google
    One", e so o daquele card - os de R$ 20, R$ 25 e R$ 30 nao citam. O
    que faltava era padrao em DO_TEXTO: a lista saia com vale_saude
    sozinho.

O nome faltava na REGUA, nao na fonte.

E A MESMA PAGINA DA CLARO USA AS DUAS CONJUNCOES, medido no caminho de
producao em Sao Paulo no mesmo dia: os cards de R$ 124,90 e R$ 179,90
dizem "Armazenamento na nuvem: Google One OU iCloud+", e os de
R$ 239,90 e R$ 339,90 dizem "Google one (AI Plus) E iCloud+". As duas
frases dizem coisas diferentes, e nomear um lado da escolha afirma o
que a fonte nao disse - o mesmo defeito de eleger um representante do
grupo e publicar o numero dele como fato.

O QUE ESTE ARQUIVO PRENDE. Tirar o padrao do Google One devolve o
silencio; tirar o corte da escolha devolve a afirmacao. Os dois somem
num refactor sem quebrar nada mais, e o primeiro canal a mentir seria a
tela, dizendo que o plano de R$ 124,90 inclui Google One.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _apoio import em_todas, montar                           # noqa: E402
import coletores.apps as apps                                 # noqa: E402
import coletores.vivo as vivo                                 # noqa: E402

# os textos sao os que as paginas publicavam em 04/11/2026, como o
# coletor os entrega: tag virada em espaco, uma linha so
CARD_PRE_35 = ("Oferta Recomendada melhor oferta! Vivo Pre 25 GB 25 GB para "
               "navegar como quiser + 10 GB de bonus trazendo seu numero "
               "para a Vivo Vale Saude Farma: desconto em farmacias "
               "Armazenamento extra com Google One Nas recargas de Valor "
               "R$ 35 Por 30 dias Ligacoes e SMS para qualquer operadora "
               "usando 15")
CARD_PRE_25 = ("Vivo Pre 15 GB 15 GB para navegar como quiser + 10 GB de "
               "bonus trazendo seu numero para a Vivo Nas recargas de "
               "Valor R$ 25 Por 30 dias")
CLARO_ESCOLHA = ("Claro Pos Ate 2 linhas R$ 124,90 /mes Armazenamento na "
                 "nuvem: Google One ou iCloud+ iCloud Google One "
                 "WhatsApp ilimitado")
CLARO_OS_DOIS = ("Claro Pos R$ 239,90 /mes Armazenamento na nuvem: Google "
                 "one (AI Plus) e iCloud+ Google One iCloud WhatsApp "
                 "ilimitado")


class ONomeQueFaltavaNaRegua(unittest.TestCase):

    def test_o_card_de_35_nomeia_o_google_one(self):
        # pelo caminho do coletor, nao pela funcao solta: e
        # apps_da_vitrine que a Vivo chama para os quatro campos de app
        lista = vivo.apps_da_vitrine("Vivo Pre", CARD_PRE_35)
        self.assertIn("google_one", lista)
        self.assertIn("vale_saude", lista)

    def test_os_outros_degraus_do_pre_seguem_sem_ele(self):
        self.assertNotIn("google_one",
                         vivo.apps_da_vitrine("Vivo Pre", CARD_PRE_25))

    def test_sem_tier_declarado_nao_ha_preco(self):
        # o card escreve so "Google One"; o tier - e o preco, que
        # pertence ao tier - fica de fora
        lista = vivo.apps_da_vitrine("Vivo Pre", CARD_PRE_35)
        self.assertIsNone(apps.tier_do_texto("google_one", CARD_PRE_35))
        planos = apps.planos_dos_apps(lista, "Vivo Pre", CARD_PRE_35) or {}
        self.assertNotIn("google_one", planos)
        self.assertIn("Google One",
                      apps.rotulo(lista, "Vivo Pre", CARD_PRE_35))

    def test_nuvem_nao_e_streaming(self):
        # app de catalogo: entra na lista e NAO sobe o nivel de bundle
        self.assertEqual(apps.nivel_dos_apps(["google_one"]), 1)


class EscolhaNaoEInclusao(unittest.TestCase):

    def test_ou_nao_entra(self):
        self.assertNotIn("google_one", apps.apps_do_texto(CLARO_ESCOLHA))

    def test_e_entra_com_o_tier_que_a_pagina_declara(self):
        lista = apps.apps_do_texto(CLARO_OS_DOIS)
        self.assertIn("google_one", lista)
        self.assertEqual(apps.tier_do_texto("google_one", CLARO_OS_DOIS),
                         "AI Plus")
        self.assertEqual(apps.rotulo(["google_one"], CLARO_OS_DOIS),
                         "Google One (AI Plus)")

    def test_a_barra_tambem_e_escolha(self):
        self.assertNotIn("google_one",
                         apps.apps_do_texto("Nuvem: Google One / iCloud+"))

    def test_o_ponto_separa_a_escolha_da_frase_seguinte(self):
        # "ou" de outra frase nao e alternativa deste app
        self.assertIn("google_one", apps.apps_do_texto(
            "Armazenamento com Google One. Ou ligue para o 1052"))

    def test_a_marca_vizinha_nao_vira_tier(self):
        # "Vivo Lite" antes do nome do app nao faz tier Lite: a janela
        # do tier comeca DEPOIS da marca
        self.assertIsNone(apps.tier_do_texto(
            "google_one", "Vivo Lite 30 GB com Google One incluso"))


class OQueONomeNaoAlcanca(unittest.TestCase):

    def test_google_sozinho_nao_e_app(self):
        # texto de vitrine vem com o Google em tres outros papeis
        for texto in ("googleTagManager = GTM-WWS4N55",
                      "Baixe na Google Play",
                      "backup no Google Fotos"):
            self.assertEqual(apps.apps_do_texto(texto), [], texto)

    def test_degustacao_ainda_vence(self):
        self.assertEqual(apps.apps_do_texto(
            "Google One: 3 meses por conta da Claro. Apos, R$ 4,50 por mes."),
            [])


class ODiaDaViradaNaoEhNoticia(unittest.TestCase):
    """Mexer na regua muda a chave, e isso nao e movimento de mercado.

    Medido na bancada sobre as 1.636 linhas de 03/11/2026: as tres
    ofertas afetadas trocam de versao da chave em 60 linhas, e a
    mensagem do dia seguinte continua dizendo "Nenhuma mudanca". A data
    esta declarada em LEITURA_MUDOU_EM para que o degrau na serie tenha
    causa escrita, e nao heuristica.
    """

    def test_a_virada_sai_calada(self):
        ontem = em_todas(operadora="Vivo", produto="prepago",
                         nome="Vivo Pre", preco=35.0, gb=25,
                         chave="Vivo|prepago|25gb|com_vale_saude",
                         apps=["vale_saude"], data="2026-10-20")
        hoje = em_todas(operadora="Vivo", produto="prepago",
                        nome="Vivo Pre", preco=35.0, gb=25,
                        chave="Vivo|prepago|25gb|com_google_one_vale_saude",
                        apps=["google_one", "vale_saude"], data="2026-10-21")
        texto = montar(ontem, hoje)
        self.assertIn("Nenhuma mudan", texto)

    def test_a_causa_esta_declarada(self):
        import robo
        self.assertIn("2026-11-04", robo.LEITURA_MUDOU_EM)
        self.assertIn("Google One", robo.LEITURA_MUDOU_EM["2026-11-04"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
