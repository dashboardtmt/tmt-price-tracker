# -*- coding: utf-8 -*-
u"""O Ultracombo da TIM lido quando o card vira componente.

EM 17/11/2026 A TIM TROCOU O CARD. O texto renderizado ("TIM Ultracombo
7 600MEGA + 65GB ... Por R$89,99/mes") virou <tim-card-pricing-offer>,
com o nome em atributo e o preco VAZIO (price=""), preenchido depois
pelo JavaScript. O leitor tira as tags e procura o texto; nao sobrou
texto nenhum, e as 40 linhas de combo sumiram das 20 pracas. A mensagem
do dia disse que os dois Ultracombos "sairam da vitrine", com a pagina
mostrando os dois a 89,99 e 139,99, como na vespera.

O preco que o JavaScript pinta vem de field_description, no
drupalSettings. O leitor agora remonta o texto do card dali quando o
HTML nao traz nenhum - e passa pela mesma regex, entao nome, franquia,
nivel e apps saem iguais. Medido nas 20 pracas no dia: as 40 linhas
identicas as de 16/11, chave inclusive.

O QUE ESTE ARQUIVO PRENDE, com o recorte da pagina real:
  - os dois combos, com o preco do card - e nao o 129,99 que o mesmo
    JSON carrega em field_preco_adicional_original, resto de campanha;
  - o caminho de producao (coletar), e nao so ler_combos;
  - o formato antigo continua lido (test_a_barra_do_caminho.py).
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import tim                                     # noqa: E402

PAGINA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "fixtures", "tim_ultracombo_2026-11-17.html")


class OUltracomboEmComponente(unittest.TestCase):

    def setUp(self):
        with io.open(PAGINA, encoding="utf-8") as f:
            self.html = f.read()
        guarda = (tim.buscar, tim.navegador, tim.PAUSA)
        tim.buscar = lambda op, url, *a, **k: (200, self.html)
        tim.navegador = lambda: None
        tim.PAUSA = 0

        def volta():
            tim.buscar, tim.navegador, tim.PAUSA = guarda
        self.addCleanup(volta)

    def test_o_recorte_e_do_formato_novo(self):
        u"""Sem isto o teste pode passar pelo caminho velho: o card tem
        de estar em componente, com o preco vazio."""
        self.assertIn("<tim-card-pricing-offer", self.html)
        self.assertIn('price=""', self.html)
        self.assertEqual(tim._combos_do_texto(
            tim.re.sub(r"<[^>]+>", " ", tim.re.sub(
                r"<script.*?</script>", " ", self.html, flags=tim.re.S)), {}),
            [], "o texto sem tags nao pode bastar - senao nada aqui e medido")

    def test_le_os_dois_combos_com_o_preco_do_card(self):
        combos, erro = tim.ler_combos(None, "http://x")
        self.assertIsNone(erro)
        por_nome = dict((o["nome_oferta"], o) for o in combos)
        self.assertEqual(sorted(por_nome), ["TIM Ultracombo 6 1GIGA + 70GB",
                                            "TIM Ultracombo 7 600MEGA + 65GB"])
        sete = por_nome["TIM Ultracombo 7 600MEGA + 65GB"]
        seis = por_nome["TIM Ultracombo 6 1GIGA + 70GB"]
        self.assertEqual((sete["preco_promocional"], sete["degrau_mbps"],
                          sete["franquia_anunciada_gb"]), (89.99, 600, 65))
        self.assertEqual((seis["preco_promocional"], seis["degrau_mbps"],
                          seis["franquia_anunciada_gb"]), (139.99, 1000, 70))

    def test_nao_le_o_preco_que_sobrou_de_campanha(self):
        self.assertIn("129,99", self.html,
                      "o recorte tem de carregar o preco velho para medir algo")
        combos, _ = tim.ler_combos(None, "http://x")
        self.assertNotIn(129.99, [o["preco_promocional"] for o in combos])

    def test_a_oferta_GRAVADA_sai_como_saia_em_16_11(self):
        u"""O caminho de producao: o que coletar() poe na linha. Os
        valores sao os gravados em 16/11, antes da troca de formato."""
        r = tim.coletar("Sao Paulo", "SP", verbose=False)
        combo = dict((o["nome_oferta"], o) for o in r["ofertas"]
                     if o.get("produto") == "combo")
        self.assertEqual(len(combo), 2, r["avisos"])
        self.assertFalse([a for a in r["avisos"] if a.startswith("combo")])
        sete = combo["TIM Ultracombo 7 600MEGA + 65GB"]
        seis = combo["TIM Ultracombo 6 1GIGA + 70GB"]
        self.assertEqual(sete["nivel_bundle"], 1)
        self.assertEqual(sete["apps"], ["aya_books", "aya_ensinah"])
        self.assertEqual(seis["nivel_bundle"], 3)
        self.assertEqual(seis["apps"],
                         ["paramount", "deezer", "aya_books", "aya_ensinah"])
        self.assertEqual(seis["apps_rotulo"],
                         "Paramount+ + Deezer + Aya Books + Aya Ensinah")


if __name__ == "__main__":
    unittest.main(verbosity=2)
