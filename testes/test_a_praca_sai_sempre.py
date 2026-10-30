# -*- coding: utf-8 -*-
u"""Todo evento da mensagem diz em que praca aconteceu.

A MENSAGEM DE 24/10/2026 anunciou dois reajustes da Brisanet - de -7% e
-6% - sem dizer onde:

    Brisanet - mudou de nome
      AGO26 500MB + Sky + Amazon -> [NOV] 500MB + Sky + Amazon
      e o preco foi de 109,70 para 101,80  -7%

A Brisanet vende em nove pracas do Nordeste. "-7%" pode ser em uma delas
ou nas nove, e a diferenca muda a leitura do movimento inteiro - foi na
comparacao entre pracas que apareceu o maior contraste de todo o
levantamento, TIM a R$ 89,99 em Sao Paulo contra R$ 149,99 no Rio.

O bloco das renomeadas era o UNICO dos seis sem a linha da praca, e o
evento ja trazia o campo: _assinar_alcance escreve "onde" em todos os
grupos e o PDF o imprimia.

POR QUE O TESTE NAO E POR BLOCO. Testar os seis um por um deixaria o
setimo bloco nascer sem praca - que e exatamente como este nasceu. Aqui
a varredura parte dos EVENTOS que os detectores produziram: para cada um
que a mensagem mostra, o "onde" dele tem de estar no texto. Serve para
os seis de hoje e para o que vier depois.
"""
import unittest

from _apoio import (HOJE, ONTEM, banco, dados, em_todas, montar, oferta,
                    sem_declaracao)

# Os grupos que a mensagem imprime, na ordem em que ela os monta - pelos
# nomes do dicionario que montar_mensagem DEVOLVE, que nao sao os nomes
# internos de mudancas(): "precos" sai como "mudancas_preco" e
# "composicao" como "mudancas_composicao". Escrevi este teste com os
# nomes internos primeiro e ele passou verde medindo listas inexistentes
# - d.get("precos") devolvia None e a varredura nao varria nada.
#
# Um grupo novo entra aqui e o teste passa a exigir a praca dele.
GRUPOS = ("mudancas_preco", "mudancas_composicao", "remodeladas", "grades",
          "voltaram", "renomeadas", "contratuais")

# GRUPOS QUE SAO RESSALVA, E NAO EVENTO DE MERCADO. A regra de "toda
# mudanca diz em que praca" e sobre MUDANCA: na ressalva nada se moveu na
# vitrine, e a cobertura e o ponto cego - da mesma familia - tambem nao
# carregam praca. O detalhe por praca fica no relatorio.
#
# A lista existe DECLARADA, e nao como excecao escondida no teste: o
# teste estrutural abaixo exige que todo grupo novo esteja em GRUPOS ou
# aqui, entao um grupo de EVENTO novo continua sem poder nascer sem
# praca - alguem teria de vir aqui e escrever que ele e ressalva.
RESSALVAS = ("duvidosa",)

# A mensagem corta cada grupo em tres e manda o resto para o PDF.
MOSTRADOS = 3


def nordeste(n=3):
    from coletores.pracas import PRACAS, rotulo
    todas = [rotulo(p) for p in PRACAS]
    return todas[:n]


def brisa(nome, preco, data, pracas, gb=None, mbps=500, chave=None):
    linhas = []
    for p in pracas:
        linhas.append(oferta(operadora="Brisanet", produto="fibra", nome=nome,
                             preco=preco, gb=gb, mbps=mbps, praca=p,
                             data=data, chave=chave
                             or "Brisanet|fibra|%dmbps|simples" % mbps))
    return linhas


