# -*- coding: utf-8 -*-
u"""A vitrine que cala, e o evento igual que sai agrupado.

A MENSAGEM DE 23/10/2026, do jeito que chegou no celular:

    4 mudancas hoje

    Below-the-line - Claro Flex 40 GB
      mesmo preco (44,90) e mesma entrega (40 GB)
      e passou de "com apps de catalogo" para "sem assinatura inclusa"
      na unica praca em que a oferta e vendida

    ... o mesmo bloco repetido para 45 GB e 50 GB

    e mais 1 oferta remodelada no relatorio

Vinte e duas linhas, tres defeitos:

  1. AFIRMA MERCADO ONDE HOUVE PAGINA. Medido na fonte: a Claro
     reescreveu o flex.claro.com.br, que passou a ter 1.814 caracteres e
     nao contem "Skeelo", "Claro Musica", "Claro Banca", "Claro Day" nem
     "McAfee" em lugar nenhum. A vitrine parou de NOMEAR. Nivel 0 e
     "nada nomeado", e "passou para sem assinatura inclusa" converte
     esse silencio em ausencia declarada - contra a regra do projeto,
     "silencio nao e ausencia".

  2. O MESMO EVENTO EM QUATRO OFERTAS VIRA QUATRO BLOCOS, doze linhas
     repetindo as mesmas palavras, enquanto a mudanca de preco - que
     agrupa por praca - diz "em todas as 20 pracas" numa linha.

  3. E AO AGRUPAR, O NUMERO DE UMA VALEU PARA TODAS. Minha primeira
     versao do agrupamento imprimiu "mesmo preco (44,90) e mesma
     entrega (40 GB)" sob um cabecalho que falava das quatro - que
     custam R$ 44,90, R$ 59,90, R$ 69,90 e R$ 119,90. O mesmo defeito
     de eleger um representante do grupo e publicar como fato, que eu
     tinha consertado no pareamento e reintroduzi na redacao.
"""
import unittest

from _apoio import HOJE, ONTEM, montar, oferta, sem_declaracao

import robo


# como o coletor batiza cada degrau da escada de bundle
VARIANTE = {0: "simples", 1: "com_apps", 2: "com_streaming",
            3: "com_varios", 4: "com_tv"}


def flex(gb, preco, bundle, data, nome=None):
    """Uma Claro Flex, na unica praca em que ela e vendida."""
    o = oferta(operadora="Claro", produto="btl",
               nome=nome or ("Claro Flex %d GB" % gb), preco=preco, gb=gb,
               praca="Sao Paulo/SP", data=data,
               # A VARIANTE SEGUE O NIVEL. Com "com_apps" para 1 e para
               # 2, a chave ficava igual nos dois dias e o evento de
               # versao nunca nascia: o teste media silencio.
               chave="Claro|btl|%dgb|%s" % (gb, VARIANTE[bundle]))
    o["nivel_bundle"] = bundle
    return o


def as_quatro(data, bundle):
    return ([flex(40, 44.90, bundle, data)]
            + [flex(45, 59.90, bundle, data)]
            + [flex(50, 69.90, bundle, data)]
            + [flex(60, 119.90, bundle, data,
                    nome="Claro Flex Passaporte 60 GB")])


class ASilenciosaNaoDizQueSaiu(unittest.TestCase):
    def setUp(self):
        sem_declaracao(self)

    def test_a_frase_fala_da_vitrine_e_nao_da_oferta(self):
        t = montar(as_quatro(ONTEM, 1), as_quatro(HOJE, 0))
        self.assertIn("a vitrine parou de nomear os apps", t)
        self.assertIn("silêncio não confirma que saíram", t)

    def test_e_nao_afirma_que_a_oferta_perdeu_a_assinatura(self):
        """A frase antiga. Nivel 0 e "nada nomeado": dali nao se conclui
        que a oferta nao tem assinatura."""
        t = montar(as_quatro(ONTEM, 1), as_quatro(HOJE, 0))
        self.assertNotIn("para \"sem assinatura inclusa\"", t)

    def test_no_sentido_inverso_tambem_fala_da_vitrine(self):
        t = montar(as_quatro(ONTEM, 0), as_quatro(HOJE, 1))
        self.assertIn("a vitrine passou a nomear", t)
        self.assertNotIn("passou de \"sem assinatura inclusa\"", t)

    def test_entre_dois_niveis_nomeados_a_recomposicao_e_real(self):
        """Com os dois lados nomeando, a vitrine declara a troca e a
        frase antiga esta certa: nao ha silencio para interpretar."""
        t = montar(as_quatro(ONTEM, 1), as_quatro(HOJE, 2))
        self.assertIn("passou de \"com apps de catálogo\" para "
                      "\"com uma assinatura\"", t)
        self.assertNotIn("silêncio", t)


