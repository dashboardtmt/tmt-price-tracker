# -*- coding: utf-8 -*-
u"""PICO DE UM DIA NAO E DUAS NOTICIAS.

A franquia contratual do TIM Controle Smart foi de 5 para 15 GB em 10
das 20 cidades em 30/10/2026, e de 15 para 5 nas mesmas 10 em 31/10. A
mensagem publicou "+200%" num dia e "-67%" no outro, sobre uma piscada
de 24 horas - dois reposicionamentos anunciados onde nao houve nenhum.

MEDIDO NOS 35 DIAS PUBLICADOS, campo por campo, antes de escrever:

    franquia contratual   13 casos em 2 dias
    nivel de bundle        2 casos em 1 dia
    preco                  0
    franquia anunciada     0
    degrau em Mbps         0
    lista de apps          0

Por isso a marca existe so para a contratual: guarda para preco seria
salvaguarda morta, e este projeto trata salvaguarda morta como defeito.

E A PRIMEIRA MEDICAO ACHOU 20 REVERSOES DE PRECO QUE NAO EXISTEM. Ela
identificava a oferta por operadora+produto+praca+nome, e quatro planos
"Vivo Pre" dividem o nome com contratos e precos diferentes: a resposta
dependia da ordem em que o banco devolvesse as linhas. E por isso que
_contratual_de_anteontem devolve CONJUNTO e nao afirma nada quando ha
mais de um valor.
"""
import datetime
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))

import robo                                                   # noqa: E402
from _apoio import HOJE, ONTEM, dados, montar, oferta         # noqa: E402

try:
    import relatorio
except Exception:                                             # pragma: no cover
    relatorio = None

ANTEONTEM = (datetime.date.fromisoformat(ONTEM)
             - datetime.timedelta(days=1)).isoformat()


def tim(contratual, data, pracas=None, nome="TIM Controle Smart",
        preco=58.99, gb=45):
    """A oferta do caso real: a vitrine parada, o contrato mexendo."""
    from coletores.pracas import PRACAS, rotulo
    onde = pracas or [rotulo(p) for p in PRACAS][:3]
    return [oferta(operadora="TIM", produto="controle", nome=nome,
                   preco=preco, gb=gb, praca=p, data=data,
                   contratual=contratual,
                   chave="TIM|controle|%dgb|simples" % gb)
            for p in onde]


class AReversaoEmVinteQuatroHoras(unittest.TestCase):

    def test_o_desfazer_sai_como_desfazer(self):
        """31/10/2026: a contratual volta aos 5 GB que tinha em 29/10. O
        fato nao e um movimento novo - e o desfazer do de ontem."""
        t = montar(tim(15, ONTEM), tim(5, HOJE), extras=tim(5, ANTEONTEM))
        self.assertIn("a franquia contratual voltou aos 5 GB em 24 horas", t)
        self.assertNotIn("-67%", t)
        self.assertNotIn("de 15 para 5", t)

    def test_o_primeiro_movimento_segue_com_o_percentual(self):
        """30/10/2026: a ida nao e reversao, e o percentual e a noticia.
        Sem este contraste, a marca comeria o movimento de verdade."""
        t = montar(tim(5, ONTEM), tim(15, HOJE), extras=tim(5, ANTEONTEM))
        self.assertIn("a franquia contratual foi de 5 para 15 GB (+200%)", t)
        self.assertNotIn("voltou", t)

    def test_sem_anteontem_nao_se_afirma_reversao(self):
        """No comeco da serie nao ha com que comparar, e "voltou" seria
        afirmacao sobre dia que ninguem olhou."""
        t = montar(tim(15, ONTEM), tim(5, HOJE))
        self.assertIn("a franquia contratual foi de 15 para 5 GB", t)
        self.assertNotIn("voltou", t)

    def test_tres_dias_seguidos_de_movimento_nao_sao_reversao(self):
        """5 -> 15 -> 20 e escalada, e nao piscada."""
        t = montar(tim(15, ONTEM), tim(20, HOJE), extras=tim(5, ANTEONTEM))
        self.assertIn("de 15 para 20 GB", t)
        self.assertNotIn("voltou", t)


class MetadeDesfazEMetadeMexePelaPrimeiraVez(unittest.TestCase):
    """O mesmo 15 -> 5 pode ser reversao numa praca e movimento noutra.

    NAO ACONTECEU NOS 35 DIAS PUBLICADOS, e o teste existe assim mesmo:
    a regua deste projeto e a garantia, e nao a frequencia. Sem a
    reversao no ident, as duas pracas caem num evento so e a frase de
    uma delas e afirmada para as duas - o mesmo defeito que a auditoria
    chama de "eleger um representante do grupo e publicar o numero dele
    como fato", e que ja custou a chave e os dois precos neste mesmo
    detector.
    """

    def test_as_duas_pracas_nao_caem_no_mesmo_evento(self):
        from coletores.pracas import PRACAS, rotulo
        a, b = [rotulo(x) for x in PRACAS][:2]
        anteontem = tim(5, ANTEONTEM, pracas=[a]) + tim(20, ANTEONTEM,
                                                        pracas=[b])
        ontem = tim(15, ONTEM, pracas=[a, b])
        hoje = tim(5, HOJE, pracas=[a, b])
        d = dados(ontem, hoje, extras=anteontem)
        eventos = d.get("contratuais") or []
        self.assertEqual(len(eventos), 2,
                         "a praca que desfez e a que mexeu sao dois fatos")
        por_praca = {e["pracas"][0]: e for e in eventos}
        self.assertIn("voltou aos 5 GB", por_praca[a]["contratual_texto"])
        self.assertIn("de 15 para 5 GB", por_praca[b]["contratual_texto"])

    def test_e_a_mensagem_diz_as_duas_coisas(self):
        from coletores.pracas import PRACAS, rotulo
        a, b = [rotulo(x) for x in PRACAS][:2]
        anteontem = tim(5, ANTEONTEM, pracas=[a]) + tim(20, ANTEONTEM,
                                                        pracas=[b])
        t = montar(tim(15, ONTEM, pracas=[a, b]), tim(5, HOJE, pracas=[a, b]),
                   extras=anteontem)
        self.assertIn("voltou aos 5 GB em 24 horas", t)
        self.assertIn("de 15 para 5 GB", t)


