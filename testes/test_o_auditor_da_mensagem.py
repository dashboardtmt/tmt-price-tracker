# -*- coding: utf-8 -*-
u"""O auditor: cada afirmacao rededuzida das linhas cruas antes de sair.

POR QUE EXISTE. O vigia confere o DADO; ninguem conferia a AFIRMACAO. Em
04/11/2026 a mensagem publicou "Vivo Lite Anual III saiu da vitrine,
estava a 40,00, em todas as 2 pracas" enquanto um 40 GB a R$ 40,00
estava na prateleira das mesmas duas, e publicou "a vitrine passou a
listar Max e Telecine" sobre mudanca que era nossa. Nos dois casos o
dado estava certo e a FRASE estava errada.

E ELE ACENDE. Medido na serie publicada: 76 eventos em 28 dias, zero
recusas - auditor que recusa noticia verdadeira e pior do que nenhum,
porque cala o mercado. Os testes aqui sao o controle do outro lado:
afirmacao torta TEM de ser recusada, senao "zero recusas" so quer dizer
"nao olhei".

AS TRES RESPOSTAS. "Sustenta", "nao sustenta" e "nao da para conferir"
sao tres estados, e confundir os dois ultimos foi o primeiro defeito
deste auditor: ele recusou sete eventos verdadeiros porque a identidade
aparecia duas vezes na janela crua - caso em que o comparador desempata
pelo codigo de registro, que o auditor nao tem.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auditor                                                # noqa: E402

PRACAS = ("Sao Paulo/SP", "Rio de Janeiro/RJ", "Belo Horizonte/MG")


def linha(praca, preco, nome="Vivo Pós", chave="Vivo|movel|50gb|simples",
          contratual=None, gb=50, mbps=None):
    return {"operadora": "Vivo", "produto": "movel", "praca": praca,
            "chave": chave, "nome_oferta": nome, "preco_promocional": preco,
            "franquia_anunciada_gb": gb, "degrau_mbps": mbps,
            "franquia_contratual_gb": contratual}


def evento_preco(pracas, antes=119.9, agora=129.9):
    return {"pracas": list(pracas),
            "antes": linha(pracas[0], antes),
            "atual": linha(pracas[0], agora)}


def dados(**kw):
    base = {"precos": [], "contratuais": [], "remodeladas": [], "saidas": []}
    base.update(kw)
    return base


class OQueOAuditorRecusa(unittest.TestCase):

    def test_praca_em_que_o_preco_nao_mudou(self):
        """A afirmacao diz tres pracas; o dado sustenta duas."""
        ontem = [linha(p, 119.9) for p in PRACAS]
        hoje = [linha(p, 129.9 if p != PRACAS[2] else 119.9) for p in PRACAS]
        recusas, _ = auditor.auditar(
            dados(precos=[evento_preco(PRACAS)]), hoje, ontem)
        self.assertEqual(len(recusas), 1)
        self.assertIn("1 de 3", recusas[0][2])
        self.assertIn("Belo Horizonte", recusas[0][2])

    def test_preco_anterior_que_a_linha_de_ontem_nega(self):
        """O numero afirmado tem de ser o numero gravado - e o caso em
        que o par veio errado e a mensagem publica um reajuste que nao
        existiu, com os dois valores de ofertas diferentes."""
        ontem = [linha(p, 99.9) for p in PRACAS]
        hoje = [linha(p, 129.9) for p in PRACAS]
        recusas, _ = auditor.auditar(
            dados(precos=[evento_preco(PRACAS)]), hoje, ontem)
        self.assertEqual(len(recusas), 1)

    def test_saida_de_oferta_que_continua_na_vitrine(self):
        ontem = [linha(p, 45.0, nome="Vivo Lite Anual III") for p in PRACAS]
        hoje = list(ontem)
        e = {"operadora": "Vivo", "produto": "movel",
             "nome_oferta": "Vivo Lite Anual III", "pracas": list(PRACAS)}
        recusas, _ = auditor.auditar(dados(saidas=[e]), hoje, ontem)
        self.assertEqual(len(recusas), 1)
        self.assertEqual(recusas[0][0], "saidas")

    def test_contratual_que_o_dado_nao_confirma(self):
        ontem = [linha(p, 59.9, contratual=5) for p in PRACAS]
        hoje = [linha(p, 59.9, contratual=15) for p in PRACAS]
        e = {"operadora": "Vivo", "produto": "movel", "nome": "Vivo Pós",
             "antes_contratual": 5, "agora_contratual": 30,
             "pracas": list(PRACAS),
             "antes": ontem[0], "atual": hoje[0]}
        recusas, _ = auditor.auditar(dados(contratuais=[e]), hoje, ontem)
        self.assertEqual(len(recusas), 1)


class OQueOAuditorDeixaPassar(unittest.TestCase):

    def test_a_afirmacao_que_o_dado_sustenta(self):
        ontem = [linha(p, 119.9) for p in PRACAS]
        hoje = [linha(p, 129.9) for p in PRACAS]
        recusas, _ = auditor.auditar(
            dados(precos=[evento_preco(PRACAS)]), hoje, ontem)
        self.assertEqual(recusas, [])

    def test_evento_que_cobre_parte_das_pracas(self):
        """O detector separa de proposito: "a praca que desfez e a que
        mexeu pela primeira vez sao dois fatos". Exigir evento maximo
        recusava 11 casos verdadeiros na primeira rodada."""
        ontem = [linha(p, 119.9) for p in PRACAS]
        hoje = [linha(p, 129.9) for p in PRACAS]
        recusas, _ = auditor.auditar(
            dados(precos=[evento_preco(PRACAS[:1])]), hoje, ontem)
        self.assertEqual(recusas, [])

    def test_identidade_repetida_nao_da_para_conferir_e_nao_e_falsa(self):
        """Duas linhas na mesma identidade: o comparador desempata pelo
        codigo de registro, que nao esta na janela crua. Recusar aqui
        seria chamar de falso o que nao se conseguiu conferir."""
        ontem = [linha(p, 119.9) for p in PRACAS] + [linha(PRACAS[0], 390.0)]
        hoje = [linha(p, 129.9) for p in PRACAS] + [linha(PRACAS[0], 410.0)]
        recusas, fora = auditor.auditar(
            dados(precos=[evento_preco(PRACAS)]), hoje, ontem)
        self.assertEqual(recusas, [])
        self.assertTrue([k for k in fora if k.startswith("precos:")],
                        "o que nao deu para conferir tem de sair dito")

    def test_saida_em_praca_que_ninguem_leu_hoje(self):
        """Praca sem coleta hoje nao sustenta NEM NEGA a saida - e o
        filtro 1 do detector, pela outra ponta.

        E O AUDITOR NAO PODE CONFIRMAR. Sem esta guarda, a praca que
        ninguem leu entra como saida CONFIRMADA - a oferta "nao esta
        hoje" porque ninguem olhou -, e o auditor passa a chancelar
        exatamente o defeito que o filtro 1 existe para impedir. O
        provador mostrou que medir so a recusa nao ve isso (Ad4): o que
        delata e a ressalva, que tem de aparecer.
        """
        ontem = [linha(p, 45.0, nome="Vivo Lite") for p in PRACAS]
        hoje = [linha(PRACAS[0], 50.0, nome="Outra Oferta")]
        e = {"operadora": "Vivo", "produto": "movel",
             "nome_oferta": "Vivo Lite", "pracas": list(PRACAS)}
        recusas, fora = auditor.auditar(dados(saidas=[e]), hoje, ontem)
        self.assertEqual(recusas, [])
        notas = [v for k, v in fora.items() if k.startswith("saidas:")]
        self.assertEqual(len(notas), 1,
                         "praca sem coleta tem de sair como nao conferida")
        self.assertIn("2 de 3", notas[0],
                      "duas das tres pracas nao foram lidas hoje")


class ARecusaNaoApaga(unittest.TestCase):

    def test_o_evento_recusado_sai_da_lista_e_fica_no_dicionario(self):
        ontem = [linha(p, 119.9) for p in PRACAS]
        hoje = [linha(p, 119.9) for p in PRACAS]
        d = dados(precos=[evento_preco(PRACAS)])
        auditor.aplicar(d, hoje, ontem)
        self.assertEqual(d["precos"], [], "a afirmacao falsa nao sai")
        self.assertEqual(len(d["recusadas"]), 1,
                         "mas a recusa fica, para poder ser auditada")

    def test_sem_janela_crua_nada_e_auditado_e_isso_sai_dito(self):
        """Nao conferir e um estado, e ele tem de aparecer: "auditado e
        aprovado" nunca pode ser suposto."""
        d = dados(precos=[evento_preco(PRACAS)])
        auditor.aplicar(d, [], [])
        self.assertEqual(len(d["precos"]), 1, "sem conferencia, nao se apaga")
        self.assertEqual(d["recusadas"], [])
        for tipo in auditor.AUDITADOS:
            self.assertIn(tipo, d["nao_auditado"])

    def test_a_recusa_chega_ao_relatorio_com_a_razao(self):
        """A MENSAGEM PROMETE "detalhe no relatorio". Sem a secao, a
        promessa era falsa - "canal gravado sem leitor" e o defeito que
        este projeto mais encontra, e aqui ele apareceria do lado pior:
        a mensagem mandando ler uma pagina que nao existe.
        """
        try:
            import pypdf                                      # noqa: F401
        except ImportError:
            self.skipTest("pypdf ausente")
        import tempfile
        import relatorio
        from test_relatorio import CATALOGO, DIA_CHEIO
        d = dict(DIA_CHEIO,
                 recusadas=[("precos", "Vivo Pós",
                             "o dado nao sustenta a afirmacao em 1 de 3 "
                             "praca(s) (Belo Horizonte)")],
                 nao_auditado={"composicao": "a assinatura SVA nao esta "
                                             "na janela crua"})
        pasta = tempfile.mkdtemp()
        caminho = os.path.join(pasta, "r.pdf")
        relatorio.gerar(d, CATALOGO, caminho)
        with open(caminho, "rb") as f:
            import pypdf as _p
            texto = "".join(p.extract_text()
                            for p in _p.PdfReader(f).pages)
        self.assertIn("Confer", texto)
        self.assertIn("Vivo P", texto)
        self.assertIn("Belo Horizonte", texto)
        self.assertIn("composicao", texto)

    def test_todo_tipo_de_evento_esta_auditado_ou_declarado_fora(self):
        """A mesma regra de COLETORES x RAIAS: tipo novo de evento nao
        pode nascer sem alguem decidir se o auditor fala por ele."""
        import robo
        tipos = {k for k in robo.mudancas.__doc__.split()
                 if k in ("precos", "composicao", "renomeadas", "grades",
                          "voltaram", "remodeladas", "contratuais",
                          "saidas", "leitura")}
        cobertos = set(auditor.AUDITADOS) | set(auditor.FORA)
        self.assertEqual(tipos - cobertos, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
