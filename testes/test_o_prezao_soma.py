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

from coletores import claro                                   # noqa: E402

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

    def test_o_degrau_de_30_dias_e_20_gb_com_17_de_uso_livre(self):
        ofertas, erro = claro.ler_prezao(None, "http://x")
        self.assertIsNone(erro)
        self.assertEqual(len(ofertas), 1)
        o = ofertas[0]
        self.assertEqual((o["nome_oferta"], o["preco_promocional"],
                          o["franquia_anunciada_gb"], o["franquia_contratual_gb"]),
                         ("Claro Prezao 20GB", 30.0, 20, 17))

    def test_os_outros_degraus_ficam_na_composicao(self):
        ofertas, _ = claro.ler_prezao(None, "http://x")
        self.assertIn("R$ 15,00 = 5GB", ofertas[0]["composicao"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
