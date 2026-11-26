# -*- coding: utf-8 -*-
u"""O card do hub da Claro fecha no "Mais detalhes", e a fidelidade vem da loja.

Duas leituras de 27/11/2026, as duas medidas no hub de Sao Paulo de 26/11:

  - O CARD QUE IA ATE O FIM DA PAGINA. O hub e cortado pela classe do card
    seguinte; o ultimo card do carrossel do pos nao tem seguinte e levava o
    resto da pagina, onde estao os quatro cards do Claro Flex. O "Claro
    Musica" do Flex de 55 e de 80 GB entrava como app do Pos 250 GB - desde
    que os apps passaram a ser lidos do card inteiro. Cada card fecha com um
    unico link "Mais detalhes", que leva o codigo do proprio plano; o
    id="plan-" que o corte deixava era o do card seguinte.

  - A FIDELIDADE QUE O CARD NAO DIZ. O Controle e o Pos do hub tem
    "Fidelidade de 12 meses" na pagina do plano na loja, e saiam com a
    fidelidade vazia ao lado dos planos sem fidelidade (0). As paginas de
    categoria da loja dao o prazo de cada plano pelo mesmo codigo.

As fixtures sao recortes reais de 26/11/2026: o hub do card do Pos 200 GB
ao fim dos cards do Flex, e o loyaltySummary das duas paginas da loja.
"""
import io
import json
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import claro  # noqa: E402

HUB = io.open(os.path.join(AQUI, "fixtures", "claro_hub_pos_e_flex_2026-11-26.html"),
              encoding="utf-8").read()
LOJA = json.load(io.open(os.path.join(AQUI, "fixtures", "claro_loja_fidelidade_2026-11-26.json"),
                         encoding="utf-8"))


def _pagina_da_loja(nome):
    return ('<html><script id="__NEXT_DATA__" type="application/json">%s</script></html>'
            % json.dumps(LOJA[nome], ensure_ascii=False))


class _ComStubs(unittest.TestCase):

    def setUp(self):
        guarda = (claro.buscar, claro.PAUSA, claro.codigo_cidade, claro.ler_sem_fidelidade)
        self.respostas = {
            claro.PAGINAS["movel"]: (200, HUB),
            claro.LOJA_COM_FIDELIDADE[0]: (200, _pagina_da_loja("pos-pago")),
            claro.LOJA_COM_FIDELIDADE[1]: (200, _pagina_da_loja("controle")),
        }
        self.pedidos = []

        def buscar(op, url, *a, **k):
            self.pedidos.append(url)
            return self.respostas.get(url, (404, ""))
        claro.buscar = buscar
        claro.PAUSA = 0
        claro.codigo_cidade = lambda op, c, u: ("x", "123", None)
        claro.ler_sem_fidelidade = lambda op: ([], None)
        claro._cache_fidelidade.clear()

        def volta():
            claro.buscar, claro.PAUSA, claro.codigo_cidade, claro.ler_sem_fidelidade = guarda
            claro._cache_fidelidade.clear()
        self.addCleanup(volta)

    def _pos(self, d):
        return {o["preco_promocional"]: o for o in d["ofertas"] if o["produto"] == "movel"}


