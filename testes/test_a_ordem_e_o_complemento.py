# -*- coding: utf-8 -*-
u"""A ordem dos blocos, a cidade que ficou de fora e a ressalva da
leitura - os tres pedidos de 05/11/2026, medidos na mensagem.

A MENSAGEM DAQUELE DIA, que gerou os tres:

    Fibra · Claro Fibra 750 Mega          <- a Claro mexeu em tres
    Controle · Claro Controle                produtos e a mensagem
    Pós-pago · Claro                         contou em cinco blocos,
    Controle · Claro                         com o Pos-pago no meio
    Controle · Claro                        dos tres de Controle

      em 19 de 20: Aracaju, Belo Horizonte, Blumenau e mais 16 [...]

    4 ofertas mudaram de versão sem mexer em preço nem entrega (TIM) —
    a leitura mudou hoje: a barra de caminho de arquivo deixou de ser
    lida como escolha, e a lista de apps passou a ler o mesmo texto que
    o nível de bundle lê, em vez da composição cortada em 400
    caracteres.

  1. "vc colocou Fibra no meio das mensagens de controle. Ficou uma
     ordem ruim." -> o grupo (produto, player) passa a mandar na ordem.
  2. "Quando houve aumento em 19 de 20 cidades, fale qual nao mudou."
     -> a cidade tomada por outro evento se nomeia, com a palavra que
     o dado autoriza: ela se mexeu, so nao neste bloco.
  3. "O ultimo paragrafo nao faz o menor sentido." -> duas ofertas em
     quatro eventos viravam "4 ofertas", e a causa saia na linguagem do
     parser.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                    # noqa: E402
from coletores.pracas import PRACAS, rotulo                    # noqa: E402
from _apoio import (HOJE, ONTEM, dados, montar, oferta,         # noqa: E402
                    sem_declaracao)

TODAS = [rotulo(p) for p in PRACAS]
CIDADES = [p.split("/")[0] for p in TODAS]


def fibra(preco, data, pracas, nome=u"Claro Fibra 750 Mega"):
    return [oferta(operadora="Claro", produto="fibra", nome=nome,
                   preco=preco, gb=None, mbps=750, praca=p, data=data,
                   chave="Claro|fibra|750mbps|simples")
            for p in pracas]


def degrau(preco, gb, data, praca, nome=u"Claro Controle"):
    u"""Um degrau da escada do Controle, numa praca."""
    return oferta(operadora="Claro", produto="controle", nome=nome,
                  preco=preco, gb=gb, praca=praca, data=data,
                  chave="Claro|controle|%dgb|com_claro_controle" % gb)


class OComplementoSeNomeia(unittest.TestCase):
    u"""A cidade de fora tem tres estados, e so dois se nomeiam."""

    def setUp(self):
        sem_declaracao(self)

    def _reajuste_com_uma_perna(self, quantas, outro_preco=80.0):
        u"""Reajuste em N pracas e OUTRO reajuste nas que faltam.

        E o caso de 30/10/2026: a mesma oferta com preco diferente em
        Sao Paulo rende dois eventos, e o de 19 pracas nao podia dizer
        "ex-Sao Paulo" - lá a oferta se mexeu. Dizia, no lugar, tres
        nomes em ordem alfabetica e "e mais 16".
        """
        ontem = fibra(100.0, ONTEM, TODAS)
        hoje = (fibra(90.0, HOJE, TODAS[:quantas])
                + fibra(outro_preco, HOJE, TODAS[quantas:]))
        return montar(ontem, hoje)

    def test_a_cidade_que_se_mexeu_em_outro_evento_se_nomeia(self):
        t = self._reajuste_com_uma_perna(19)
        self.assertIn("em 19 das 20 cidades; %s sai em separado"
                      % CIDADES[19], t)
        self.assertNotIn("e mais 16", t)
        # E NAO PODE SAIR COMO PARADA: lá o preco mudou, para outro
        # valor. "ex-" afirma que a cidade foi olhada e nada mudou.
        self.assertNotIn("ex-%s" % CIDADES[19], t)

    def test_duas_cidades_saem_no_plural(self):
        t = self._reajuste_com_uma_perna(18)
        a, b = sorted(CIDADES[18:20])
        self.assertIn("em 18 das 20 cidades; %s e %s saem em separado"
                      % (a, b), t)

    def test_com_muitas_de_fora_volta_a_lista_do_que_mudou(self):
        u"""A frase da excecao existe para ser mais curta E dizer mais."""
        t = self._reajuste_com_uma_perna(10)
        self.assertNotIn("sai em separado", t)
        self.assertNotIn("saem em separado", t)
        self.assertIn("em 10 de 20", t)

    def test_a_cidade_sem_ontem_nao_se_nomeia(self):
        u"""Nao comparada e o terceiro estado, e ele nao tem frase.

        Em 13/10/2026 a coleta de Belo Horizonte do dia anterior
        falhou, o reajuste da Claro alcancou BH como as outras 19 e a
        primeira versao desta regra dizia "ex-Belo Horizonte". Nao
        houve nada em BH para olhar: faltou o dia de antes.
        """
        ontem = fibra(100.0, ONTEM, TODAS[:19])
        hoje = fibra(90.0, HOJE, TODAS)
        t = montar(ontem, hoje)
        self.assertNotIn("ex-", t)
        self.assertNotIn("em separado", t)

    def test_a_escada_dividida_nomeia_a_cidade_da_outra_perna(self):
        u"""O caso de 05/11/2026, que motivou o pedido.

        A escada do Claro Controle deslizou nas tres pracas; na
        terceira o degrau de 59,90 nao deslizou. Sao dois eventos de
        grade, e o evento de grade nao fala de uma oferta - fala do
        portfolio -, entao ele nao tinha pegada comparavel nenhuma e
        nao podia nomear ninguem. Ver _escada_do_evento.
        """
        tres = TODAS[:3]
        ontem = [degrau(p, gb, ONTEM, c)
                 for c in tres for p, gb in ((59.90, 40), (69.90, 45))]
        hoje = [degrau(p, gb, HOJE, c)
                for c in tres[:2] for p, gb in ((59.90, 45), (69.90, 50))]
        hoje += [degrau(59.90, 40, HOJE, tres[2]),
                 degrau(69.90, 50, HOJE, tres[2])]
        t = montar(ontem, hoje)
        self.assertIn("em 2 das 3 cidades; %s sai em separado"
                      % tres[2].split("/")[0], t)

    def test_a_escada_sem_a_cidade_em_ontem_nao_nomeia(self):
        u"""Mesma guarda da oferta, agora na escada: cidade que nao
        tinha preco e degrau legiveis nos dois dias nao foi olhada."""
        tres = TODAS[:3]
        ontem = [degrau(p, gb, ONTEM, c)
                 for c in tres[:2] for p, gb in ((59.90, 40), (69.90, 45))]
        hoje = [degrau(p, gb, HOJE, c)
                for c in tres for p, gb in ((59.90, 45), (69.90, 50))]
        t = montar(ontem, hoje)
        # AS DUAS FORMAS, e nao so a nova: sem a guarda, a cidade sem
        # ontem volta a ser "parada" e sai como "ex-" - que foi o
        # defeito de 13/10/2026. O provador cobrou: a primeira versao
        # deste teste media so "em separado" e a mutacao Dc3 passou
        # verde, porque o codigo quebrado nomeia a cidade pela OUTRA
        # frase.
        self.assertNotIn("em separado", t)
        self.assertNotIn("ex-", t)


class AOrdemAgrupaPorProdutoEPlayer(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def _tres_produtos(self):
        ontem, hoje = self._fixture()
        return montar(ontem, hoje)

    def _fixture(self):
        u"""A Claro mexendo em fibra (preco) e em controle (escada).

        A ESCADA SAI EM DOIS BLOCOS E O POS-PAGO FICA ENTRE ELES na
        ordem dos detectores, que e a ordem por efeito: a perna forte do
        Controle pesa 0,50 (40 para 60 GB), o Pos-pago 0,20 e a perna
        fraca do Controle 0,044. Sem esses tres pesos nesta ordem o
        teste nao mede nada - a mutacao Dc5 passou verde na primeira
        versao, em que as duas pernas do Controle ja nasciam vizinhas e
        agrupar nao mudava nada.
        """
        tres = TODAS[:3]
        ontem = fibra(129.90, ONTEM, tres)
        hoje = fibra(99.90, HOJE, tres)
        ontem += [degrau(p, gb, ONTEM, c)
                  for c in tres for p, gb in ((59.90, 40), (69.90, 45))]
        # perna forte, em duas pracas: +50% no degrau de 59,90
        hoje += [degrau(p, gb, HOJE, c)
                 for c in tres[:2] for p, gb in ((59.90, 60), (69.90, 50))]
        # perna fraca, na terceira: +4,4% no degrau de 69,90
        hoje += [degrau(59.90, 40, HOJE, tres[2]),
                 degrau(69.90, 47, HOJE, tres[2])]
        # o terceiro produto, com peso no meio: +20%
        ontem += [oferta(operadora="Claro", produto="movel",
                         nome="Claro Pós", preco=124.90, gb=50,
                         praca=tres[0], data=ONTEM,
                         chave="Claro|movel|50gb|com_apps")]
        hoje += [oferta(operadora="Claro", produto="movel",
                        nome="Claro Pós", preco=124.90, gb=60,
                        praca=tres[0], data=HOJE,
                        chave="Claro|movel|60gb|com_apps")]
        return ontem, hoje

    def test_a_ordem_dos_detectores_poe_outro_produto_no_meio(self):
        u"""O CONTROLE DO TESTE DE CIMA. Se os tres pesos deixarem de
        por o Pos-pago entre as duas pernas do Controle, agrupar nao
        muda nada e o teste de cima passa a medir o nada."""
        d = dados(*self._fixture())
        pesos = [robo._por_efeito(g) for g in d["grades"]]
        self.assertEqual(sorted(pesos, reverse=True), pesos,
                         "a lista de grades nao esta ordenada por efeito")
        produtos = [g["produto"] for g in d["grades"]]
        self.assertEqual(produtos, ["controle", "movel", "controle"],
                         "o pos-pago tem de nascer ENTRE as duas pernas")

    def _cabecalhos(self, texto):
        return [l for l in texto.splitlines() if " · " in l
                and not l.startswith(" ") and not l.startswith("TMT")
                and not l.startswith("Relat")]

    def test_os_blocos_do_mesmo_produto_ficam_juntos(self):
        cabs = self._cabecalhos(self._tres_produtos())
        produtos = [c.split(" · ")[0] for c in cabs]
        # dois blocos de Controle, e nada entre eles
        self.assertEqual(produtos.count("Controle"), 2, produtos)
        primeiro = produtos.index("Controle")
        self.assertEqual(produtos[primeiro + 1], "Controle", produtos)

    def test_o_reajuste_continua_abrindo_a_mensagem(self):
        u"""A ordem dos detectores nao foi jogada fora: ela decide a
        posicao do GRUPO, pelo bloco mais forte que ele tem."""
        cabs = self._cabecalhos(self._tres_produtos())
        self.assertTrue(cabs[0].startswith("Fibra"), cabs)

    def test_a_cauda_do_corte_fica_no_fim(self):
        u"""e mais N no relatorio" fala do CANAL, e nao do player.

        Colada no ultimo bloco do grupo, a frase parecia dizer que as
        que faltam eram daquele player.
        """
        ontem = fibra(100.0, ONTEM, TODAS[:4])
        hoje = (fibra(90.0, HOJE, TODAS[:1]) + fibra(80.0, HOJE, TODAS[1:2])
                + fibra(70.0, HOJE, TODAS[2:3])
                + fibra(60.0, HOJE, TODAS[3:4]))
        t = montar(ontem, hoje)
        linhas = [l for l in t.splitlines() if l.strip()]
        corte = [i for i, l in enumerate(linhas)
                 if l.startswith("e mais 1 mudan")]
        self.assertTrue(corte, t)
        depois = linhas[corte[0] + 1:]
        self.assertFalse([l for l in depois if " · " in l
                          and not l.startswith("Relat")],
                         "nenhum bloco pode vir depois da cauda: %s" % depois)


class ARessalvaEmLinguagemDeLeitor(unittest.TestCase):
    u"""A data de _apoio (21/10) e declarada, entao a mudanca de versao
    cai na ressalva da leitura - que e o que se mede aqui."""

    def _duas_ofertas_em_quatro_eventos(self):
        u"""Duas ofertas, cada uma com preco diferente numa praca.

        E o dia 05/11/2026: a TIM Ultracombo 6 e a 7 mudaram de versao
        nas 20 pracas, e porque Sao Paulo tem outro preco (89,99 e
        139,99 contra 99,99 e 149,99) cada uma rendeu dois eventos. A
        mensagem publicou "4 ofertas".
        """
        def combo(nome, preco, variante, data, pracas):
            return [oferta(operadora="TIM", produto="combo", nome=nome,
                           preco=preco, gb=None, mbps=600, praca=p,
                           data=data,
                           chave="TIM|combo|600mbps|%s" % variante)
                    for p in pracas]
        ontem, hoje = [], []
        for nome, caro, barato in ((u"TIM Ultracombo 7", 99.99, 89.99),
                                   (u"TIM Ultracombo 6", 149.99, 139.99)):
            ontem += combo(nome, caro, "com_apps", ONTEM, TODAS[:19])
            ontem += combo(nome, barato, "com_apps", ONTEM, TODAS[19:])
            hoje += combo(nome, caro, "com_mais_apps", HOJE, TODAS[:19])
            hoje += combo(nome, barato, "com_mais_apps", HOJE, TODAS[19:])
        return ontem, hoje

    def test_conta_ofertas_e_nao_eventos(self):
        ontem, hoje = self._duas_ofertas_em_quatro_eventos()
        d = dados(ontem, hoje)
        self.assertEqual(len(d["leitura"]), 4, "sao quatro eventos")
        t = montar(ontem, hoje)
        self.assertIn("2 ofertas mudaram de vers", t)
        self.assertNotIn("4 ofertas mudaram", t)

    def test_a_causa_sai_em_uma_linha_e_a_tecnica_vai_no_relatorio(self):
        ontem, hoje = self._duas_ofertas_em_quatro_eventos()
        t = montar(ontem, hoje)
        self.assertIn(robo.LEITURA_EM_UMA_LINHA[HOJE], t)
        self.assertNotIn(robo.LEITURA_MUDOU_EM[HOJE], t)
        d = dados(ontem, hoje)
        self.assertEqual(d["leitura_declarada"], robo.LEITURA_MUDOU_EM[HOJE])

    def test_toda_data_declarada_tem_frase_de_leitor(self):
        u"""O PORTAO DO PASSO SEGUINTE. Declarar a data e um passo
        consciente - alguem escreve o comentario e a frase tecnica -, e
        sem este teste a frase de leitor seria o passo que se esquece:
        a mensagem cairia na declaracao longa sem avisar ninguem.
        """
        faltam = sorted(set(robo.LEITURA_MUDOU_EM) -
                        set(robo.LEITURA_EM_UMA_LINHA))
        self.assertEqual(faltam, [], "datas sem frase de uma linha")

    def test_a_frase_de_leitor_cabe_numa_linha(self):
        longas = {d: len(t) for d, t in robo.LEITURA_EM_UMA_LINHA.items()
                  if len(t) > 120}
        self.assertEqual(longas, {}, "frase de leitor longa demais")


if __name__ == "__main__":
    unittest.main()
