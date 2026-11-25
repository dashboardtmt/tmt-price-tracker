# -*- coding: utf-8 -*-
u"""O celular e os combos da Unifique, que o coletor nao lia ate 25/11/2026.

As fixtures sao o texto das paginas de Florianopolis em 25/11/2026, como o
coletor o ve depois de tirar as tags: o bloco "Ofertas Exclusivas".
"""
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import armazenamento, unifique                  # noqa: E402

def _ler(nome):
    return io.open(os.path.join(AQUI, "fixtures", nome), encoding="utf-8").read()


MOVEL = _ler("unifique_movel_florianopolis_2026-11-25.txt")
COMBO = _ler("unifique_combo_florianopolis_2026-11-25.txt")
FIBRA = u"Florianópolis FIBRA IDEAL 500 Mega com Wi-Fi R$ 119,90 /mês"


class OsLeitores(unittest.TestCase):

    def test_os_tres_planos_de_celular(self):
        lidos = [(o["nome_oferta"], o["franquia_anunciada_gb"], o["preco_promocional"],
                  o["fidelidade_meses"]) for o in unifique.extrair_movel(MOVEL)]
        self.assertEqual(lidos, [("LEVE 10 GB", 10, 39.9, 12), ("IDEAL 30 GB", 30, 64.9, 12),
                                 ("SEM LIMITE 100 GB", 100, 99.9, 12)])

    def test_os_dois_combos_com_o_depois(self):
        lidos = [(o["degrau_mbps"], o["franquia_anunciada_gb"], o["preco_cheio"],
                  o["preco_promocional"], o["meses_desconto"], o["preco_pos_promocao"])
                 for o in unifique.extrair_combo(COMBO)]
        self.assertEqual(lidos, [(550, 10, None, 99.9, 3, 149.9),
                                 (550, 30, 149.9, 119.9, 12, 149.9)])

    def test_so_portabilidade_fica_dito(self):
        trinta = unifique.extrair_combo(COMBO)[1]
        self.assertIn("Somente portabilidade", trinta["contexto"])

    def test_o_detalhe_sem_preco_nao_vira_oferta(self):
        u"""A pagina repete "PLANO DE CELULAR 30 GB IDEAL" nos detalhes, sem
        preco, ANTES do bloco de cards: fora do bloco nada e lido."""
        texto = (u"PLANO DE CELULAR 30 GB IDEAL Fidelidade 12 meses Pagamento " + MOVEL)
        self.assertEqual(len(unifique.extrair_movel(texto)), 3)


class NoColetar(unittest.TestCase):
    u"""O caminho de producao: a fibra, o combo e o celular de cada cidade."""

    def paginas(self, por_rota):
        guarda = unifique.buscar

        def buscar(url):
            for pedaco, resposta in por_rota.items():
                if pedaco in url:
                    return resposta
            return 404, ""
        unifique.buscar = buscar
        self.addCleanup(setattr, unifique, "buscar", guarda)

    def test_os_tres_produtos(self):
        self.paginas({"internet-fibra": (200, FIBRA), "combos-fibra-movel": (200, COMBO),
                      "movel-planos-de-celular": (200, MOVEL)})
        s = unifique.coletar("Florianopolis", "SC", verbose=False)
        por = sorted((o["produto"], o["nome_oferta"]) for o in s["ofertas"])
        self.assertEqual([p for p, _ in por].count("movel"), 3)
        self.assertEqual([p for p, _ in por].count("combo"), 2)
        self.assertEqual([p for p, _ in por].count("fibra"), 1)
        self.assertTrue(all(o["operadora"] == "Unifique" and o["praca"] == "Florianopolis/SC"
                            for o in s["ofertas"]))
        self.assertTrue(all(o["whatsapp"] for o in s["ofertas"] if o["produto"] == "movel"))

    def test_cada_combo_tem_a_sua_serie(self):
        self.paginas({"internet-fibra": (200, FIBRA), "combos-fibra-movel": (200, COMBO),
                      "movel-planos-de-celular": (200, MOVEL)})
        s = unifique.coletar("Florianopolis", "SC", verbose=False)
        chaves = [armazenamento.chave_continuidade(o) for o in s["ofertas"]]
        self.assertEqual(len(set(chaves)), len(chaves))

    def test_404_no_combo_e_nao_vende_e_nao_derruba_o_resto(self):
        self.paginas({"internet-fibra": (200, FIBRA), "movel-planos-de-celular": (200, MOVEL)})
        s = unifique.coletar("Florianopolis", "SC", verbose=False)
        self.assertEqual(sorted(set(o["produto"] for o in s["ofertas"])), ["fibra", "movel"])
        self.assertTrue(any("nao vende combo" in a for a in s["avisos"]))

    def test_pagina_sem_card_e_sem_cidade_e_layout(self):
        self.paginas({"internet-fibra": (200, FIBRA), "combos-fibra-movel": (200, "outra coisa"),
                      "movel-planos-de-celular": (200, MOVEL)})
        s = unifique.coletar("Florianopolis", "SC", verbose=False)
        self.assertTrue(any(a.startswith("combo:") and "layout" in a for a in s["avisos"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
