# -*- coding: utf-8 -*-
u"""O Prezao da Claro: "17GB + 3GB Youtube" sao 20 GB.

Ate 24/11/2026 a leitura tomava o 17 como o total e o 3 como parte dele:
gravava 17 GB anunciados e 14 de uso livre. O card da propria Claro
desfaz a duvida - "Melhor opcao 20GB R$30/30 dias - Para uso livre 17GB,
Para YouTube 3GB" -, e o de R$ 25 diz "12GB" sobre "10GB + 2GB".

Texto da tabela copiado da pagina em 24/11/2026.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import apps, claro                             # noqa: E402

TABELA = (u"<div>Conheça as recargas da renovação parcial</div><p>Prezão R$ 1 "
          u"por dia</p><div>Valor do saldo</div><span>R$ 30,00</span>"
          u"<span>R$ 25,00</span><span>R$ 20,00</span><span>R$ 15,00</span>"
          u"<h3>PREZÃO R$1 POR DIA</h3><li>17GB + 3GB Youtube / 30 dias</li>"
          u"<li>10GB + 2GB Youtube / 25 dias</li><li>8GB + 2GB Youtube / 20 "
          u"dias</li><li>5GB / 15 dias</li><p>WhatsApp ilimitado com "
          u"videochamadas + Ligações para todo Brasil</p>")


class OPrezaoSoma(unittest.TestCase):

    def setUp(self):
        guarda = claro.buscar
        claro.buscar = lambda op, url, *a, **k: (200, TABELA)
        self.addCleanup(setattr, claro, "buscar", guarda)

    def test_as_quatro_recargas_com_a_validade(self):
        u"""Desde 25/11/2026 entram as quatro, cada uma com os dias que
        vale - escolha de quem le: "Todas, com a validade"."""
        ofertas, erro = claro.ler_prezao(None, "http://x")
        self.assertIsNone(erro)
        lidas = [(o["nome_oferta"], o["preco_promocional"],
                  o["franquia_anunciada_gb"], o["franquia_contratual_gb"],
                  o["validade_dias"]) for o in ofertas]
        self.assertEqual(lidas, [
            ("Claro Prezao 20GB", 30.0, 20, 17, 30),
            ("Claro Prezao 12GB", 25.0, 12, 10, 25),
            ("Claro Prezao 10GB", 20.0, 10, 8, 20),
            ("Claro Prezao 5GB", 15.0, 5, None, 15),
        ])

    def test_os_outros_degraus_ficam_na_composicao(self):
        ofertas, _ = claro.ler_prezao(None, "http://x")
        self.assertIn("R$ 15,00 = 5GB", ofertas[0]["composicao"])


class OSkeeloDasVantagensDoPre(unittest.TestCase):
    u"""A pagina oferece o Skeelo "para clientes Claro Pre", fora do card
    da recarga. Texto copiado da pagina em 24/11/2026."""

    VANTAGEM = (u"<h4>Skeelo</h4><p>Plataforma digital de incentivo à leitura "
                u"que disponibiliza um best-seller por mês para clientes "
                u"Claro Pré.</p>")

    def _ler(self, html):
        guarda = claro.buscar
        claro.buscar = lambda op, url, *a, **k: (200, html)
        self.addCleanup(setattr, claro, "buscar", guarda)
        return claro.ler_prezao(None, "http://x")[0][0]

    def test_com_a_vantagem_o_prezao_traz_o_skeelo(self):
        o = self._ler(self.VANTAGEM + TABELA)
        self.assertTrue(o["composicao"].startswith("Inclui Skeelo"))
        self.assertEqual(apps.apps_do_texto(o["composicao"]), ["skeelo"])

    def test_sem_a_vantagem_nao_traz(self):
        o = self._ler(TABELA)
        self.assertEqual(apps.apps_do_texto(o["composicao"]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
