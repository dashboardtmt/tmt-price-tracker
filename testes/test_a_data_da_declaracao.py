# -*- coding: utf-8 -*-
u"""A data declarada e a da primeira COLETA afetada, nao a do commit.

O DEFEITO QUE ESTE ARQUIVO FECHA. A coleta roda de madrugada; commit que
entra depois dela so chega ao dado no dia seguinte. Em 21/10/2026 o
commit ac93d2d entrou as 10:54 - depois da coleta daquele dia - e fez a
janela de degustacao parar de engolir o ultimo app citado no card. A
data declarada em LEITURA_MUDOU_EM foi 21/10, que era a data do commit
anterior; a leitura nova so apareceu no dado de 22/10.

Resultado, medido em 04/11/2026 nos 35 dias publicados: a mensagem de
22/10 saiu com "3 mudancas hoje / Combo - Vivo Total V 1, 2 e 10 Giga /
sem mexer em preco nem entrega / e a vitrine passou a listar "Max" e
"Telecine" / em todas as 20 pracas". Tres eventos atribuidos a vitrine
da Vivo, com preco e entrega parados, num dia em que a Vivo nao mexeu em
nada - o que mudou foi a nossa leitura.

E ERRAR A DATA E PIOR DO QUE NAO DECLARAR. A declaracao vence as duas
heuristicas: ela afirma com certeza. Na data errada, ela afirma com
certeza sobre o dia errado, e marca como nosso um dia em que a operadora
pode ter mexido de verdade.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
from _apoio import banco, oferta, sem_declaracao              # noqa: E402

HOJE, ONTEM = "2026-10-22", "2026-10-21"

# As tres ofertas do caso real: mesmo preco, mesma entrega, a lista de
# apps indo de um para dois. A chave carrega a lista, entao a identidade
# troca de versao e o detector ve "remodelada so de versao".
TRES = (("Vivo Total V 1 Giga", 1200.0, 1000),
        ("Vivo Total V 2 Giga", 1500.0, 2000),
        ("Vivo Total V 10 Giga", 3000.0, 10000))


def dia(data, apps, variante):
    return [oferta(operadora="Vivo", produto="combo", nome=nome, preco=preco,
                   gb=None, mbps=mbps, data=data, apps=list(apps),
                   chave="Vivo|combo|%dmbps|%s" % (mbps, variante))
            for nome, preco, mbps in TRES]


ANTES = dia(ONTEM, ("max",), "com_max")
DEPOIS = dia(HOJE, ("max", "telecine"), "com_max_telecine")


class ADataEADaPrimeiraColeta(unittest.TestCase):

    def test_o_dia_do_commit_e_o_dia_do_efeito_sao_dois_dias(self):
        """O par 21/22 de outubro e o caso de teste da regra.

        Se algum dia alguem juntar as duas numa linha so, este teste cai
        - e a juncao e exatamente o defeito: um commit de 20/10 e um de
        21/10 produzem efeito em dias diferentes.
        """
        self.assertIn("2026-10-21", robo.LEITURA_MUDOU_EM)
        self.assertIn("2026-10-22", robo.LEITURA_MUDOU_EM)
        self.assertNotEqual(robo.LEITURA_MUDOU_EM["2026-10-21"],
                            robo.LEITURA_MUDOU_EM["2026-10-22"])

    def test_a_entrada_de_22_10_nomeia_o_que_mudou(self):
        """Data sem causa escrita nao serve: o leitor da serie precisa
        saber o que mudou, e nao so que algo mudou."""
        t = robo.LEITURA_MUDOU_EM["2026-10-22"]
        self.assertIn("Max", t)
        self.assertIn("Telecine", t)
        self.assertIn("degusta", t)

    def test_com_a_declaracao_o_evento_sai_do_balde_do_mercado(self):
        banco(ANTES + DEPOIS)
        m = robo.mudancas(HOJE, ONTEM)
        self.assertEqual(len(m["remodeladas"]), 0,
                         "nenhum dos tres e movimento da Vivo")
        self.assertEqual(len(m["leitura"]), 3)

    def test_sem_a_declaracao_o_mesmo_dia_vira_noticia_de_mercado(self):
        """A prova de que a linha declarada e o que muda a atribuicao.

        Uma operadora so, em todas as pracas em que a oferta existe: e
        o caso em que as duas heuristicas erram, e por isso a data
        existe.
        """
        sem_declaracao(self)
        banco(ANTES + DEPOIS)
        m = robo.mudancas(HOJE, ONTEM)
        self.assertEqual(len(m["remodeladas"]), 3)
        self.assertEqual(len(m["leitura"]), 0)

    def test_a_mensagem_do_dia_declarado_diz_a_causa(self):
        banco(ANTES + DEPOIS)
        texto, _ = robo.montar_mensagem(HOJE, ONTEM)
        self.assertIn("a leitura mudou hoje", texto)
        self.assertIn("Telecine", texto)
        # e nao conta como mudanca de mercado
        self.assertNotIn("3 mudan", texto)

    def test_preco_no_dia_declarado_continua_sendo_noticia(self):
        """A declaracao vale para mudanca de VERSAO, e so. Se ela cegasse
        o preco, um reajuste de verdade no dia de uma mexida nossa
        desapareceria."""
        banco(ANTES + dia(HOJE, ("max",), "com_max")[:1]
              + [oferta(operadora="Vivo", produto="combo",
                        nome="Vivo Total V 2 Giga", preco=1650.0, gb=None,
                        mbps=2000, data=HOJE, apps=["max"],
                        chave="Vivo|combo|2000mbps|com_max")])
        m = robo.mudancas(HOJE, ONTEM)
        self.assertEqual(len(m["precos"]), 1)

    def test_a_regra_esta_escrita_onde_quem_declara_vai_ler(self):
        """O defeito nasceu da regra escrita como "quem mexer poe a data
        aqui" - que convida a por a data do commit. A frase corrigida
        mora ao lado do dicionario, e nao num arquivo de notas."""
        caminho = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "robo.py")
        with open(caminho, encoding="utf-8") as f:
            fonte = f.read()
        inicio = fonte.index("LEITURA_MUDOU_EM = {")
        regra = fonte[max(0, inicio - 2600):inicio]
        self.assertIn("PRIMEIRA COLETA AFETADA", regra)
        self.assertIn("ac93d2d", regra)


DIA_BRISA, VESPERA = "2026-10-19", "2026-10-18"


def brisa(data, mbps, chave, lista=None):
    """A Brisanet de 19/10: mesmo preco, velocidade que aparece do nada."""
    return [oferta(operadora="Brisanet", produto="combo",
                   nome="500MB + HBO PCA", preco=114.80, gb=None, mbps=mbps,
                   praca=p, data=data, apps=lista, chave=chave)
            for p in ("Fortaleza/CE", "Recife/PE", "Natal/RN")]


class OCampoQueALeituraPassouALer(unittest.TestCase):
    """A SEGUNDA METADE DO MESMO DEFEITO, medida em 19/10/2026.

    Declarar a data nao bastava: _separar_o_que_e_nosso so olhava evento
    "so de versao", e este nao e - a entrega foi de nao lida para 500
    Mbps. Chamar isso de parado era o defeito N14, que esta certo; o que
    faltava era a declaracao alcancar o campo que a nossa leitura
    ganhou.

    E A FRASE TEM DE MUDAR COM ELE: "sem mexer em preco nem entrega" e
    falso sobre a oferta cuja entrega passou a ser lida. Trocar a
    atribuicao errada por uma afirmacao errada nao e conserto.
    """

    def montar_dia(self):
        banco(brisa(VESPERA, None, "Brisanet|combo|0gb|com_apps")
              + brisa(DIA_BRISA, 500, "Brisanet|combo|500mbps|com_max",
                      ["max"]))

    def test_com_a_data_declarada_o_campo_novo_e_nosso(self):
        self.montar_dia()
        m = robo.mudancas(DIA_BRISA, VESPERA)
        self.assertEqual(len(m["remodeladas"]), 0,
                         "a Brisanet nao mexeu em nada naquele dia")
        self.assertEqual(len(m["leitura"]), 1)

    def test_sem_a_data_declarada_continua_no_balde_do_mercado(self):
        """Sem declaracao a causa e desconhecida: pode ser a vitrine
        comecando a publicar a velocidade, e chutar seria inventar."""
        sem_declaracao(self)
        self.montar_dia()
        m = robo.mudancas(DIA_BRISA, VESPERA)
        self.assertEqual(len(m["remodeladas"]), 1)
        self.assertEqual(len(m["leitura"]), 0)

    def test_a_ressalva_nao_afirma_que_a_entrega_ficou_parada(self):
        self.montar_dia()
        texto, _ = robo.montar_mensagem(DIA_BRISA, VESPERA)
        self.assertIn("passou a ter campo lido que antes não era", texto)
        self.assertNotIn("sem mexer em preço nem entrega", texto)
        self.assertIn("a leitura mudou hoje", texto)

    def test_a_frase_da_entrega_diz_que_ela_passou_a_ser_lida(self):
        """"entrega nao lida" era verdade pela metade errada.

        A frase tinha dois estados e o campo tem tres: nao lida nos dois
        dias, passou a ser lida, deixou de ser lida. Com dois, a tabela
        do relatorio escrevia "entrega nao lida" ao lado de um evento
        que o texto chamava de mudanca - e hoje ela FOI lida.
        """
        self.montar_dia()
        m = robo.mudancas(DIA_BRISA, VESPERA)
        e = m["leitura"][0]
        self.assertIn("passou a ser lida", e["texto_entrega"])
        self.assertIn("500", e["texto_entrega"])
        self.assertNotIn("não lida", e["texto_entrega"])

    def test_e_quando_nao_foi_lida_nos_dois_dias_a_frase_nao_muda(self):
        """O estado antigo continua: nada se moveu, e e o caso da
        Brisanet que o defeito V6 desenhou."""
        banco([oferta(operadora="Brisanet", produto="combo",
                      nome="500MB + HBO PCA", preco=114.80, gb=None,
                      mbps=None, praca=p, data=d,
                      chave="Brisanet|combo|0gb|com_apps"
                            if d == VESPERA else
                            "Brisanet|combo|0gb|com_max",
                      apps=None if d == VESPERA else ["max"])
               for d in (VESPERA, DIA_BRISA)
               for p in ("Fortaleza/CE", "Recife/PE", "Natal/RN")])
        m = robo.mudancas(DIA_BRISA, VESPERA)
        e = (m["leitura"] + m["remodeladas"])[0]
        self.assertEqual(e["texto_entrega"], "entrega não lida")

    def test_o_preco_nao_lido_nao_entra_nesta_regra(self):
        """Preco nao lido num dos dias deixa aberta a possibilidade de
        reajuste que nao vimos: leitura nova POR CIMA de um buraco
        continua no balde do mercado, onde o leitor confere."""
        banco([oferta(operadora="Brisanet", produto="combo",
                      nome="500MB + HBO PCA", preco=None, gb=None, mbps=None,
                      praca=p, data=VESPERA,
                      chave="Brisanet|combo|0gb|com_apps")
               for p in ("Fortaleza/CE", "Recife/PE", "Natal/RN")]
              + brisa(DIA_BRISA, 500, "Brisanet|combo|500mbps|com_max",
                      ["max"]))
        m = robo.mudancas(DIA_BRISA, VESPERA)
        self.assertEqual(len(m["leitura"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
