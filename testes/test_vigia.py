# -*- coding: utf-8 -*-
"""O vigia tem de achar o que as varreduras acharam na mao.

Cada teste aqui reproduz um achado real do mes, com o numero real. Se o
vigia nao pegar isso, ele nao serve para nada - e nesse caso e melhor
nao existir do que dar falsa sensacao de cobertura.

E os testes de silencio importam tanto quanto: vigia que grita todo dia
vira ruido, e depois ninguem le nem quando ele acerta.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vigia                                                  # noqa: E402


def oferta(operadora="Vivo", produto="movel", nome="Vivo Pós", preco=150.0,
           gb=60, mbps=None, praca="Sao Paulo/SP", chave=None):
    return {"operadora": operadora, "produto": produto, "praca": praca,
            "nome_oferta": nome, "preco_promocional": preco,
            "franquia_anunciada_gb": gb, "degrau_mbps": mbps,
            "chave": chave or "%s|%s|x|simples" % (operadora, produto)}


def dia_normal(n=30, operadora="Vivo"):
    return [oferta(operadora=operadora, nome="Oferta %d" % i,
                   preco=100.0 + i, chave="%s|movel|%d|s" % (operadora, i))
            for i in range(n)]


def historico(dias=5, n=30, operadora="Vivo"):
    return {"2026-10-%02d" % (10 + i): dia_normal(n, operadora)
            for i in range(dias)}


def graves(lista):
    return [t for g, t in lista if g == "grave"]


def atencoes(lista):
    return [t for g, t in lista if g == "atencao"]


class PrecoFantasma(unittest.TestCase):
    """07/10: tres cards de Claro Controle gravados a R$ 24,60, que e o
    preco avulso do Disney+ citado no proprio card."""

    def test_o_preco_do_disney_virando_preco_do_plano(self):
        """R$ 24,60 nao e um preco impossivel - a Vivo Pre custa R$ 20.

        O que denunciava aquele valor era ser -75% do que a MESMA oferta
        custava no dia anterior. Limite fixo nunca pegaria; o detector
        de salto pega.

        E TEM DE SER GRAVE, nao atencao: atencao fica no relatorio, e um
        preco que nao e preco de plano precisa chegar a mensagem - foi
        o defeito que gerou este modulo, e ele passaria em silencio no
        canal onde alguem olha.
        """
        hist = historico()
        hoje = dia_normal()
        # a oferta que no historico custa R$ 100 aparece a R$ 24,60
        hoje[0]["preco_promocional"] = 24.60
        r = vigia.achados(hoje, hist)
        self.assertTrue(any("salto" in t for t in graves(r)), r)
        self.assertIn("salto", vigia.resumo(r))

    def test_preco_impossivel_de_verdade_e_grave(self):
        hoje = dia_normal() + [oferta(nome="Lixo", preco=0.99,
                                      chave="Vivo|movel|zz|s")]
        r = vigia.achados(hoje, historico())
        self.assertTrue(any("fora da faixa" in t for t in graves(r)))

    def test_preco_absurdo_para_cima_tambem(self):
        hoje = dia_normal() + [oferta(nome="Aparelho", preco=12999.0)]
        self.assertTrue(any("fora da faixa" in t for t in graves(vigia.achados(hoje, historico()))))

    def test_preco_normal_nao_e_denunciado(self):
        r = vigia.achados(dia_normal(), historico())
        self.assertEqual([t for t in graves(r) if "faixa" in t], [])


class EntregaSumida(unittest.TestCase):
    """119 linhas por dia da Brisanet sem velocidade: a API manda numero
    puro e a leitura exigia unidade."""

    def test_operadora_inteira_sem_entrega_e_grave(self):
        hoje = dia_normal() + [
            oferta(operadora="Brisanet", produto="fibra", nome="F%d" % i,
                   gb=None, mbps=None, chave="Brisanet|fibra|%d|s" % i)
            for i in range(12)]
        r = vigia.achados(hoje, historico())
        self.assertTrue(any("sem velocidade nem franquia" in t for t in graves(r)))

    def test_uma_ou_outra_sem_entrega_nao_alarma(self):
        hoje = dia_normal() + [oferta(nome="Avulsa", gb=None, mbps=None,
                                      chave="Vivo|movel|zz|s")]
        self.assertEqual([t for t in graves(vigia.achados(hoje, historico()))
                          if "sem velocidade" in t], [])


class OfertasIndistinguiveis(unittest.TestCase):
    """As duas "Vivo Familia 2 + TV" com a mesma chave, praca e nome:
    20 por dia que o comparador nunca viu."""

    def test_par_colidido_e_denunciado(self):
        a = oferta(nome="Vivo Família 2 + TV", preco=290.0, chave="Vivo|combo|700|familia")
        b = oferta(nome="Vivo Família 2 + TV", preco=390.0, chave="Vivo|combo|700|familia")
        r = vigia.achados(dia_normal() + [a, b], historico())
        self.assertTrue(any("indistinguiveis" in t for t in atencoes(r)))

    def test_dia_limpo_nao_denuncia(self):
        self.assertEqual([t for t in atencoes(vigia.achados(dia_normal(), historico()))
                          if "indistinguiveis" in t], [])


class VolumeDeOfertas(unittest.TestCase):
    """Operadora que some ou encolhe e coleta quebrada, nao mercado."""

    def test_operadora_que_sumiu_e_grave(self):
        hist = historico(operadora="Claro")
        r = vigia.achados(dia_normal(operadora="Vivo"), hist)
        self.assertTrue(any("Claro nao aparece hoje" in t for t in graves(r)))

    def test_queda_grande_e_atencao(self):
        r = vigia.achados(dia_normal(n=10), historico(n=30))
        self.assertTrue(any("contra 30 tipicos" in t for t in atencoes(r)))

    def test_variacao_pequena_nao_alarma(self):
        # vitrine muda; cair de 30 para 27 e vida normal
        r = vigia.achados(dia_normal(n=27), historico(n=30))
        self.assertEqual([t for t in atencoes(r) if "tipicos" in t], [])

    def test_crescer_nao_e_problema(self):
        r = vigia.achados(dia_normal(n=45), historico(n=30))
        self.assertEqual([t for t in atencoes(r) if "tipicos" in t], [])


class SaltoDePreco(unittest.TestCase):

    def test_preco_que_dobra_e_grave(self):
        hist = historico()
        hoje = dia_normal()
        hoje[0]["preco_promocional"] = 100.0 * 2
        r = vigia.achados(hoje, hist)
        self.assertTrue(any("salto" in t for t in graves(r)), r)

    def test_salto_de_reajuste_fica_no_relatorio(self):
        """+60% e muito, mas e um numero que operadora pratica - e o
        comparador ja reporta isso com nome e praca. Virar manchete
        todo mes gastaria a credibilidade da linha "Conferir"."""
        hoje = dia_normal()
        hoje[0]["preco_promocional"] = 160.0
        r = vigia.achados(hoje, historico())
        self.assertTrue(any("salto" in t for t in atencoes(r)), r)
        self.assertEqual([t for t in graves(r) if "salto" in t], [])

    def test_reajuste_pequeno_nao_vira_ruido(self):
        hoje = dia_normal()
        hoje[0]["preco_promocional"] = 110.0
        self.assertEqual([t for t in atencoes(vigia.achados(hoje, historico()))
                          if "salto" in t], [])


class DiaSemDado(unittest.TestCase):

    def test_sem_captura_nenhuma_e_grave(self):
        r = vigia.achados([], historico())
        self.assertEqual(graves(r), ["nenhuma captura hoje"])


class Silencio(unittest.TestCase):
    """Vigia que grita todo dia vira ruido."""

    def test_dia_normal_nao_produz_nada(self):
        self.assertEqual(vigia.achados(dia_normal(), historico()), [])

    def test_a_vaga_da_mensagem_vai_para_o_mais_grave(self):
        """RESSALVA 5 DO VEREDITO. A mensagem tem uma vaga, e qual achado
        a ocupava vinha da ordem em que "achados" os produz - ordem de
        codigo e nada mais. Por 18 dos 21 dias medidos o primeiro era a
        Brisanet sem velocidade, defeito de leitura ja corrigido que se
        repetia todo dia, e um achado novo entrava atras dele. Segundo
        plano e a posicao de onde o preco fantasma ja ficou calado."""
        r = vigia.resumo([
            ("grave", "Brisanet: 119 de 119 ofertas sem velocidade"),
            ("grave", "3 oferta(s) com preco fora da faixa de varejo"),
            ("grave", "Claro nao aparece hoje (tipico: 364 ofertas)")])
        self.assertTrue(r.startswith("Conferir: Claro nao aparece hoje"), r)
        self.assertIn("mais 2 ponto(s)", r)

    def test_e_a_ordem_nao_depende_de_como_chegou(self):
        baralhado = [
            ("grave", "nenhuma captura hoje"),
            ("grave", "Brisanet: 119 de 119 ofertas sem velocidade")]
        for ordem in (baralhado, list(reversed(baralhado))):
            self.assertTrue(vigia.resumo(ordem).startswith(
                "Conferir: nenhuma captura hoje"), ordem)

    def test_resumo_vazio_quando_nao_ha_grave(self):
        self.assertEqual(vigia.resumo([("atencao", "algo pequeno")]), "")
        self.assertIn("Conferir", vigia.resumo([("grave", "algo serio")]))


def captura(dia, operadora="Vivo", produto="movel", nome="Oferta A",
            praca="Sao Paulo/SP", contratual=10, anunciada=50, mbps=None):
    return {"data_captura": dia, "operadora": operadora, "produto": produto,
            "praca": praca, "nome_oferta": nome, "preco_promocional": 100.0,
            "franquia_anunciada_gb": anunciada, "degrau_mbps": mbps,
            "franquia_contratual_gb": contratual,
            "chave": "%s|%s|%s" % (operadora, produto, nome)}


def serie(tamanhos, **kw):
    u"""{dia: capturas} com um numero de ofertas por dia.

    tamanhos[i] e quantas ofertas o balde tem no dia i. O ultimo dia e
    devolvido a parte, como "hoje".
    """
    dias = {}
    for i, n in enumerate(tamanhos):
        dia = "2026-10-%02d" % (10 + i)
        dias[dia] = [captura(dia, nome="Oferta %d" % j, **kw) for j in range(n)]
    ultimo = sorted(dias)[-1]
    return dias.pop(ultimo), dias


class OSilencioQueDuraTresDias(unittest.TestCase):
    u"""OS DOIS ACHADOS QUE NAO OLHAM SO O DIA.

    O resto do vigia pergunta "o que coletei hoje faz sentido?". Estes
    dois perguntam "o que parou de aparecer, e ja faz dias?" - e por
    isso sao os unicos que podem errar de tres jeitos novos: falar cedo
    demais, repetir todo dia enquanto dura, e falar por oscilacao.

    Os numeros aqui sao os dois casos reais que deram origem a eles: a
    fibra da TIM com 1 oferta de 10 por 35 dias, e a franquia garantida
    das Vivo Familia nula por 31 dias.
    """

    # ----------------------------------------------- prateleira

    def test_prateleira_encolhida_fala_no_terceiro_dia(self):
        hoje, antes = serie([10, 10, 10, 10, 10, 3, 3, 3])
        achou = [t for t in graves(vigia.achados(hoje, antes))
                 if "encolheu para" in t]
        self.assertEqual(len(achou), 1, vigia.achados(hoje, antes))
        self.assertIn("3 ofertas", achou[0])
        self.assertIn("vinha de 10", achou[0])

    def test_no_segundo_dia_ainda_nao_fala(self):
        u"""Falar no primeiro dia renderia 35 avisos em 41 dias, e 7 das
        17 mortes de campo medidas duravam um dia so - susto, nao
        defeito."""
        hoje, antes = serie([10, 10, 10, 10, 10, 10, 3, 3])
        self.assertEqual([t for t in graves(vigia.achados(hoje, antes))
                          if "encolheu para" in t], [])

    def test_no_quarto_dia_nao_repete(self):
        u"""Fala UMA vez. Repetir enquanto durasse poria a Brisanet
        quatro dias seguidos dizendo a mesma coisa."""
        hoje, antes = serie([10, 10, 10, 10, 3, 3, 3, 3])
        self.assertEqual([t for t in graves(vigia.achados(hoje, antes))
                          if "encolheu para" in t], [])

    def test_oscilacao_pequena_nao_fala(self):
        hoje, antes = serie([10, 10, 10, 10, 10, 8, 8, 8])
        self.assertEqual([t for t in graves(vigia.achados(hoje, antes))
                          if "encolheu para" in t], [])

    def test_balde_minusculo_nao_rende_noticia(self):
        u"""A NuCel tem 3 ofertas e a Claro tem 364. Sair de 2 para 1 e
        metade, e nao e noticia - por isso o piso."""
        hoje, antes = serie([2, 2, 2, 2, 2, 1, 1, 1])
        self.assertEqual([t for t in graves(vigia.achados(hoje, antes))
                          if "encolheu para" in t], [])

    # ----------------------------------------------- campo que morre

    def _com_contratual(self, valores, nomes=("Oferta A",)):
        u"""valores[i] e a garantida de cada dia; None e campo morto."""
        dias = {}
        for i, v in enumerate(valores):
            dia = "2026-10-%02d" % (10 + i)
            dias[dia] = [captura(dia, nome=n, contratual=v) for n in nomes]
        ultimo = sorted(dias)[-1]
        return dias.pop(ultimo), dias

    def test_campo_morto_tres_dias_fala(self):
        hoje, antes = self._com_contratual([10, 10, 10, 10, 10, None, None, None])
        achou = [t for t in graves(vigia.achados(hoje, antes))
                 if "não é lida há" in t]
        self.assertEqual(len(achou), 1, vigia.achados(hoje, antes))
        self.assertIn("franquia garantida", achou[0])

    def test_campo_morto_um_dia_nao_fala(self):
        hoje, antes = self._com_contratual([10, 10, 10, 10, 10, 10, None, 10])
        self.assertEqual([t for t in graves(vigia.achados(hoje, antes))
                          if "não é lida há" in t], [])

    def test_campo_que_nunca_foi_lido_nao_morre(self):
        u"""Campo que ja vinha falhando metade do tempo nao morreu:
        sempre foi assim, e isso e outro assunto."""
        hoje, antes = self._com_contratual([None, None, None, None, None,
                                            None, None, None])
        self.assertEqual([t for t in graves(vigia.achados(hoje, antes))
                          if "não é lida há" in t], [])

    def test_a_morte_de_uma_familia_nao_se_esconde_atras_das_irmas(self):
        u"""O GRAO E A OFERTA, E ESTE TESTE E O PORQUE.

        No grao da operadora+produto a garantida das Vivo Familia nunca
        chegaria a zero: as outras ofertas do mesmo produto seguem
        preenchidas e a taxa pararia em 60%. Medido no dado publicado -
        no grao errado este vigia acha 6 casos e perde justamente os 31
        dias que o fizeram existir.
        """
        irmas = ["Vivo Pós com Netflix", "Vivo Pós com Disney+", "Vivo Pós"]
        familia = ["Vivo Família 2", "Vivo Família 3"]
        dias = {}
        for i in range(8):
            dia = "2026-10-%02d" % (10 + i)
            morreu = i >= 5
            dias[dia] = ([captura(dia, nome=n, contratual=10) for n in irmas]
                         + [captura(dia, nome=n,
                                    contratual=None if morreu else 120)
                            for n in familia])
        ultimo = sorted(dias)[-1]
        hoje = dias.pop(ultimo)
        achou = [t for t in graves(vigia.achados(hoje, dias))
                 if "não é lida há" in t]
        self.assertEqual(len(achou), 1, vigia.achados(hoje, dias))
        self.assertIn("Vivo Família", achou[0])


class OsDoisVigiasDisputamAVaga(unittest.TestCase):
    u"""A FRASE E A MARCA DE PRIORIDADE MORAM EM LUGARES DIFERENTES.

    A mensagem tem uma vaga so: o primeiro grave sai inteiro, escolhido
    por PRIORIDADE, e os outros viram contagem. PRIORIDADE casa por
    TRECHO DE TEXTO - entao trocar "nao e lida" por "não é lida", que e
    exatamente o que eu fiz ao acertar o acento, faz o achado perder a
    vaga e nunca mais aparecer na mensagem, sem quebrar teste nenhum e
    sem deixar marca em lugar algum.

    Aconteceu na bancada: o meu proprio replay dos 41 dias passou a
    contar 3 frases onde havia 8, pelo mesmo motivo.
    """

    def _frase_do_campo(self):
        dias = {}
        for i in range(8):
            dia = "2026-10-%02d" % (10 + i)
            dias[dia] = [captura(dia, contratual=None if i >= 5 else 10)]
        ultimo = sorted(dias)[-1]
        return vigia.achados(dias.pop(ultimo), dias)

    def _frase_da_prateleira(self):
        hoje, antes = serie([10, 10, 10, 10, 10, 3, 3, 3])
        return vigia.achados(hoje, antes)

    def test_a_marca_do_campo_esta_na_frase(self):
        textos = graves(self._frase_do_campo())
        self.assertTrue(any("não é lida há" in t for t in textos), textos)
        self.assertIn("não é lida há", vigia.PRIORIDADE)

    def test_a_marca_da_prateleira_esta_na_frase(self):
        textos = graves(self._frase_da_prateleira())
        self.assertTrue(any("encolheu para" in t for t in textos), textos)
        self.assertIn("encolheu para", vigia.PRIORIDADE)

    def test_as_duas_chegam_a_mensagem(self):
        u"""Nao basta o achado existir: ele tem de GANHAR a vaga, senao
        fica no PDF e o dado segue sumindo sem ninguem ver."""
        for saida in (self._frase_do_campo(), self._frase_da_prateleira()):
            linha = vigia.resumo(saida)
            self.assertTrue(
                "não é lida há" in linha or "encolheu para" in linha,
                "o achado novo nao chegou a mensagem: %r" % linha)


if __name__ == "__main__":
    unittest.main(verbosity=2)