class TodoEventoDizAPraca(unittest.TestCase):
    def setUp(self):
        sem_declaracao(self)

    def _varre(self, ontem, hoje, extras=()):
        """Para cada evento que a mensagem mostra, o "onde" dele no texto."""
        t = montar(ontem, hoje, extras=extras)
        d = dados(ontem, hoje, extras=extras)
        vistos = 0
        for grupo in GRUPOS:
            for e in (d.get(grupo) or [])[:MOSTRADOS]:
                onde = e.get("onde")
                self.assertTrue(onde, "evento de %s sem 'onde'" % grupo)
                self.assertIn(onde, t,
                              "o evento de %s nao diz a praca na mensagem"
                              % grupo)
                vistos += 1
        return vistos, t

    def test_a_renomeada_diz_a_praca(self):
        """O defeito de 24/10/2026, com a forma real: nome novo e preco
        novo na mesma oferta."""
        pracas = nordeste(3)
        vistos, t = self._varre(
            brisa("AGO26 500MB + Sky + Amazon", 109.70, ONTEM, pracas),
            brisa("[NOV] 500MB + Sky + Amazon", 101.80, HOJE, pracas))
        self.assertTrue(vistos, "o fixture tem de produzir algum evento")
        self.assertIn("mudou de nome", t)
        self.assertIn("109,70 para 101,80", t)
        self.assertIn("em todas as 3 praças", t,
                      "a praca sai junto do reajuste")

    def test_a_mudanca_de_preco_diz_a_praca(self):
        pracas = nordeste(2)
        vistos, t = self._varre(brisa("500MB", 99.90, ONTEM, pracas),
                                brisa("500MB", 109.90, HOJE, pracas))
        self.assertTrue(vistos)
        self.assertIn("99,90 → 109,90", t)

    def test_a_remodelada_diz_a_praca(self):
        pracas = nordeste(4)
        ontem = brisa("500MB", 99.90, ONTEM, pracas)
        hoje = brisa("500MB", 109.90, HOJE, pracas, mbps=700,
                     chave="Brisanet|fibra|700mbps|simples")
        vistos, t = self._varre(ontem, hoje)
        self.assertTrue(vistos)

    def test_num_dia_com_tudo_junto_nenhum_evento_fica_sem_praca(self):
        """A varredura vale pouco se o fixture produzir um evento so."""
        a, b = nordeste(2), nordeste(5)[3:]
        ontem = (brisa("500MB", 99.90, ONTEM, a)
                 + brisa("AGO26 1000MB", 149.90, ONTEM, b, mbps=1000,
                         chave="Brisanet|fibra|1000mbps|simples")
                 + em_todas(data=ONTEM))
        hoje = (brisa("500MB", 109.90, HOJE, a)
                + brisa("[NOV] 1000MB", 139.90, HOJE, b, mbps=1000,
                        chave="Brisanet|fibra|1000mbps|simples")
                + em_todas(data=HOJE))
        vistos, t = self._varre(ontem, hoje)
        self.assertGreaterEqual(vistos, 2, "o dia tem de ter dois eventos")

    def test_a_contratual_diz_a_praca(self):
        """O grupo mais novo, de 30/10/2026: a mesma oferta na vitrine e
        outro numero no contrato."""
        pracas = nordeste(6)
        ontem = [dict(l, franquia_contratual_gb=20)
                 for l in brisa("500MB", 99.90, ONTEM, pracas)]
        hoje = [dict(l, franquia_contratual_gb=15)
                for l in brisa("500MB", 99.90, HOJE, pracas)]
        vistos, t = self._varre(ontem, hoje)
        self.assertTrue(vistos, "o fixture tem de produzir algum evento")
        self.assertIn("franquia contratual foi de 20 para 15 GB", t)

    def test_a_praca_unica_sai_dita_por_extenso(self):
        """Oferta vendida numa praca so nao pode sair como "em 1 de 1",
        que soa como movimento localizado onde ele foi total."""
        vistos, t = self._varre(brisa("500MB", 99.90, ONTEM, nordeste(1)),
                                brisa("500MB", 109.90, HOJE, nordeste(1)))
        self.assertTrue(vistos)
        self.assertNotIn("em 1 de 1", t)


class OsGruposQueOTesteVarre(unittest.TestCase):
    """O teste acima so protege os grupos que ele conhece."""

    def test_a_lista_cobre_todo_grupo_de_eventos_que_mudancas_devolve(self):
        """Detector novo tem de entrar em GRUPOS junto.

        Senao a varredura passa por cima dele e o bloco novo pode nascer
        sem praca - que e exatamente como o das renomeadas nasceu.

        A primeira versao deste teste lia os nomes da DOCSTRING de
        mudancas(), e isso e esperteza inutil: ela pescava palavras da
        prosa ("ordem", "cada", "assim") e falhava por motivo errado. A
        fonte certa e o dicionario que a funcao devolve.
        """
        import robo

        # o que nao e grupo de evento: ressalva, erro ou numero
        sem_evento = {"erro", "cego", "cego_ontem", "cobertura", "leitura"}
        # mudancas() chama de "precos" e "composicao" o que
        # montar_mensagem devolve como "mudancas_preco" e
        # "mudancas_composicao"
        traduz = {"precos": "mudancas_preco",
                  "composicao": "mudancas_composicao"}

        pracas = nordeste(2)
        banco(brisa("500MB", 99.90, ONTEM, pracas)
              + brisa("500MB", 109.90, HOJE, pracas))
        r = robo.mudancas(HOJE, ONTEM)
        grupos = {traduz.get(k, k) for k, v in r.items()
                  if isinstance(v, list) and k not in sem_evento}
        self.assertTrue(grupos, "mudancas() tem de devolver algum grupo")
        self.assertEqual(grupos - set(GRUPOS) - set(RESSALVAS), set(),
                         "grupo novo: ou e evento e entra em GRUPOS, ou e "
                         "ressalva e entra em RESSALVAS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
