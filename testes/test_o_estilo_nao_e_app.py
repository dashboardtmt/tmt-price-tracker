# -*- coding: utf-8 -*-
u"""O CSS da pagina da TIM nao e nome de app.

Desde 21/10/2026 o campo de preco do TIM Pre XIP traz um <style> com
".service img { max-width: 110px }". A limpeza tirava as tags e deixava
o conteudo do estilo, e "max" virava o app Max: as recargas de R$ 20 e
R$ 25 entraram na serie com HBO Max e nivel 2, em 1.400 linhas, sem Max
nenhum na pagina. Campo copiado da pagina em 24/11/2026.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import tim                                     # noqa: E402

CAMPO = (u'<p>R$20 por 17 dias</p>\r\n\r\n<p style="font-weight: 400; color: '
         u'#696969;">Sua recarga no app Meu TIM com benefícios exclusivos</p>'
         u'\r\n<div class="container1 spaced-section-sm">\r\n<div class="service">'
         u'<img alt="Logotipo Zé Delivery, streaming disponível em ofertas TIM '
         u'Pré XIP" src="logo-ze-delivery-desconto.webp" /></div>\r\n</div>\r\n'
         u'<style type="text/css">/*Estilo do grid*/\r\n.container1 { width: '
         u'246px; display: grid; }\r\n.service img { max-width: 110px; height: '
         u'auto; }\r\n</style>')


class OEstiloNaoEApp(unittest.TestCase):

    def test_o_texto_do_campo_nao_traz_o_css(self):
        t = tim.texto([{"value": CAMPO}])
        self.assertIn("R$20 por 17 dias", t)
        self.assertNotIn("max-width", t)
        self.assertNotIn("grid", t)

    def test_a_recarga_nao_ganha_o_max(self):
        pagina = ('<script data-drupal-selector="drupal-settings-json">'
                  + json.dumps({"ofertas": [{
                      "field_subtitle": [{"value": u"TIM Pré XIP Plus"}],
                      "field_titulo": [{"value": "6GB"}],
                      "field_information_text": [{"value": "6GB da oferta"}],
                      "field_preco_card_oferta": [{"value": "20,00"}],
                      "field_preco_principal_7_1_3": [{"value": CAMPO}]}]})
                  + "</script>")
        guarda = tim.buscar
        tim.buscar = lambda op, url, *a, **k: (200, pagina)
        self.addCleanup(setattr, tim, "buscar", guarda)
        ofertas, erro = tim.ler_ofertas(None, "http://x", "SP")
        self.assertIsNone(erro)
        self.assertFalse(ofertas[0]["apps"])
        self.assertEqual(ofertas[0]["nivel_bundle"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
