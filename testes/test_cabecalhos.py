# -*- coding: utf-8 -*-
"""Os cabecalhos que carregam peso, e os que nao carregam.

A metodologia listava "cabecalhos das outras cinco operadoras" como
pendencia desde 01/10/2026: sabia-se que a Vivo exigia o conjunto
completo de navegador e nao se sabia das demais. Medido em 27/10/2026,
contra as fontes de verdade:

  Vivo         403 sem o conjunto completo. Reproduzido duas vezes: so
               com User-Agent a resposta e 403 limpo; com o conjunto,
               200 e 530 KB. E a unica que BARRA.
  Claro, TIM   ja mandam o conjunto completo.
  Brisanet     254.748 bytes identicos com UA sozinho, com os
               cabecalhos de hoje e com o conjunto completo. Nao muda
               nada.
  TIM FIT      200 nos tres casos, com diferenca de 133 bytes entre
               leituras seguidas - variacao da propria pagina, nao do
               cabecalho.
  Starlink     200 nos tres, MAS o conteudo muda: sem Accept-Language a
               resposta vem em ingles. Ver abaixo.
  Unifique,
  NuCel,
  Claro Flex   sobem Chromium pelo Playwright: os cabecalhos sao de um
               navegador de verdade e nao passam por aqui.

A LICAO DO STARLINK e a que vale guardar: cabecalho que nao muda o
STATUS ainda pode mudar o CONTEUDO. Olhar so para o 200 teria fechado a
pendencia dizendo "nao precisa".
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import brisanet, claro, starlink, tim, tim_fit, vivo  # noqa: E402

PRECISA_DE_NAVEGADOR = ("Accept-Language", "Sec-Fetch-Mode",
                        "Upgrade-Insecure-Requests")


def _pedidos(modulo, chamar):
    """Roda `chamar` com a rede desligada e devolve os cabecalhos pedidos.

    Mede o que o coletor MANDA, no caminho de producao, sem bater na
    fonte. Testar a constante nao provaria nada: o que chega na
    operadora e o que foi posto no Request.
    """
    import urllib.request
    vistos = []
    original = urllib.request.urlopen

    def espiao(req, *a, **kw):
        vistos.append(dict(getattr(req, "headers", {}) or {}))
        raise RuntimeError("rede desligada no teste")

    # SEM AS ESPERAS DA RETENTATIVA. rede.insistir tenta tres vezes,
    # com 2s e 5s entre elas: o teste levava 7 segundos para medir um
    # cabecalho, e aqui a falha e proposital - nao ha o que insistir.
    #
    # Trocar rede.ESPERAS nao resolve: ela e VALOR PADRAO do parametro
    # de insistir(), e o padrao foi avaliado quando a funcao foi
    # definida. Quem dorme e o time.sleep de dentro, e e ele que sai.
    from coletores import rede
    dormir = rede.time.sleep
    rede.time.sleep = lambda *_: None
    urllib.request.urlopen = espiao
    try:
        try:
            chamar()
        except Exception:
            pass
    finally:
        urllib.request.urlopen = original
        rede.time.sleep = dormir
    return vistos


class OStarlinkPedeEmPortugues(unittest.TestCase):
    u"""Accept-Language e carga: sem ele a resposta vem em ingles.

    Dois efeitos, os dois silenciosos:

      O NOME MUDA. "Residencial: 100 Mbps" vira "Residential - 100
      Mbps". O nome entra na identidade da oferta, entao trocar a lingua
      faria toda a Starlink parecer nova no mesmo dia.

      A VELOCIDADE DECLARADA SOME. Em portugues o Max traz "Ate mais de
      400 Mbps"; em ingles, "Up to 400+ Mbps", que a leitura nao casa
      porque o "+" fica entre o numero e a unidade.
    """

    def test_o_pedido_declara_portugues(self):
        vistos = _pedidos(starlink, lambda: starlink._http(
            "https://www.starlink.com/api/nao-vai-sair-daqui"))
        self.assertTrue(vistos, "nenhum pedido foi montado")
        lingua = vistos[0].get("Accept-language") or vistos[0].get(
            "Accept-Language") or ""
        self.assertIn("pt", lingua.lower())

    def test_a_leitura_em_ingles_perderia_a_frase(self):
        """A medicao que justifica o cabecalho, congelada como teste.

        Se um dia a leitura passar a entender o "400+", este teste cai -
        e ai o cabecalho deixa de ser a unica defesa, o que e uma
        melhora. Ele existe para que a mudanca seja NOTADA.
        """
        pt = u"Nosso serviço. \n * Até mais de 400 Mbps\n * Dados"
        en = u"Our best service. \n* Up to 400+ Mbps\n* Unlimited Data"
        self.assertEqual(starlink.velocidade_declarada(pt),
                         u"Até mais de 400 Mbps")
        self.assertIsNone(starlink.velocidade_declarada(en))

    def test_nem_em_portugues_nem_em_ingles_sai_um_degrau_falso(self):
        """A faixa nao vira numero em lingua nenhuma - o 400 falso no
        grafico foi o defeito que criou velocidade_declarada."""
        self.assertIsNone(starlink.velocidade(u"Até mais de 400 Mbps"))
        self.assertIsNone(starlink.velocidade(u"Up to 400+ Mbps"))

    def test_o_teto_do_mesmo_numero_continua_valendo(self):
        """Controle: "Ate 100 Mbps" e teto, nao faixa, e tem de ler."""
        self.assertEqual(starlink.velocidade(u"Até 100 Mbps"), 100)
        self.assertEqual(starlink.velocidade(u"Up to 100 Mbps"), 100)


class AVivoPedeComoNavegador(unittest.TestCase):
    u"""A unica das nove que BARRA sem o conjunto completo: 403."""

    @staticmethod
    def _cabecalhos(modulo):
        # a Vivo devolve (opener, cookiejar); Claro e TIM devolvem so o
        # opener - o teste nao pode supor a mesma forma nas tres
        r = modulo.navegador()
        op = r[0] if isinstance(r, tuple) else r
        return dict(op.addheaders)

    def test_o_navegador_da_vivo_manda_o_conjunto(self):
        cab = self._cabecalhos(vivo)
        for h in PRECISA_DE_NAVEGADOR:
            self.assertIn(h, cab, "a Vivo responde 403 sem %s" % h)

    def test_claro_e_tim_mandam_o_mesmo_conjunto(self):
        """Nao foi medido que elas BARRAM, mas elas ja mandam - e tirar
        agora seria mexer sem medir."""
        for modulo in (claro, tim):
            cab = self._cabecalhos(modulo)
            for h in PRECISA_DE_NAVEGADOR:
                self.assertIn(h, cab, "%s perdeu %s" % (modulo.__name__, h))


class OQueNaoCarregaPeso(unittest.TestCase):
    u"""Medido que nao muda nada - e registrado para nao se medir de novo.

    Estes testes nao impedem ninguem de ADICIONAR cabecalho; eles
    guardam o motivo de nao ter sido adicionado, que e a parte que se
    perde.
    """

    def test_brisanet_manda_o_minimo_de_proposito(self):
        self.assertTrue(hasattr(brisanet, "UA"))
        self.assertIn("Mozilla", brisanet.UA)

    def test_tim_fit_manda_o_minimo_de_proposito(self):
        self.assertTrue(hasattr(tim_fit, "UA"))
        self.assertIn("Mozilla", tim_fit.UA)


if __name__ == "__main__":
    unittest.main(verbosity=2)
