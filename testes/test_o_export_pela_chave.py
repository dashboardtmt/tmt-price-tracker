# -*- coding: utf-8 -*-
u"""O export da tela pagina pela chave primaria, nao por offset.

O QUE ACONTECEU EM 17/11/2026. A coleta e a mensagem sairam, e o job da
tela morreu no primeiro passo: HTTP 500, codigo 57014, "canceling
statement due to statement timeout". O painel ficou no dia 16.

Com offset, cada pagina pedia ao banco a janela inteira ordenada - com
o jsonb aberto em todas as linhas - e descartava o que vinha antes do
offset. Eram 82 paginas, logo 82 vezes a tabela: custo no quadrado da
serie, com a janela de 90 dias ainda pela metade.

O que este arquivo prende, e cada um volta CALADO:

  1. a volta do offset: o export passa de novo no teste do dia a dia
     e estoura quando a serie cresce;
  2. a ordem da saida: a tela recebia (data, operadora, id) do banco e
     agora a ordem e refeita no cliente - se ela mudar, a tela recebe
     outro arquivo com os mesmos numeros;
  3. o id vazando para o arquivo publicado;
  4. "pagina menor que o pedido" voltando a encerrar a busca: se o
     servidor cortar abaixo de PAGINA, a exportacao para no meio;
  5. a chave que nao avanca virando laco infinito em vez de erro.

Passa pelo main(), que e o caminho que o workflow roda.
"""
import io
import json
import os
import random
import sys
import tempfile
import unittest
import urllib.parse
from datetime import date, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import exportar                       # noqa: E402
from coletores import armazenamento   # noqa: E402


def _dia(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _banco():
    """Capturas de 3 dias x 3 operadoras, com ids EMBARALHADOS entre os
    grupos - so dentro de cada grupo o id segue a ordem de gravacao - e
    uma captura fora da janela, que nao pode sair."""
    grupos = []
    for d in (2, 1, 0):
        for op in ("Claro", "TIM", "Vivo"):
            grupos.append([{"data_captura": _dia(d), "operadora": op,
                            "nome_oferta": "%s-%d-%d" % (op, d, k)}
                           for k in range(9)])
    rnd = random.Random(3)
    filas, linhas = [list(g) for g in grupos], []
    while filas:
        i = rnd.randrange(len(filas))
        linhas.append(filas[i].pop(0))
        if not filas[i]:
            filas.pop(i)
    linhas.insert(5, {"data_captura": _dia(400), "operadora": "Claro",
                      "nome_oferta": "velha"})
    banco = []
    for i, l in enumerate(linhas, start=1):
        r = {"id": i * 3}
        r.update(l)
        banco.append(r)
    esperado = sorted((dict(l) for l in banco if l["data_captura"] >= _dia(90)),
                      key=lambda l: (l["data_captura"], l["operadora"], l["id"]))
    for l in esperado:
        del l["id"]
    return banco, esperado


class ExportPelaChave(unittest.TestCase):

    def setUp(self):
        self.banco, self.esperado = _banco()
        self.pedidos = []
        self.teto = None           # corte do servidor abaixo de PAGINA
        self.travar = False        # servidor que ignora o id=gt
        self._consultar = armazenamento.consultar
        self._pagina = exportar.PAGINA
        armazenamento.consultar = self._falso
        exportar.PAGINA = 7

    def tearDown(self):
        armazenamento.consultar = self._consultar
        exportar.PAGINA = self._pagina

    def _falso(self, caminho):
        self.pedidos.append(caminho)
        q = urllib.parse.parse_qs(caminho.split("?", 1)[1])
        desde = q["data_captura"][0].split(".", 1)[1]
        depois = 0 if self.travar else int(q["id"][0].split(".", 1)[1])
        lim = int(q["limit"][0])
        if self.teto:
            lim = min(lim, self.teto)
        fora = [dict(l) for l in self.banco
                if l["data_captura"] >= desde and l["id"] > depois]
        fora.sort(key=lambda l: l["id"])
        return fora[:lim], None

    def _rodar(self):
        with tempfile.TemporaryDirectory() as tmp:
            saida = os.path.join(tmp, "dados.json")
            argv = sys.argv
            sys.argv = ["exportar.py", "--dias", "90", "--saida", saida]
            try:
                rc = exportar.main()
            finally:
                sys.argv = argv
            if rc != 0:
                return rc, None
            with io.open(saida, encoding="utf-8") as f:
                return rc, json.loads(f.read())

    def test_sai_o_mesmo_arquivo_na_ordem_do_banco(self):
        rc, dados = self._rodar()
        self.assertEqual(rc, 0)
        self.assertEqual(dados, self.esperado)
        self.assertNotIn("velha", [l["nome_oferta"] for l in dados])

    def test_o_id_nao_vaza_para_o_arquivo(self):
        _, dados = self._rodar()
        self.assertTrue(all("id" not in l for l in dados))

    def test_nenhuma_pagina_usa_offset(self):
        self._rodar()
        self.assertGreater(len(self.pedidos), 3)
        for p in self.pedidos:
            self.assertNotIn("offset=", p)
            self.assertIn("&id=gt.", p)
            self.assertIn("order=id.asc", p)
            self.assertIn("select=id,", p)

    def test_servidor_que_corta_abaixo_da_pagina_nao_encerra_a_busca(self):
        self.teto = 4
        rc, dados = self._rodar()
        self.assertEqual(rc, 0)
        self.assertEqual(dados, self.esperado)

    def test_chave_que_nao_avanca_e_erro_e_nao_laco(self):
        self.travar = True
        rc, dados = self._rodar()
        self.assertEqual(rc, 1)
        self.assertLess(len(self.pedidos), 5)


if __name__ == "__main__":
    unittest.main()
