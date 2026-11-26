# -*- coding: utf-8 -*-
u"""GeForce NOW, iCloud+ e Claro Banca: o que os cards da Claro listam.

Medido no caminho de producao em Sao Paulo, 26/11/2026: o "Claro Controle
Geforce" de R$ 69,90 saia com os mesmos apps do Claro Controle de R$ 69,90
(so Skeelo), o iCloud+ do "Google One (AI Plus) e iCloud+" dos Pos de
R$ 239,90 e R$ 339,90 ficava de fora, e a Claro Banca do "Apps exclusivos
para voce: Skeelo Claro Banca" tambem. Os trechos abaixo sao os do card.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import apps  # noqa: E402

CONTROLE = (u"Redes Sociais e Apps Instagram +4 Apps exclusivos para você "
            u"Skeelo Claro Banca Ligações ilimitadas Mais detalhes")
GEFORCE = (u"Ganhe GeForce NOW Performance para jogar na nuvem. "
           u"Apps exclusivos para você Skeelo Claro Banca")
OS_DOIS = u"Armazenamento na nuvem: Google One (AI Plus) e iCloud+ WhatsApp e ligações"
ESCOLHA = u"Armazenamento na nuvem: Google One ou iCloud+ WhatsApp e ligações"


class OsTresAppsDaClaro(unittest.TestCase):

    def test_a_claro_banca_do_controle(self):
        self.assertEqual(sorted(apps.apps_do_texto(CONTROLE)), ["claro_banca", "skeelo"])

    def test_o_geforce_now_separa_os_dois_controles_de_69_90(self):
        self.assertIn("geforce_now", apps.apps_do_texto(GEFORCE))
        self.assertNotIn("geforce_now", apps.apps_do_texto(CONTROLE))

    def test_geforce_solto_e_a_placa_de_video(self):
        self.assertNotIn("geforce_now", apps.apps_do_texto(u"notebook com GeForce RTX 4060"))

    def test_com_e_entram_os_dois(self):
        self.assertEqual(sorted(apps.apps_do_texto(OS_DOIS)), ["google_one", "icloud"])

    def test_com_ou_nenhum_entra(self):
        u"""ESCOLHA NAO E INCLUSAO: "Google One ou iCloud+" e um dos dois,
        a escolher, e nomear qualquer um afirma o que a fonte nao disse."""
        lista = apps.apps_do_texto(ESCOLHA)
        self.assertNotIn("icloud", lista)
        self.assertNotIn("google_one", lista)

    def test_nenhum_dos_tres_sobe_o_nivel(self):
        u"""Jogo na nuvem, armazenamento e revistas sao catalogo."""
        for app in ("geforce_now", "icloud", "claro_banca"):
            self.assertNotIn(app, apps.STREAMING)
            self.assertIn(app, apps.APPS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
