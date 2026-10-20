# -*- coding: utf-8 -*-
"""O relatorio em PDF tem de ser gerado nos dois extremos.

POR QUE EXISTIA UM BURACO AQUI. O relatorio nao tinha teste nenhum, e e
o arquivo com mais caminhos: cinco tabelas de mudanca, quatro de
catalogo, a cobertura, as denuncias e a nota metodologica. Ele e gerado
dentro de um try/except no robo, e por desenho - o anexo nao pode
derrubar o aviso do dia. So que isso tambem significa que um erro aqui
sai como uma frase de rodape na mensagem e mais nada: o PDF simplesmente
nao chega, todo dia, sem ninguem notar.

Os dois extremos sao o que importa: o dia cheio, em que todos os
detectores acharam algo, e o dia vazio, em que a comparacao nao
aconteceu. O segundo e o que ja quebrou - com "if not itens: continue",
secoes inteiras desapareciam em vez de dizer que nao havia dado.

O teste e pulado quando o reportlab nao esta instalado: ele e dependencia
so do passo do aviso, e nao da coleta.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import relatorio
except ImportError:                                      # pragma: no cover
    relatorio = None

HOJE, ONTEM = "2026-10-21", "2026-10-20"


def linha(operadora="Vivo", produto="movel", nome="Vivo Pós", preco=119.90,
          gb=50, mbps=None):
    return {"operadora": operadora, "produto": produto, "nome_oferta": nome,
            "preco_promocional": preco, "franquia_anunciada_gb": gb,
            "degrau_mbps": mbps,
            "destaque": ("%s GB" % gb) if gb else ("%s Mbps" % mbps)}


DIA_CHEIO = {
    "dia": HOJE, "ontem": ONTEM,
    "mudancas_preco": [{"atual": linha(preco=139.90), "antes": linha(),
                        "pracas": ["Sao Paulo/SP", "Rio de Janeiro/RJ"],
                        "onde": "em 2 de 20: Rio de Janeiro, Sao Paulo",
                        "universo": 20}],
    "mudancas_composicao": [{"atual": dict(linha(), assinatura_sva="a+b"),
                             "antes": dict(linha(), assinatura_sva="a"),
                             "pracas": ["Sao Paulo/SP"],
                             "onde": "em 1 de 20: Sao Paulo"}],
    "renomeadas": [{"atual": linha(nome="TIM Controle Smart", operadora="TIM"),
                    "antes": linha(nome="TIM Controle", operadora="TIM"),
                    "pracas": ["Sao Paulo/SP"], "onde": "em 1 de 20: Sao Paulo"}],
    "grades": [{"operadora": "Vivo", "produto": "prepago", "unidade": "GB",
                "saltos": [(30.0, 25, 20)], "precos": [(20, 30.0, 35.0)],
                "pracas": ["Sao Paulo/SP"], "onde": "em 1 de 20: Sao Paulo"}],
    "voltaram": [{"operadora": "Vivo", "produto": "prepago", "entrega": 25,
                  "unidade": "GB", "antes": 30.0, "agora": 35.0,
                  "quando": "2026-10-15", "nome": "Vivo Pré",
                  "pracas": ["Sao Paulo/SP"], "onde": "em 1 de 20: Sao Paulo"}],
    "remodeladas": [{"operadora": "Vivo", "produto": "prepago",
                     "nome": "Vivo Pré", "unidade": "GB",
                     "antes_preco": 30.0, "agora_preco": 35.0,
                     "antes_entrega": 25, "agora_entrega": 20,
                     "preco_mudou": True, "entrega_mudou": True,
                     "versao_mudou": False,
                     "bundle_antes": None, "bundle_agora": None,
                     "atual": linha(), "antes": linha(),
                     "pracas": ["Sao Paulo/SP"], "onde": "em 1 de 20: Sao Paulo"}],
    # as que a nossa leitura explica, e nao o mercado
    "leitura": [{"operadora": "TIM", "produto": "controle",
                 "nome": "TIM Controle Redes Sociais", "unidade": "GB",
                 "antes_preco": 64.99, "agora_preco": 64.99,
                 "antes_entrega": 46, "agora_entrega": 46,
                 "preco_mudou": False, "entrega_mudou": False,
                 "versao_mudou": True,
                 "bundle_antes": "sem assinatura inclusa",
                 "bundle_agora": "com apps de catálogo",
                 "atual": linha(operadora="TIM"), "antes": linha(operadora="TIM"),
                 "pracas": ["Curitiba/PR", "Manaus/AM"],
                 "onde": "em 2 de 18: Curitiba, Manaus"}],
    "erro_comparacao": None,
    "ponto_cego": "2 oferta(s) não foram comparadas (Vivo Família 2 + TV).",
    "cobertura": {"pares": 900, "hoje": 1000, "ontem": 980, "fracao": 0.9,
                  "por_operadora": {"Vivo": (400, 420), "Claro": (500, 580)}},
    "denuncias": [("grave", "Brisanet: 119 de 119 ofertas sem velocidade"),
                  ("atencao", "3 oferta(s) sem preco")],
    "coletas": [{"operadora": "Vivo", "pracas_ok": 20, "pracas_pedidas": 20,
                 "ofertas": 420, "sucesso": True}],
    "falhas": [], "sem_registro": ["NuCel"], "total_ofertas": 1000,
}

DIA_VAZIO = {
    "dia": HOJE, "ontem": ONTEM,
    "mudancas_preco": [], "mudancas_composicao": [], "renomeadas": [],
    "grades": [], "voltaram": [], "remodeladas": [], "leitura": [],
    "erro_comparacao": None, "ponto_cego": None, "cobertura": None,
    "denuncias": [], "coletas": [], "falhas": [],
    "sem_registro": ["Vivo", "TIM", "Claro"], "total_ofertas": 0,
}

CATALOGO = {"controle": [linha(operadora="TIM", produto="controle",
                               nome="TIM Smart", preco=59.99, gb=40)],
            "btl": [], "prepago": [], "combo": []}


@unittest.skipIf(relatorio is None, "reportlab nao instalado")
class GerarOPdf(unittest.TestCase):

    def _gerar(self, dados, entradas):
        pasta = tempfile.mkdtemp()
        caminho = os.path.join(pasta, "r.pdf")
        feito = relatorio.gerar(dados, entradas, caminho)
        self.assertTrue(os.path.exists(feito))
        self.assertGreater(os.path.getsize(feito), 2000)
        return feito

    def test_dia_cheio_sai_inteiro(self):
        self._gerar(DIA_CHEIO, CATALOGO)

    def test_dia_vazio_tambem_sai(self):
        """Dia sem coleta nenhuma e o dia em que mais se olha o anexo."""
        self._gerar(DIA_VAZIO, {})

    def test_produto_sem_oferta_nao_perde_a_secao(self):
        """AUDITORIA 18. Com "if not itens: continue" a secao do produto
        desaparecia, e quem le nao distingue "nao ha oferta" de "o
        relatorio quebrou no meio"."""
        import pypdf
        caminho = self._gerar(DIA_CHEIO, CATALOGO)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        for titulo in ("Controle", "Below-the-line", "Pré-pago", "Combo"):
            self.assertIn(titulo, texto, "a seção de %s sumiu" % titulo)
        self.assertIn("Sem dados disponíveis", texto)

    def test_as_cinco_tabelas_de_mudanca_existem(self):
        """A mensagem manda o leitor ao relatorio - "e mais N de grade no
        relatorio". Se a tabela nao existe la, a mensagem mente."""
        import pypdf
        caminho = self._gerar(DIA_CHEIO, CATALOGO)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        for titulo in ("Mudanças de preço",
                       "Ofertas reapresentadas com outra configuração",
                       "Alterações atribuíveis à leitura dos dados",
                       "Reorganização de grade",
                       "Degraus retomados com preço diferente",
                       "Alterações de denominação",
                       "Cobertura da comparação"):
            self.assertIn(titulo, texto, "falta a tabela: %s" % titulo)

    def test_o_que_a_leitura_explica_fica_em_tabela_propria(self):
        """A mensagem diz "Detalhe no relatório" sobre as ofertas que
        mudaram de versão por conta da nossa leitura. Misturar essas com
        as de mercado numa tabela só transformaria mudança de parser em
        movimento de operadora - a atribuição errada mais fácil de fazer
        aqui."""
        import pypdf
        caminho = self._gerar(DIA_CHEIO, CATALOGO)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        # o PDF quebra a celula em duas linhas: confere o pedaco que
        # nao pode ter sido quebrado
        self.assertIn("TIM Controle Redes", texto)
        self.assertIn("com apps de catálogo", texto)
        self.assertIn("em 2 de 18", texto)

    def test_a_pracas_nao_sai_vazia(self):
        """AUDITORIA 9. O relatorio lia uma chave "onde" que ninguem
        escrevia, e a coluna Praças saia "—" em todas as linhas de toda
        edicao do relatorio."""
        import pypdf
        caminho = self._gerar(DIA_CHEIO, CATALOGO)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        self.assertIn("Rio de Janeiro", texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
