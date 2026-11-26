# -*- coding: utf-8 -*-
u"""Os apps do Claro Flex vem do hub da Claro (27/11/2026).

Os dois sites da Claro discordam. O hub de planos mostra "App exclusivo pra
voce: Skeelo" nos quatro cards do Flex, e Claro Musica no de 55 GB e no
Passaporte 80 GB; o site do Flex (cards, gavetas e cadastro) nao cita app.
Escolha de quem le, 26/11/2026: "hub da Claro". Preco, franquia e WhatsApp
continuam vindo do site do Flex.

As fixtures sao reais de 26/11/2026: o texto da pagina do Flex, ja com o
WhatsApp do logo marcado, e o recorte do hub com o bloco do Flex.
"""
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import armazenamento, claro_flex  # noqa: E402

FIX = os.path.join(AQUI, "fixtures")
with io.open(os.path.join(FIX, "claro_flex_2026-11-26.txt"), encoding="utf-8") as _f:
    SITE = _f.read()
with io.open(os.path.join(FIX, "claro_hub_pos_e_flex_2026-11-26.html"), encoding="utf-8") as _f:
    HUB = _f.read()


class _Pagina(object):
    u"""O bastante de uma pagina do playwright para o coletar()."""

    def __init__(self, texto):
        self.texto = texto

    def goto(self, *a, **k):
        return None

    def wait_for_timeout(self, ms):
        return None

    def evaluate(self, js):
        return 0

    def inner_text(self, seletor):
        return self.texto


class OBlocoDoFlexNoHub(unittest.TestCase):

    def test_os_quatro_cards_do_hub(self):
        hub = claro_flex.apps_do_hub(HUB)
        self.assertEqual(sorted((gb, p["preco"], p["apps"]) for gb, p in hub.items()),
                         [(40, 44.9, ["skeelo"]), (50, 59.9, ["skeelo"]),
                          (55, 69.9, ["skeelo", "claro_musica"]),
                          (80, 119.9, ["skeelo", "claro_musica"])])

    def test_hub_sem_o_flex_e_vazio(self):
        self.assertEqual(claro_flex.apps_do_hub("<html><p>Claro Pós 80GB</p></html>"), {})


class _Coleta(unittest.TestCase):

    def setUp(self):
        guarda = claro_flex.ler_hub
        self.addCleanup(setattr, claro_flex, "ler_hub", guarda)
        self.hub = (claro_flex.apps_do_hub(HUB), None)
        claro_flex.ler_hub = lambda: self.hub

    def coletar(self):
        d = claro_flex.coletar(verbose=False, pagina=_Pagina(SITE))
        return d, dict((o["franquia_anunciada_gb"], o) for o in d["ofertas"])


class OFlexComOsAppsDoHub(_Coleta):

    def test_o_skeelo_e_o_claro_musica_entram(self):
        d, por_gb = self.coletar()
        self.assertEqual({gb: o["apps"] for gb, o in por_gb.items()},
                         {40: ["skeelo"], 50: ["skeelo"],
                          55: ["skeelo", "claro_musica"], 80: ["skeelo", "claro_musica"]})
        self.assertEqual(por_gb[55]["apps_rotulo"], u"Skeelo + Claro Música")
        self.assertFalse(d["avisos"])

    def test_o_resto_continua_do_site_do_flex(self):
        _d, por_gb = self.coletar()
        self.assertEqual({gb: (o["preco_cheio"], o["franquia_contratual_gb"], o["whatsapp"])
                          for gb, o in por_gb.items()},
                         {40: (44.9, 30, True), 50: (59.9, 35, True),
                          55: (69.9, 40, True), 80: (119.9, 50, True)})

    def test_o_app_sobe_o_nivel_do_bundle(self):
        _d, por_gb = self.coletar()
        self.assertTrue(all(o["nivel_bundle"] >= 1 for o in por_gb.values()))

    def test_a_chave_da_serie_muda_e_por_isso_esta_declarada(self):
        u"""A lista de apps entra na chave: o Flex comeca serie nova em
        27/11, e a declaracao daquele dia cobre o Claro Flex."""
        _d, por_gb = self.coletar()
        chave = armazenamento.chave_continuidade(por_gb[40])
        self.assertTrue(chave.startswith("Claro|btl|40gb|"))
        self.assertNotEqual(chave, "Claro|btl|40gb|simples")
        import robo
        quem = [q for decl in robo.LEITURA_DE_OFERTA_MUDOU_EM["2026-11-27"] for q in decl["quem"]]
        self.assertIn(("Claro", "btl", u"Claro Flex"), quem)


class OHubQueFalha(_Coleta):

    def test_hub_fora_do_ar_tira_o_flex_do_dia_e_diz(self):
        self.hub = (None, "HTTP 503")
        d, por_gb = self.coletar()
        self.assertEqual(por_gb, {})
        self.assertTrue(any("HTTP 503" in a and "fica fora hoje" in a for a in d["avisos"]))

    def test_hub_sem_o_flex_deixa_os_apps_do_site_e_diz(self):
        self.hub = ({}, None)
        d, por_gb = self.coletar()
        self.assertEqual(len(por_gb), 4)
        self.assertTrue(all(o["apps"] == [] for o in por_gb.values()))
        self.assertTrue(any("nao mostrou o Flex" in a for a in d["avisos"]))

    def test_card_sem_par_no_hub_fica_com_o_site_e_diz(self):
        hub = dict(claro_flex.apps_do_hub(HUB))
        del hub[55]
        self.hub = (hub, None)
        d, por_gb = self.coletar()
        self.assertEqual(por_gb[55]["apps"], [])
        self.assertEqual(por_gb[40]["apps"], ["skeelo"])
        self.assertTrue(any("55 GB" in a for a in d["avisos"]))


if __name__ == "__main__":
    unittest.main()
