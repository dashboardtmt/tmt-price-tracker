# -*- coding: utf-8 -*-
u"""A digital do leitor gravada no dado, para a atribuicao sair da memoria.

POR QUE EXISTE. Em 04/11/2026 duas datas de LEITURA_MUDOU_EM estavam
erradas por um dia - a coleta roda de madrugada e o commit entrou depois
dela -, e as duas custaram afirmacao falsa publicada: "a vitrine passou
a listar Max e Telecine" nas 20 pracas e "a Brisanet mexeu na
composicao" nas 7, as duas sendo commit nosso. A atribuicao dependia de
alguem lembrar de escrever uma data a mao.

Com a digital em cada captura, "o leitor mudou entre as duas coletas" e
FATO LIDO DO DADO. A declaracao continua, porque ela diz a causa em
portugues; o que ela deixa de ser e a unica fonte da verdade.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
from coletores import armazenamento                           # noqa: E402
from _apoio import banco, em_todas, oferta, sem_declaracao    # noqa: E402

HOJE, ONTEM = "2026-10-21", "2026-10-20"


def com_versao(linhas, versao):
    return [dict(l, versao_leitura=versao) for l in linhas]


class ADigitalDoLeitor(unittest.TestCase):

    def test_sai_curta_e_estavel(self):
        a = armazenamento.versao_da_leitura()
        self.assertEqual(len(a), 12)
        self.assertEqual(a, armazenamento.versao_da_leitura())

    def test_a_digital_depende_do_codigo_dos_coletores(self):
        """SEM ESTE TESTE A DIGITAL PODIA SER CONSTANTE e passar: o
        provador trocou o hash por doze zeros (Vb1) e a suite ficou
        verde, porque so se media o FORMATO. Agora se mede o que ela
        serve para medir."""
        import tempfile
        um = "def ler(x):\n    return x + 1\n"
        outro = "def ler(x):\n    return x + 2\n"
        with tempfile.TemporaryDirectory() as a:
            with tempfile.TemporaryDirectory() as b:
                for onde, corpo in ((a, um), (b, outro)):
                    with open(os.path.join(onde, "vivo.py"), "w",
                              encoding="utf-8") as f:
                        f.write(corpo)
                da = armazenamento.versao_da_leitura(a)
                db = armazenamento.versao_da_leitura(b)
        self.assertEqual(len(da), 12)
        self.assertNotEqual(da, db,
                            "codigo diferente, digital diferente")

    def test_comentario_nao_muda_a_digital_tambem_na_funcao(self):
        """A contraparte do de cima, na funcao de verdade e nao no
        ast.dump solto: comentario novo nao pode virar "o leitor
        mudou"."""
        import tempfile
        limpo = "def ler(x):\n    return x + 1\n"
        comentado = ("# explicando por que\ndef ler(x):\n"
                     "    # e aqui tambem\n    return x + 1\n")
        with tempfile.TemporaryDirectory() as a:
            with tempfile.TemporaryDirectory() as b:
                for onde, corpo in ((a, limpo), (b, comentado)):
                    with open(os.path.join(onde, "vivo.py"), "w",
                              encoding="utf-8") as f:
                        f.write(corpo)
                self.assertEqual(armazenamento.versao_da_leitura(a),
                                 armazenamento.versao_da_leitura(b))

    def test_comentario_nao_muda_a_digital(self):
        """Neste projeto o comentario e maior que o codigo e muda todo
        dia. Se ele entrasse na digital, todo push viraria "o leitor
        mudou" e o sinal nao valeria nada - salvaguarda que sempre
        acende nao distingue nada."""
        import ast
        base = "def f(x):\n    return x + 1\n"
        with_comment = "# explicando\ndef f(x):\n    # e aqui\n    return x + 1\n"
        self.assertEqual(ast.dump(ast.parse(base)),
                         ast.dump(ast.parse(with_comment)))

    def test_codigo_diferente_muda_a_digital(self):
        import ast
        a = ast.dump(ast.parse("def f(x):\n    return x + 1\n"))
        b = ast.dump(ast.parse("def f(x):\n    return x + 2\n"))
        self.assertNotEqual(a, b)


