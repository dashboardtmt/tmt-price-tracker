"""Confere se o bot do Telegram consegue mandar a mensagem diaria.

Nao escreve nada em lugar nenhum. So manda uma mensagem de teste e diz
se funcionou. Os segredos vem do ambiente; o token nunca e impresso.

Uso:  python testes/teste_telegram.py
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


def mascarar(token):
    """Mostra so o suficiente para conferir qual bot e, sem expor o token."""
    if not token or ":" not in token:
        return "(formato inesperado)"
    id_bot = token.split(":")[0]
    return "bot %s, restante oculto" % id_bot


def chamar(token, metodo, dados=None):
    url = "https://api.telegram.org/bot%s/%s" % (token, metodo)
    corpo = urllib.parse.urlencode(dados).encode() if dados else None
    req = urllib.request.Request(url, data=corpo, method="POST" if dados else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode()), e.code
        except Exception:
            return None, e.code
    except Exception as e:
        return None, str(e)


def main():
    # .strip() e essencial: colar o token no GitHub costuma levar junto uma
    # quebra de linha, e a URL da API nao aceita caractere de controle.
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    print("=" * 60)
    print("TESTE DO AVISO DIARIO NO TELEGRAM")
    print("=" * 60)
    print("  token ...... %s" % (mascarar(token) if token else "AUSENTE"))
    print("  chat_id .... %s" % (chat or "AUSENTE"))

    if not token or not chat:
        print("\n  FALHOU: segredo faltando no repositorio.")
        return 1

    # 1. o bot existe e o token e valido?
    info, err = chamar(token, "getMe")
    if not info or not info.get("ok"):
        print("\n  FALHOU ao identificar o bot: %s" % (info or err))
        print("  Provavel causa: token invalido ou revogado.")
        return 1
    print("  bot ........ @%s" % info["result"].get("username"))

    # 2. consegue mandar mensagem no formato que sera usado de verdade?
    agora = datetime.now(timezone(timedelta(hours=-3)))
    texto = (
        "Price Tracker - teste de configuracao\n"
        "%s\n\n"
        "Se voce esta lendo isto, o aviso diario das 8h vai funcionar.\n\n"
        "Exemplo do que chegara todo dia:\n\n"
        "Coleta OK: 6 de 6 operadoras, 20 pracas\n\n"
        "Controle, plano de entrada (SP):\n"
        "Vivo   45GB  R$ 59,00\n"
        "Claro  40GB  R$ 59,90\n"
        "TIM    38GB  R$ 58,99"
    ) % agora.strftime("%d/%m/%Y %H:%M")

    envio, err = chamar(token, "sendMessage", {"chat_id": chat, "text": texto})
    if envio and envio.get("ok"):
        print("\n  SUCESSO: mensagem enviada. Confira no Telegram.")
        return 0

    print("\n  FALHOU ao enviar: %s" % (envio or err))
    desc = (envio or {}).get("description", "")
    if "chat not found" in desc.lower():
        print("  Causa: o chat_id esta errado, ou voce ainda nao mandou")
        print("  /start para o bot. O Telegram nao deixa o bot escrever")
        print("  primeiro para alguem que nunca falou com ele.")
    elif "unauthorized" in desc.lower():
        print("  Causa: token invalido. Foi revogado e nao atualizado?")
    return 1


if __name__ == "__main__":
    sys.exit(main())