class OEventoIgualSaiJunto(unittest.TestCase):
    def setUp(self):
        sem_declaracao(self)

    def test_as_quatro_ofertas_saem_num_bloco(self):
        t = montar(as_quatro(ONTEM, 1), as_quatro(HOJE, 0))
        self.assertEqual(t.count("a vitrine parou de nomear"), 1,
                         "o mesmo evento nao se repete por oferta")

    def test_e_o_nome_reduz_pelo_que_e_comum(self):
        """O que varia entre as ofertas e o degrau, e so ele precisa
        aparecer quatro vezes."""
        t = montar(as_quatro(ONTEM, 1), as_quatro(HOJE, 0))
        self.assertIn("Claro Flex 40, 45, 50 e Passaporte 60 GB", t)

    def test_a_mensagem_encolhe(self):
        t = montar(as_quatro(ONTEM, 1), as_quatro(HOJE, 0))
        self.assertLess(len(t.split("\n")), 14,
                        "eram 22 linhas para dizer uma coisa")

    def test_o_numero_de_uma_oferta_nao_vale_para_o_grupo(self):
        """O DEFEITO QUE EU INTRODUZI AO AGRUPAR. As quatro custam
        R$ 44,90, R$ 59,90, R$ 69,90 e R$ 119,90: imprimir "mesmo preco
        (44,90)" sob o cabecalho das quatro afirma para todas o que vale
        para uma."""
        t = montar(as_quatro(ONTEM, 1), as_quatro(HOJE, 0))
        self.assertIn("sem mexer em preço nem entrega", t)
        for preco in ("44,90", "59,90", "69,90", "119,90"):
            self.assertNotIn("mesmo preço (%s)" % preco, t)

    def test_oferta_sozinha_continua_com_os_numeros_dela(self):
        """Sem grupo nao ha numero ambiguo, e o leitor quer o numero."""
        t = montar([flex(40, 44.90, 1, ONTEM)], [flex(40, 44.90, 0, HOJE)])
        self.assertIn("mesmo preço (44,90)", t)
        self.assertNotIn("sem mexer em preço nem entrega", t)

    def test_preco_diferente_entre_ofertas_desfaz_o_grupo(self):
        """So agrupa quando nao ha numero a perder: com o preco andando,
        cada oferta volta a ter seu bloco, porque ali o numero e a
        noticia e juntar esconderia de qual oferta ele e."""
        ontem = [flex(40, 44.90, 1, ONTEM), flex(45, 59.90, 1, ONTEM)]
        hoje = [flex(40, 49.90, 0, HOJE), flex(45, 59.90, 0, HOJE)]
        t = montar(ontem, hoje)
        self.assertIn("44,90 → 49,90", t)
        self.assertEqual(t.count("a vitrine parou de nomear"), 2)


class OAgrupadorEOReducaoDeNome(unittest.TestCase):
    """As duas funcoes isoladas, para os casos que a mensagem nao mostra."""

    def _ev(self, nome, **kw):
        d = {"operadora": "Claro", "produto": "btl", "onde": "em SP",
             "antes_bundle": 1, "agora_bundle": 0, "versao_mudou": True,
             "preco_mudou": False, "entrega_mudou": False,
             "atual": {"operadora": "Claro", "nome_oferta": nome,
                       "produto": "btl"}}
        d.update(kw)
        return d

    def test_praca_diferente_nao_agrupa(self):
        g = robo._agrupar_remodeladas(
            [self._ev("A"), self._ev("B", onde="em MG")])
        self.assertEqual(len(g), 2)

    def test_transicao_diferente_nao_agrupa(self):
        g = robo._agrupar_remodeladas(
            [self._ev("A"), self._ev("B", agora_bundle=2)])
        self.assertEqual(len(g), 2)

    def test_sem_parte_comum_lista_os_nomes_inteiros(self):
        """Inventar um nome de serie seria pior que repetir."""
        nome = robo._nomes_juntos(
            [self._ev("Claro Controle"), self._ev("Flex Passaporte")])
        self.assertEqual(nome, "Claro Controle e Flex Passaporte")

    def test_nome_repetido_entra_uma_vez(self):
        nome = robo._nomes_juntos([self._ev("Claro Flex 40 GB")] * 3)
        self.assertEqual(nome, "Claro Flex 40 GB")

    def test_o_prefixo_comum_nao_corta_no_meio_da_palavra(self):
        """A mesma armadilha do outro lado do nome.

        "Claro Controle 40 GB" e "Claro Contrato 40 GB" compartilham
        "Claro Contr", que nao termina em palavra: os miolos viravam
        "ole" e "ato" e a reducao imprimia

            Claro Controle e ato 40 GB
        """
        nome = robo._nomes_juntos([self._ev("Claro Controle 40 GB"),
                                   self._ev("Claro Contrato 40 GB")])
        self.assertNotIn("Controle e ato", nome)
        self.assertIn("Controle", nome)
        self.assertIn("Contrato", nome)

    def test_o_sufixo_comum_nao_corta_no_meio_da_palavra(self):
        """O DEFEITO QUE ESTES TESTES ACHARAM, antes de ir ao ar.

        "Claro Controle" e "Claro Flex Passaporte" terminam as duas em
        "e": o sufixo comum virou "e", os miolos viraram "Control" e
        "Flex Passaport", e a reducao imprimia

            Claro Control e Flex Passaporte

        Texto remendado desse jeito chega ao Telegram sem ninguem
        perceber. O corte passou a exigir palavra inteira.
        """
        nome = robo._nomes_juntos([self._ev("Claro Controle"),
                                   self._ev("Claro Flex Passaporte")])
        self.assertNotIn("Control e", nome)
        self.assertIn("Controle", nome)
        self.assertIn("Passaporte", nome)


if __name__ == "__main__":
    unittest.main(verbosity=2)