class ONomeRepetidoNaoDecideSozinho(unittest.TestCase):
    """Duas ofertas podem dividir o nome, e ai nao se afirma nada.

    Quatro planos "Vivo Pre" tem o mesmo nome, contratos diferentes e
    precos diferentes. Elegendo um representante, a resposta dependeria
    da ordem em que o banco devolvesse as linhas - e foi exatamente
    assim que a primeira medicao desta reversao achou 20 casos de preco
    que nao existem.
    """

    def test_dois_contratos_sob_o_mesmo_nome_nao_rendem_reversao(self):
        from coletores.pracas import PRACAS, rotulo
        praca = [rotulo(p) for p in PRACAS][:1]
        # anteontem o mesmo nome aparece com 5 e com 99 de contrato
        anteontem = (tim(5, ANTEONTEM, pracas=praca)
                     + tim(99, ANTEONTEM, pracas=praca, gb=77))
        t = montar(tim(15, ONTEM, pracas=praca), tim(5, HOJE, pracas=praca),
                   extras=anteontem)
        self.assertIn("a franquia contratual foi de 15 para 5 GB", t)
        self.assertNotIn("voltou", t)

    def test_e_a_funcao_devolve_conjunto(self):
        janela = {ANTEONTEM: [
            {"operadora": "TIM", "produto": "controle", "praca": "X/XX",
             "nome_oferta": "TIM Controle Smart", "franquia_contratual_gb": 5},
            {"operadora": "TIM", "produto": "controle", "praca": "X/XX",
             "nome_oferta": "TIM Controle Smart",
             "franquia_contratual_gb": 99}]}
        v = robo._contratual_de_anteontem(janela, ONTEM)
        self.assertEqual(v[("TIM", "controle", "X/XX", "tim controle smart")],
                         {5, 99})


class OSelectQueOBancoDeMentiraNaoMede(unittest.TestCase):
    """A coluna tem de estar no select, e so o fonte prova isso aqui.

    O banco de mentira dos testes NAO projeta as colunas pedidas: ele
    aplica os filtros do PostgREST e devolve a linha inteira. Isso ja
    esconderia este defeito uma vez - em 30/10/2026 o detector da
    contratual passou por uma suite verde sem o campo no select de
    _indexar, e so a producao teria visto o None.

    Entao o teste olha o SELECT, e nao o resultado.
    """

    def test_a_janela_pede_a_contratual_ao_banco(self):
        import inspect
        fonte = inspect.getsource(robo._capturas_para_o_vigia)
        self.assertIn("franquia_contratual_gb", fonte,
                      "sem a coluna no select, anteontem vem None e a "
                      "reversao nunca e reconhecida em producao")


class OPrecoNaoGanhouAMarca(unittest.TestCase):
    """A marca existe so onde a medicao achou o caso.

    Preco, franquia anunciada, degrau em Mbps e lista de apps revertem
    ZERO vezes nos 35 dias publicados. Marca para eles seria salvaguarda
    morta - e salvaguarda morta esconde o risco de verdade em vez de
    cobri-lo, como o escape do "&" no relatorio ja ensinou.
    """

    def test_preco_que_volta_nao_sai_como_reversao(self):
        ida = tim(5, ONTEM, preco=69.99)
        volta = tim(5, HOJE, preco=58.99)
        t = montar(ida, volta, extras=tim(5, ANTEONTEM, preco=58.99))
        self.assertIn("58,99", t)
        self.assertNotIn("em 24 horas", t)


@unittest.skipIf(relatorio is None, "reportlab nao instalado")
class ORelatorioDizReversaoNaColunaDaVariacao(unittest.TestCase):

    def _texto(self, d):
        import pypdf
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        return "".join(p.extract_text()
                       for p in pypdf.PdfReader(caminho).pages)

    def test_a_coluna_da_variacao_diz_voltou(self):
        """O percentual de uma reversao e ruido: "-67%" sobre o desfazer
        de um "+200%" de ontem soa como reposicionamento. Os dois
        numeros continuam nas colunas ao lado."""
        d = dados(tim(15, ONTEM), tim(5, HOJE), extras=tim(5, ANTEONTEM))
        texto = self._texto(d)
        # a celula quebra em duas linhas na extracao do PDF
        self.assertIn("em 24h", texto)
        self.assertIn("voltou", texto)
        self.assertIn("15 GB", texto)
        self.assertIn("5 GB", texto)

    def test_e_segue_dizendo_o_percentual_no_movimento_de_ida(self):
        d = dados(tim(5, ONTEM), tim(15, HOJE), extras=tim(5, ANTEONTEM))
        texto = self._texto(d)
        self.assertNotIn("em 24h", texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
