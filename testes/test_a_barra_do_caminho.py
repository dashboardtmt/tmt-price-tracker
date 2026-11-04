# -*- coding: utf-8 -*-
u"""A barra de caminho de arquivo nao e' escolha, e o teto nao e' leitura.

DOIS DEFEITOS MEDIDOS EM 04/11/2026, na primeira coleta depois de a
regra de escolha entrar - e os dois tiraram app de oferta, calados, nas
20 pracas:

1. A BARRA DO CAMINHO. A TIM nomeia o app no nome do arquivo do icone,
   "/sites/default/files/2026-07/Paramount+ Icon (1).png", e a barra
   imediatamente antes do nome foi lida como o "/" de "Google One /
   iCloud+". O Paramount da Ultracombo 6 e o Aya Books da 7 sairam da
   lista: 40 linhas. A barra de prosa tem espaco do lado; a de caminho,
   nao.

2. O TETO DA COMPOSICAO. ler_combos calculava o nivel com o texto
   inteiro e gravava a composicao cortada em 400 caracteres, e a LISTA
   de apps era lida da composicao cortada. No mesmo dia a TIM pos um
   beneficio novo ("Frame 35840.png Noping - Fibra") na FRENTE da lista
   e empurrou o nome do Paramount para depois do corte: nivel 3 com
   lista vazia, que e o par contraditorio que nivel_dos_apps existe
   para impedir. Teto de EXIBICAO nao pode governar o que a leitura ve.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import apps, tim                               # noqa: E402

# O texto real do beneficio, como a pagina da TIM o publicou em
# 04/11/2026 para "1giga + 70gb". A ordem importa: o Noping entrou na
# frente naquele dia, e e ele que empurra o Paramount.
BENEFICIO = (
    "Contrate e ganhe por 6 meses + Modem WiFi e serviços inclusos "
    "/sites/default/files/2026-10/Frame 35840.png Noping - Fibra "
    "/sites/default/files/2026-07/Paramount+ Icon (1).png "
    "Icone Paramount - TIM Ultracombo "
    "/sites/default/files/2026-07/Deezer Icon.png "
    "Icone Deezer - TIM Ultracombo "
    "/sites/default/files/2024-06/Aya Books_0.png Aya books - Fibra")

# O card real tem cerca de 230 caracteres antes do preco, e e' esse
# tamanho que faz o corte em 400 cair no meio da lista de beneficios.
CARD = ("TIM Ultracombo 6 1GIGA + 70GB de TIM Black A para móvel: "
        "(15GB do plano + 50GB promo + 5GB bônus especial) "
        "Aproveite com seu plano Ultracombo. Modem WiFi incluso, "
        "instalação em até 7 dias uteis e aplicativos "
        "inclusos no plano, sem custo adicional nos 6 primeiros meses "
        "de contrato. Por R$149,99/mes")


class ABarraDoCaminhoNaoEEscolha(unittest.TestCase):

    def test_o_app_no_nome_do_arquivo_continua_sendo_lido(self):
        lista = apps.apps_do_texto(BENEFICIO)
        self.assertIn("paramount", lista)
        self.assertIn("deezer", lista)
        self.assertIn("aya_books", lista)

    def test_a_escolha_de_verdade_continua_fora(self):
        """O caso que criou a regra, na pagina da Claro de 04/11/2026."""
        self.assertEqual(
            apps.apps_do_texto("Armazenamento na nuvem: Google One ou "
                               "iCloud+"), [])

    def test_e_com_e_os_dois_entram(self):
        self.assertIn("google_one",
                      apps.apps_do_texto("Armazenamento na nuvem: Google "
                                         "one (AI Plus) e iCloud+"))

    def test_a_barra_de_prosa_tambem_e_escolha(self):
        """Com espaco do lado, a barra e separador de frase."""
        self.assertEqual(
            apps.apps_do_texto("Armazenamento: Google One / iCloud+"), [])

    def test_o_limite_fica_dito_e_medido(self):
        """"Google One/iCloud+" sem espaco ENTRA, e isto esta escrito na
        regra: nenhuma vitrine escreveu assim nas medicoes, e guarda
        contra caso que nao existe esconde o que existe - foi esta regra
        que ensinou isso, em 40 linhas."""
        self.assertIn("google_one",
                      apps.apps_do_texto("Armazenamento: Google One/iCloud+"))


class OTetoDaComposicaoNaoGovernaALeitura(unittest.TestCase):

    def _pagina(self):
        cru = {"ofertas": [{"field_titulo": [{"value": "1GIGA + 70GB"}],
                            "field_outros_beneficios": [
                                {"value": BENEFICIO}]}]}
        html = ('<script data-drupal-selector="drupal-settings-json">'
                + json.dumps(cru) + "</script><div>" + CARD + "</div>")
        guarda = tim.buscar
        tim.buscar = lambda op, url: (200, html)
        self.addCleanup(lambda: setattr(tim, "buscar", guarda))

    def test_o_texto_da_leitura_vai_alem_do_teto_da_composicao(self):
        self._pagina()
        combos, erro = tim.ler_combos(None, "http://x")
        self.assertIsNone(erro)
        self.assertEqual(len(combos), 1)
        o = combos[0]
        self.assertEqual(len(o["composicao"]), 400,
                         "o cenario precisa estourar o teto para medir algo")
        self.assertGreater(len(o["texto_apps"]), 400)

    def test_e_o_app_cortado_pelo_teto_continua_nomeado(self):
        """O corte esconde app que o texto inteiro nomeia.

        Medido na pagina de verdade em 04/11/2026: a composicao da
        Ultracombo 6 parava em "/2026-07/Deez" e nomeava so o
        Paramount, enquanto o texto inteiro nomeia Paramount, Deezer,
        Aya Books e Aya Ensinah. O teste nao fixa QUAL app fica de
        fora - fixa que o teto esconde algum.
        """
        self._pagina()
        combos, _ = tim.ler_combos(None, "http://x")
        o = combos[0]
        curta = set(apps.apps_do_texto(o["composicao"]))
        cheia = set(apps.apps_do_texto(o["texto_apps"]))
        self.assertTrue(curta < cheia,
                        "o cenario precisa de app depois do corte: "
                        "curta=%s cheia=%s" % (sorted(curta), sorted(cheia)))
        self.assertIn("paramount", cheia)

    def test_a_oferta_GRAVADA_leva_a_lista_inteira(self):
        """O CAMINHO DE PRODUCAO, e nao a peca.

        A primeira versao deste arquivo media ler_combos e dava a
        mutacao por provada - mas quem escolhe a fonte da lista e
        coletar(), duas funcoes depois. O provador nao pegou a mutacao
        que devolvia a composicao cortada, e estava certo: nenhum teste
        passava por ali.
        """
        self._pagina()
        guarda = (tim.navegador, tim.PAUSA)
        tim.navegador = lambda: None
        tim.PAUSA = 0
        self.addCleanup(lambda: setattr(tim, "PAUSA", guarda[1]))
        self.addCleanup(lambda: setattr(tim, "navegador", guarda[0]))
        r = tim.coletar("Sao Paulo", "SP", verbose=False)
        combo = [o for o in r["ofertas"] if o.get("produto") == "combo"]
        self.assertEqual(len(combo), 1, "o cenario tem de gravar o combo")
        o = combo[0]
        self.assertIn("paramount", o["apps"])
        self.assertIn("deezer", o["apps"],
                      "o app depois do corte de 400 tem de chegar gravado")
        self.assertIn("Deezer", o["apps_rotulo"])
        self.assertNotIn("texto_apps", o,
                         "o texto da leitura nao e campo de publicacao")

    def test_o_nivel_e_a_lista_leem_o_mesmo_texto(self):
        """Nivel 3 com lista vazia foi o que a base publicou em 40 linhas.
        O nivel sai do texto inteiro; a lista tem de sair do mesmo."""
        self._pagina()
        combos, _ = tim.ler_combos(None, "http://x")
        o = combos[0]
        lista = apps.apps_do_texto(o["texto_apps"])
        self.assertEqual(o["nivel_bundle"],
                         apps.nivel_dos_apps(lista, o["nivel_bundle"]))
        self.assertTrue(lista, "nivel alto com lista vazia e o par proibido")


if __name__ == "__main__":
    unittest.main(verbosity=2)
