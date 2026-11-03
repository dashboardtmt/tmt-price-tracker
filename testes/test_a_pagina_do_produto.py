# -*- coding: utf-8 -*-
u"""A PAGINA-HUB NAO E A VITRINE: achado em 03/11/2026 comparando o
tracker com o report de precos da JPMorgan de 30/10.

Eles publicavam R$ 129,99 como preco de entrada do pos-pago da TIM; o
tracker publicava R$ 169,99, 31% acima, nos 35 dias e nas 20 pracas da
serie inteira - o valor 129,99 aparecia ZERO vezes na base. A causa: a
TIM era a unica das seis operadoras lida por pagina-hub, e a hub
destaca dois planos Black onde a pagina de produto lista dez. O balde
do movel tinha 2 planos onde a Vivo tem 11 e a Claro 5.

Nenhuma guarda do projeto olhava para isso: o vigia compara a contagem
de hoje com a dos dias anteriores, nunca com o que a fonte publica -
balde que nasce magro fica magro para sempre.

Os testes aqui fixam as tres decisoes do leitor novo:

  1. a franquia sai SO da descricao, porque o mesmo card traz tres
     numeros diferentes para o mesmo plano
  2. "ate N gigas" nao e franquia, e card sem franquia entra sem ela
  3. sem franquia declarada a chave colide, e a identidade passa a sair
     do nome do degrau
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import armazenamento, tim                      # noqa: E402


def card(nome, preco, descricao, alt="", ufs="sp,rj,am"):
    """Um <tim-card-dynamic> com a forma que a TIM publica."""
    return (
        '<tim-card-dynamic class="coh-inline-element" cta="Contratar" '
        'alt="%s" regionalization-toggle="%s" link="https://loja/x"> '
        '<div class="coh-container" slot="header" > '
        '<h4 class="coh-heading paragraph-md">%s</h4>  '
        '<p class="coh-paragraph tim-mb-0 paragraph-lg">%s</p> </div>  '
        '<div class="coh-container" slot="footer" >  '
        '<p class="coh-paragraph paragraph-sm">Por apenas</p>  '
        '<p class="coh-paragraph tim-mb-0 tim-mt-0 paragraph-lg">'
        'R$%s/mes</p> </div> </tim-card-dynamic>'
        % (alt, ufs, nome, descricao, preco))


# a pagina de 03/11/2026, reduzida aos casos que decidem
PAGINA = "<html><body>" + "".join([
    card("TIM Black", "129,99",
         "Pos-pago 70GB com 1 servico incluso para trocar todo mes!",
         alt="Pos-pago TIM Black com 70 gigas"),
    card("TIM Black Premium", "169,99",
         "Pos-pago 110GB com 1 servico incluso para trocar todo mes!",
         alt="Pos-pago TIM Black Premium com 100 gigas"),
    card("TIM Black A Express", "119,99",
         "Pos-pago com Deezer incluso, apps e muito mais",
         alt="Le-se: ate 67 gigas e liberdade para escolher"),
    card("TIM Black B Express", "144,99",
         "Pos-pago com Deezer incluso, muita internet e apps para usar",
         alt="Pos-pago TIM Black ate 112 gigas traz Deezer"),
    card("TIM Black C Express", "164,99",
         "Pos-pago com Deezer incluso, muita internet e apps para usar",
         alt="Pos-pago TIM Black ate 127 gigas traz Deezer"),
    card("TIM Black Familia VIP", "399,99",
         "Pos-pago com servicos inclusos e 5 dependentes gratis"),
    card("TIM Black Familia Plus", "284,99",
         "Pos-pago com servicos inclusos e 2 dependentes gratis"),
]) + "</body></html>"


class ALeituraDaPaginaDeProduto(unittest.TestCase):

    def _pagina(self, html):
        guarda = tim.buscar
        tim.buscar = lambda op, url, **k: (200, html)
        self.addCleanup(lambda: setattr(tim, "buscar", guarda))

    def _ler(self, html=PAGINA, uf="SP"):
        self._pagina(html)
        cards, erro = tim.ler_cards_dinamicos(None, "http://x", uf)
        self.assertIsNone(erro, erro)
        return {c["nome_oferta"]: c for c in cards}

    def test_le_os_planos_que_a_hub_nao_mostra(self):
        por_nome = self._ler()
        self.assertIn("TIM Black", por_nome)
        self.assertEqual(por_nome["TIM Black"]["preco_promocional"], 129.99)
        self.assertEqual(por_nome["TIM Black A Express"]["preco_promocional"],
                         119.99)
        self.assertEqual(len(por_nome), 7)

    def test_a_franquia_sai_da_descricao_e_nunca_do_alt(self):
        """O card do Premium diz "110GB" na descricao e "com 100 gigas"
        no alt da imagem. Ler o alt seria gravar como contrato o numero
        que a pagina usa para acessibilidade."""
        premium = self._ler()["TIM Black Premium"]
        self.assertEqual(premium["franquia_anunciada_gb"], 110)
        self.assertEqual(premium["destaque"], "110GB")

    def test_ate_n_gigas_nao_vira_franquia(self):
        """"ate 67 gigas" e teto, nao franquia. Sem numero na descricao,
        a oferta entra SEM franquia - do jeito que a fibra da Brisanet
        ja entra. A mensagem sabe lidar com entrega vazia e nao sabe
        lidar com entrega inventada."""
        for nome in ("TIM Black A Express", "TIM Black B Express",
                     "TIM Black C Express"):
            o = self._ler()[nome]
            self.assertIsNone(o["franquia_anunciada_gb"], nome)
            self.assertIsNone(o["destaque"], nome)

    def test_a_uf_do_card_e_respeitada(self):
        """O card declara em que UF vale. Sem olhar para isso, o tracker
        gravaria em Manaus uma oferta que a TIM so vende em Sao Paulo."""
        html = ("<html>" + card("So em SP", "99,99", "Pos-pago 10GB",
                                ufs="sp")
                + card("No pais", "88,88", "Pos-pago 20GB",
                       ufs="sp,am") + "</html>")
        self.assertEqual(sorted(self._ler(html, "AM")), ["No pais"])
        self.assertEqual(sorted(self._ler(html, "SP")), ["No pais", "So em SP"])

    def test_pagina_sem_card_dinamico_devolve_erro(self):
        """Lista vazia sem erro vira afirmacao de que a operadora nao
        vende o produto."""
        self._pagina("<html><body>nada aqui</body></html>")
        cards, erro = tim.ler_cards_dinamicos(None, "http://x", "SP")
        self.assertIsNone(cards)
        self.assertIn("formato mudou", erro)

    def test_card_sem_preco_nao_derruba_a_leitura(self):
        html = ("<html>" + card("Decorativo", "", "Conheca o pos-pago")
                + card("De verdade", "77,77", "Pos-pago 30GB") + "</html>")
        self.assertEqual(sorted(self._ler(html)), ["De verdade"])

    def test_cards_presentes_mas_nenhum_reconhecido_avisa(self):
        self._pagina("<html><tim-card-dynamic>vazio</tim-card-dynamic></html>")
        cards, erro = tim.ler_cards_dinamicos(None, "http://x", "SP")
        self.assertEqual(cards, [])
        self.assertIn("leitura falhou", erro)


class OQueOAltNaoConsegueAfirmar(unittest.TestCase):
    """O risco latente do alt, escrito com o que o mede.

    A primeira versao deste arquivo trouxe uma mutacao no provador - a
    Z2 - trocando a fonte da franquia por "gb(desc) or gb(alt)", para
    provar que "ate 67 gigas" nao viraria franquia. ELA NAO PEGOU, e
    medindo o porque: gb() exige o token "GB" e o alt escreve "gigas",
    entao ler o alt nao produz numero nenhum. O defeito que a mutacao
    descrevia nao e alcancavel, e mutacao de defeito impossivel da
    impressao de cobertura que nao existe - saiu, como saiu o escape do
    "&" no relatorio.

    O QUE SOBRA E O RISCO DE VERDADE: se a TIM passar a escrever "ate
    67GB" no alt, ler o alt comeca a produzir franquia, e a de um teto e
    nao a de um contrato. Este teste fixa o comportamento de hoje para
    que a mudanca apareca como vermelho, e nao como numero novo na
    serie.
    """

    def test_o_alt_de_hoje_nao_rende_franquia_nenhuma(self):
        for texto in ("Le-se: ate 67 gigas e liberdade para escolher",
                      "Pos-pago TIM Black ate 112 gigas traz Deezer",
                      "Pos-pago TIM Black Premium com 100 gigas"):
            self.assertIsNone(tim.gb(texto), texto)

    def test_mas_com_o_token_GB_renderia(self):
        """A medicao que decide: e o token, e nao a palavra. No dia em
        que o alt trocar "gigas" por "GB", a guarda entra em
        ler_cards_dinamicos - com dado para apontar, e nao com
        suspeita."""
        self.assertEqual(tim.gb("Pos-pago TIM Black ate 67GB"), 67)


class AIdentidadeDeQuemNaoDeclaraFranquia(unittest.TestCase):
    """Sem franquia, sete dos dez planos da pagina caem em DUAS chaves.

    Medido em 03/11/2026: os tres Express dividiam
    "TIM|movel|0gb|com_deezer" com precos de R$ 119,99, R$ 144,99 e
    R$ 164,99, e os quatro Familia dividiam "TIM|movel|0gb|familia" de
    R$ 219,99 a R$ 399,99. A serie de cada chave ficaria alternando
    entre os precos como se houvesse reajuste todo dia.
    """

    def _cards(self):
        guarda = tim.buscar
        tim.buscar = lambda op, url, **k: (200, PAGINA)
        self.addCleanup(lambda: setattr(tim, "buscar", guarda))
        cards, erro = tim.ler_cards_dinamicos(None, "http://x", "SP")
        self.assertIsNone(erro)
        saida = []
        for c in cards:
            o = dict(c, operadora="TIM",
                     produto=tim.classificar(c["nome_oferta"], c["destaque"]))
            saida.append((o["nome_oferta"],
                          armazenamento.chave_continuidade(o)))
        return saida

    def test_cada_plano_tem_chave_propria(self):
        chaves = [k for _, k in self._cards()]
        self.assertEqual(len(chaves), len(set(chaves)),
                         "dois planos de precos diferentes na mesma serie")

    def test_os_tres_express_nao_dividem_a_chave_do_deezer(self):
        por_nome = dict(self._cards())
        express = [por_nome[n] for n in ("TIM Black A Express",
                                         "TIM Black B Express",
                                         "TIM Black C Express")]
        self.assertEqual(len(set(express)), 3)
        for k in express:
            self.assertNotIn("com_deezer", k)

    def test_quem_declara_franquia_segue_a_regra_de_sempre(self):
        """A variante explicita e so para quem nao tem degrau. Com
        franquia, a chave continua saindo de _variante - senao este
        leitor criaria uma identidade paralela para plano que a hub ja
        grava de outro jeito."""
        por_nome = dict(self._cards())
        self.assertEqual(por_nome["TIM Black"], "TIM|movel|70gb|simples")
        self.assertEqual(por_nome["TIM Black Premium"],
                         "TIM|movel|110gb|simples")


class OMesmoPlanoNasDuasPaginas(unittest.TestCase):
    """Quando o plano aparece na hub e na pagina de produto, a HUB MANDA.

    E ela que a TIM atualiza na campanha: o TIM Black Premium saiu de
    110GB para 125GB na hub em 31/10/2026 enquanto a pagina de produto
    seguia dizendo 110. Sem a regra, os dois virariam duas ofertas,
    porque a deduplicacao do fim de coletar compara franquia e preco.
    """

    def test_o_nome_curto_colapsa_as_duas_grafias(self):
        self.assertEqual(tim._nome_curto("TIM Pre XIP Plus - 16GB"),
                         tim._nome_curto("TIM Pre XIP Plus"))
        self.assertEqual(tim._nome_curto("TIM Black Premium"),
                         tim._nome_curto("tim black premium"))

    def test_nomes_diferentes_nao_colapsam(self):
        self.assertNotEqual(tim._nome_curto("TIM Black"),
                            tim._nome_curto("TIM Black Plus"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