class OCardFechaNoDetalhe(_ComStubs):

    def test_a_fixture_tem_o_claro_musica_do_flex_depois_do_card(self):
        # sem o Flex depois do ultimo card, o teste de baixo passaria por
        # nao haver o que vazar
        fim_do_card = HUB.rindex("plan-more-details")
        self.assertIn("Claro Musica", HUB[fim_do_card:])
        self.assertNotIn("Claro Musica", HUB[:fim_do_card])

    def test_o_pos_250_nao_leva_o_claro_musica_do_flex(self):
        cards, erro = claro.ler_cards(None, claro.PAGINAS["movel"], "movel")
        self.assertIsNone(erro)
        self.assertEqual([c["preco_promocional"] for c in cards], [239.9, 339.9])
        pos = self._pos(claro.coletar("Sao Paulo", "SP", verbose=False))
        self.assertEqual(pos[339.9]["apps"], ["google_one", "icloud", "skeelo"])
        self.assertEqual(pos[239.9]["apps"], ["google_one", "icloud", "skeelo"])
        self.assertTrue(pos[339.9]["whatsapp"])

    def test_o_codigo_e_o_do_proprio_card(self):
        cards, _ = claro.ler_cards(None, claro.PAGINAS["movel"], "movel")
        self.assertEqual({c["preco_promocional"]: c["id_catalogo"] for c in cards},
                         {239.9: "24158", 339.9: "24159"})

    def test_card_sem_o_link_fica_como_era(self):
        card = ('<div class="card-planos-custom"><h3>Claro Pós 80GB</h3><p>80GB</p>'
                '<p>R$ 124,90 /mês</p><p>Apps exclusivos para você Skeelo</p></div>'
                '<div id="plan-24154" class="card-planos-custom"><h3>Claro Pós 150GB</h3>'
                '<p>150GB</p><p>R$ 179,90 /mês</p></div>')
        self.respostas[claro.PAGINAS["movel"]] = (200, "<html>%s</html>" % card)
        cards, _ = claro.ler_cards(None, claro.PAGINAS["movel"], "movel")
        self.assertEqual(cards[0]["id_catalogo"], "24154")
        self.assertIn("Skeelo", cards[0]["texto_apps"])


class AFidelidadeDaLoja(_ComStubs):

    def test_os_oito_planos_tem_doze_meses(self):
        mapa, erro = claro.ler_fidelidade(None)
        self.assertIsNone(erro)
        self.assertEqual(mapa, dict.fromkeys(
            ["24153", "24154", "24156", "24158", "24159", "23809", "23811", "23883"], 12))

    def test_o_hub_sai_com_a_fidelidade_da_loja(self):
        d = claro.coletar("Sao Paulo", "SP", verbose=False)
        pos = self._pos(d)
        self.assertEqual(pos[239.9]["fidelidade_meses"], 12)
        self.assertEqual(pos[339.9]["fidelidade_meses"], 12)
        # multa proporcional ao tempo restante: a loja nao da valor fixo
        self.assertIsNone(pos[339.9].get("multa_fidelidade"))
        self.assertFalse([a for a in d["avisos"] if "fidelidade da loja" in a])

    def test_a_loja_que_falha_nao_derruba_o_plano(self):
        del self.respostas[claro.LOJA_COM_FIDELIDADE[0]]
        del self.respostas[claro.LOJA_COM_FIDELIDADE[1]]
        d = claro.coletar("Sao Paulo", "SP", verbose=False)
        pos = self._pos(d)
        self.assertEqual(sorted(pos), [239.9, 339.9])
        self.assertIsNone(pos[339.9].get("fidelidade_meses"))
        aviso = [a for a in d["avisos"] if "fidelidade da loja" in a]
        self.assertEqual(len(aviso), 1)
        self.assertIn("pos-pago: HTTP 404", aviso[0])

    def test_pagina_que_falha_nao_apaga_a_outra_e_nao_fica_guardada(self):
        del self.respostas[claro.LOJA_COM_FIDELIDADE[1]]
        mapa, erro = claro.ler_fidelidade(None)
        self.assertEqual(sorted(mapa), ["24153", "24154", "24156", "24158", "24159"])
        self.assertIn("controle: HTTP 404", erro)
        self.respostas[claro.LOJA_COM_FIDELIDADE[1]] = (200, _pagina_da_loja("controle"))
        mapa, erro = claro.ler_fidelidade(None)
        self.assertIsNone(erro)
        self.assertEqual(len(mapa), 8)

    def test_a_loja_e_lida_uma_vez_por_rodada(self):
        claro.ler_fidelidade(None)
        antes = len(self.pedidos)
        claro.ler_fidelidade(None)
        self.assertEqual(len(self.pedidos), antes)

    def test_prazo_que_nao_e_doze_e_lido(self):
        outra = json.loads(json.dumps(LOJA["pos-pago"]))
        outra["props"]["pageProps"]["filteredProducts"][0]["loyaltySummary"]["title"] = \
            u"Fidelidade de 24 meses"
        self.respostas[claro.LOJA_COM_FIDELIDADE[0]] = (
            200, '<script id="__NEXT_DATA__">%s</script>' % json.dumps(outra))
        mapa, _ = claro.ler_fidelidade(None)
        self.assertEqual(mapa["24153"], 24)


if __name__ == "__main__":
    unittest.main()