class ADigitalViajaNaCaptura(unittest.TestCase):
    """Sem coluna nova e sem ALTER TABLE: dentro do bruto, como a
    assinatura SVA. E numa COPIA - mexer no dicionario de quem chamou
    faria o coletor devolver um campo que ele nao leu."""

    def test_o_bruto_gravado_leva_a_versao(self):
        capturado = {}
        guardas = (armazenamento._config, armazenamento._pedir)
        self.addCleanup(setattr, armazenamento, "_config", guardas[0])
        self.addCleanup(setattr, armazenamento, "_pedir", guardas[1])
        armazenamento._config = lambda: ("http://x", "k")

        def falso(url, chave, caminho, corpo, prefer):
            capturado["corpo"] = corpo
            return 201, "[]"

        armazenamento._pedir = falso
        o = {"operadora": "Vivo", "produto": "movel", "praca": "Sao Paulo/SP",
             "nome_oferta": "Vivo Pós", "preco_promocional": 119.9,
             "franquia_anunciada_gb": 50,
             "capturado_em": "2026-11-05T09:00:00+00:00"}
        armazenamento.gravar_capturas([o])
        enviado = capturado["corpo"]
        self.assertEqual(enviado[0]["bruto"]["versao_leitura"],
                         armazenamento.versao_da_leitura())
        self.assertNotIn("versao_leitura", o,
                         "a copia existe para nao sujar o dado do coletor")


class AAtribuicaoSaiDoDado(unittest.TestCase):

    def montar(self, versao_ontem, versao_hoje):
        banco(com_versao(em_todas(nome="Vivo Pós com Max", preco=150.0,
                                  gb=60, data=ONTEM,
                                  chave="Vivo|movel|60gb|com_max"),
                         versao_ontem)
              + com_versao(em_todas(nome="Vivo Pós com Max", preco=150.0,
                                    gb=60, data=HOJE,
                                    chave="Vivo|movel|60gb|com_max_telecine",
                                    apps=["max", "telecine"]),
                           versao_hoje))
        return robo.mudancas(HOJE, ONTEM)

    def test_leitor_diferente_torna_a_mudanca_nossa(self):
        sem_declaracao(self)
        m = self.montar("aaaaaaaaaaaa", "bbbbbbbbbbbb")
        self.assertEqual(len(m["remodeladas"]), 0,
                         "uma operadora so, em todas as pracas: sem a "
                         "digital isto sairia como movimento de mercado")
        self.assertEqual(len(m["leitura"]), 1)

    def test_mesmo_leitor_deixa_a_heuristica_decidir(self):
        sem_declaracao(self)
        m = self.montar("aaaaaaaaaaaa", "aaaaaaaaaaaa")
        self.assertEqual(len(m["remodeladas"]), 1)
        self.assertEqual(len(m["leitura"]), 0)

    def test_linha_sem_digital_nao_afirma_nada(self):
        """Captura gravada antes de 05/11/2026 nao tem digital, e
        ausencia nao e diferenca: vale o que valia antes."""
        sem_declaracao(self)
        m = self.montar(None, "bbbbbbbbbbbb")
        self.assertEqual(len(m["leitura"]), 0)
        self.assertEqual(len(m["remodeladas"]), 1)

    def test_a_mensagem_diz_que_o_leitor_mudou_e_pede_a_causa(self):
        sem_declaracao(self)
        self.montar("aaaaaaaaaaaa", "bbbbbbbbbbbb")
        texto, _ = robo.montar_mensagem(HOJE, ONTEM)
        self.assertIn("o leitor mudou entre as duas coletas", texto)
        self.assertIn("LEITURA_MUDOU_EM", texto)
        self.assertNotIn("costuma ser", texto,
                         "com a digital, "
                         "\"costuma ser\" virou \"foi\"")

    def test_a_causa_declarada_continua_vencendo_a_frase(self):
        """A data declarada diz O QUE mudou; a digital diz que mudou.
        Com as duas, a mensagem traz a causa escrita."""
        m = self.montar("aaaaaaaaaaaa", "bbbbbbbbbbbb")
        self.assertEqual(len(m["leitura"]), 1)
        texto, _ = robo.montar_mensagem(HOJE, ONTEM)
        self.assertIn("a leitura mudou hoje:", texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
