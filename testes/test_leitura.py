# -*- coding: utf-8 -*-
"""Separar o que o mercado fez do que a nossa leitura passou a ver.

ACHADO PELA MEDICAO, nao pela auditoria. Com o detector de oferta
remodelada funcionando, rodei a mensagem sobre os 21 dias reais. Dois
dias mostraram o problema:

  16/10  doze ofertas de Claro, Claro Flex, Vivo e Brisanet "mudaram de
         versao" no MESMO dia - no dia seguinte ao coletor de apps
         passar a exigir o tier declarado pela fonte. Operadora nao
         combina reposicionamento com a concorrente.

  13/10  a "TIM Controle Redes Sociais" passou a incluir apps em 2 das
         18 pracas em que existe, e em 14/10 desfez nas mesmas duas. A
         pagina da TIM mostra a lista de apps as vezes.

Nos dois casos o fato e real - o dado mudou - e a CAUSA nao e o mercado.
Esconder seria mentir por omissao; reportar como movimento de operadora
seria mentir por atribuicao. Entao vai para a mensagem como uma linha
sobre a leitura, e para o relatorio em tabela propria.

E PRECO NUNCA CAI NESTA REGRA. Reajuste simultaneo entre operadoras
acontece, e reajuste chega praca por praca: a escada da Claro em 13/10
alcancou 19 de 20. Quando acontece, e a noticia.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
from _apoio import (HOJE, ONTEM, dados, em_todas, montar,       # noqa: E402
                    oferta, sem_declaracao)

def versao(operadora="Vivo", produto="prepago", nome="Vivo Pré", preco=30.0,
           gb=20, variante="simples", bundle=0, data=HOJE, pracas=None):
    """A mesma oferta, numa versao da chave de continuidade."""
    from coletores.pracas import PRACAS, rotulo
    quais = pracas or [rotulo(p) for p in PRACAS]
    linhas = []
    for p in quais:
        o = oferta(operadora=operadora, produto=produto, nome=nome,
                   preco=preco, gb=gb, praca=p, data=data,
                   chave="%s|%s|%dgb|%s" % (operadora, produto, gb, variante))
        o["nivel_bundle"] = bundle
        linhas.append(o)
    return linhas


class UmaOperadoraEhNoticia(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def test_oferta_que_passou_a_incluir_assinatura(self):
        """A FRASE MUDOU EM 23/10/2026, e o motivo e medido.

        Ela dizia: passou de "sem assinatura inclusa" para "com uma
        assinatura". A segunda metade e observada - a vitrine nomeia o
        app hoje. A primeira nao: "sem assinatura inclusa" e nivel 0,
        que significa "nada nomeado", e dali nao se conclui que a
        oferta nao tinha assinatura ontem.

        E o mesmo defeito que apareceu no sentido inverso, no Claro
        Flex: a Claro reescreveu o flex.claro.com.br, a pagina deixou
        de conter "Skeelo" e "Claro Musica" em lugar nenhum, e a
        mensagem anunciou "passou para sem assinatura inclusa" em tres
        ofertas - afirmacao sobre o mercado tirada do silencio da
        vitrine. "Silencio nao e ausencia" e regra do projeto.

        Nos dois sentidos, a unica coisa observada e o que a vitrine
        DIZ.
        """
        t = montar(versao(variante="simples", bundle=0, data=ONTEM),
                   versao(variante="com_apps", bundle=2, data=HOJE))
        self.assertIn("mesmo preço (30,00) e mesma entrega (20 GB)", t)
        self.assertNotIn("pelo mesmo preço (30,00) e", t)
        self.assertIn("a vitrine passou a nomear \"com uma assinatura\", "
                      "que antes não aparecia", t)
        self.assertNotIn("passou de \"sem assinatura inclusa\"", t)
        self.assertNotIn("nossa leitura", t)

    def test_o_nome_interno_da_versao_nao_sai_na_mensagem(self):
        """"simples -> com_apps" e como o codigo guarda a variante. Codigo
        sem dicionario e ruido com cara de informacao - a mesma regra dos
        codigos SVA."""
        t = montar(versao(variante="simples", bundle=0, data=ONTEM),
                   versao(variante="com_apps", bundle=2, data=HOJE))
        self.assertNotIn("com_apps", t)
        self.assertNotIn("simples", t)


class DuasOperadorasEhLeitura(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def _dia(self, variante, bundle, data):
        return (versao(operadora="Vivo", variante=variante, bundle=bundle,
                       data=data)
                + versao(operadora="Claro", produto="controle",
                         nome="Claro Controle", preco=59.90, gb=40,
                         variante=variante, bundle=bundle, data=data))

    def test_mudanca_simultanea_vai_para_a_linha_da_leitura(self):
        t = montar(self._dia("simples", 0, ONTEM),
                   self._dia("com_apps", 2, HOJE))
        self.assertIn("nossa leitura", t)
        self.assertIn("Claro, Vivo", t)
        self.assertNotIn("mesmo preço (30,00)", t)

    def test_e_nao_conta_como_mudanca_de_mercado(self):
        r = dados(self._dia("simples", 0, ONTEM),
                  self._dia("com_apps", 2, HOJE))
        self.assertEqual(r["remodeladas"], [])
        self.assertEqual(len(r["leitura"]), 2)

    def test_preco_simultaneo_continua_sendo_noticia(self):
        """Reajuste no mesmo dia em duas operadoras acontece de verdade -
        e quando acontece, e a noticia do dia."""
        t = montar(self._dia("simples", 0, ONTEM),
                   versao(operadora="Vivo", variante="simples", bundle=0,
                          preco=35.0, gb=18, data=HOJE)
                   + versao(operadora="Claro", produto="controle",
                            nome="Claro Controle", preco=69.90, gb=36,
                            variante="simples", bundle=0, data=HOJE))
        self.assertNotIn("nossa leitura", t)
        self.assertIn("30,00 → 35,00", t)
        self.assertIn("59,90 → 69,90", t)


class PoucasPracasEhLeitura(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    def test_duas_de_vinte_nao_e_reposicionamento(self):
        from coletores.pracas import PRACAS, rotulo
        quais = [rotulo(p) for p in PRACAS]
        t = montar(versao(variante="simples", bundle=0, data=ONTEM),
                   versao(variante="com_apps", bundle=1, data=HOJE,
                          pracas=quais[:2])
                   + versao(variante="simples", bundle=0, data=HOJE,
                            pracas=quais[2:]))
        self.assertIn("nossa leitura", t)

    def test_a_vitrine_inteira_e_reposicionamento(self):
        t = montar(versao(variante="simples", bundle=0, data=ONTEM),
                   versao(variante="com_apps", bundle=1, data=HOJE))
        self.assertNotIn("nossa leitura", t)
        self.assertIn("com apps de catálogo", t)

    def test_preco_numa_praca_so_continua_sendo_noticia(self):
        """A escada da Claro em 13/10 alcancou 19 de 20 pracas, e o
        reajuste chega cidade por cidade de verdade: a regra de alcance
        vale so para mudanca de versao."""
        from coletores.pracas import PRACAS, rotulo
        quais = [rotulo(p) for p in PRACAS]
        t = montar(versao(variante="simples", bundle=0, data=ONTEM),
                   versao(variante="simples", bundle=0, preco=35.0,
                          data=HOJE, pracas=quais[:1])
                   + versao(variante="simples", bundle=0, data=HOJE,
                            pracas=quais[1:]))
        self.assertNotIn("nossa leitura", t)
        self.assertIn("30,00 → 35,00", t)


class ARessalvaVemDepoisDosEventos(unittest.TestCase):

    def setUp(self):
        sem_declaracao(self)

    """Ela nao e um evento: e uma ressalva sobre o dado, e lugar de
    ressalva e depois do que ela qualifica. Saia no meio das mudancas de
    preco - em 08/10 caiu entre duas da Claro."""

    def test_a_linha_da_leitura_fica_no_fim(self):
        t = montar(versao(operadora="Vivo", variante="simples", bundle=0,
                          data=ONTEM)
                   + versao(operadora="Claro", produto="controle",
                            nome="Claro Controle", preco=59.90, gb=40,
                            variante="simples", bundle=0, data=ONTEM)
                   + em_todas(operadora="TIM", produto="movel",
                              nome="TIM Pós", preco=100.0, data=ONTEM),
                   versao(operadora="Vivo", variante="com_apps", bundle=2,
                          data=HOJE)
                   + versao(operadora="Claro", produto="controle",
                            nome="Claro Controle", preco=59.90, gb=40,
                            variante="com_apps", bundle=2, data=HOJE)
                   + em_todas(operadora="TIM", produto="movel",
                              nome="TIM Pós", preco=120.0, data=HOJE))
        self.assertLess(t.index("100,00 → 120,00"), t.index("nossa leitura"))

    def test_concordancia_no_singular(self):
        from coletores.pracas import PRACAS, rotulo
        quais = [rotulo(p) for p in PRACAS]
        t = montar(versao(variante="simples", bundle=0, data=ONTEM),
                   versao(variante="com_apps", bundle=1, data=HOJE,
                          pracas=quais[:2])
                   + versao(variante="simples", bundle=0, data=HOJE,
                            pracas=quais[2:]))
        self.assertIn("1 oferta mudou de versão", t)
        self.assertNotIn("1 oferta mudaram", t)


class ACausaPodeSerDeclarada(unittest.TestCase):
    """As duas heuristicas erram justamente no caso mais comum de mexida
    nossa: um coletor que passa a ler melhor e muda uma operadora
    INTEIRA, em todas as pracas, de um dia para o outro. E o que
    aconteceu em 21/10/2026, quando o nivel de bundle passou a sair da
    lista de apps da oferta em vez de so do texto do card.

    Entao a causa pode ser declarada em LEITURA_MUDOU_EM, e a declaracao
    vence as heuristicas - e o unico caso em que o codigo sabe a
    resposta em vez de estimar."""

    def test_na_data_declarada_a_mudanca_e_nossa(self):
        """O que importa e a mensagem EXPLICAR, e nao qual linha explica.

        O motivo sai na linha da cobertura quando ela fala, e na linha
        da leitura quando nao - duas linhas repetindo a mesma explicacao
        seria pior. O teste media a frase e nao o fato, e quebrou quando
        a cobertura passou a dar o motivo.
        """
        t = montar(versao(variante="simples", bundle=0, data=ONTEM),
                   versao(variante="com_apps", bundle=2, data=HOJE))
        self.assertIn("nível de bundle", t, "o motivo tem de estar escrito")
        self.assertIn("mudança de leitura" if "mudança de leitura" in t
                      else "a leitura mudou hoje", t)

    def test_e_a_mensagem_diz_qual_foi(self):
        """"isso costuma ser mudanca na nossa leitura" e o que sobra sem
        declaracao. Com ela, da para dizer o que mudou."""
        t = montar(versao(variante="simples", bundle=0, data=ONTEM),
                   versao(variante="com_apps", bundle=2, data=HOJE))
        self.assertNotIn("costuma ser", t)

    def test_fora_da_data_declarada_vale_a_heuristica(self):
        sem_declaracao(self)
        t = montar(versao(variante="simples", bundle=0, data=ONTEM),
                   versao(variante="com_apps", bundle=2, data=HOJE))
        self.assertNotIn("a leitura mudou hoje", t)

    def test_preco_na_data_declarada_continua_sendo_noticia(self):
        """Declarar que a leitura mudou nao cega o comparador de preco:
        a declaracao vale para mudanca de VERSAO, e so."""
        t = montar(versao(variante="simples", bundle=0, data=ONTEM),
                   versao(variante="simples", bundle=0, preco=35.0,
                          data=HOJE))
        self.assertIn("30,00 → 35,00", t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
