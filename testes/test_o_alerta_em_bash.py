# -*- coding: utf-8 -*-
u"""Alerta em bash limpa o token antes de montar a URL.

O QUE ACONTECEU EM 17/11/2026. O export da tela falhou e o job
tela_falhou rodou - e morreu com exit 3 do curl, "URL malformada". O
segredo TELEGRAM_BOT_TOKEN tem espaco no fim: todo codigo Python do
projeto faz .strip() nele, o curl nao. O painel ficou no dia 16 e o
alerta que existe exatamente para isso nao chegou.

Prende duas coisas em todo curl ao Telegram dos workflows: o token
limpo antes, e o --fail, para que o Telegram recusando a mensagem deixe
o passo vermelho em vez de imprimir "enviado".
"""
import glob
import io
import os
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMPA = '''TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"'''


class AlertaEmBash(unittest.TestCase):

    def test_todo_curl_ao_telegram_limpa_o_token_e_falha_alto(self):
        achados = 0
        for arq in glob.glob(os.path.join(RAIZ, ".github", "workflows", "*.yml")):
            linhas = io.open(arq, encoding="utf-8").read().splitlines()
            for i, l in enumerate(linhas):
                if "api.telegram.org/bot${TOKEN}" not in l:
                    continue
                achados += 1
                antes = "\n".join(linhas[max(0, i - 4):i])
                nome = "%s:%d" % (os.path.basename(arq), i + 1)
                self.assertIn(LIMPA, antes, nome + " monta a URL com o token cru")
                self.assertIn("--fail", l, nome + " sem --fail")
        self.assertGreaterEqual(achados, 4)


if __name__ == "__main__":
    unittest.main()
