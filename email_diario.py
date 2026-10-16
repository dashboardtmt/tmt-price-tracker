# -*- coding: utf-8 -*-
"""Manda a mensagem do dia por e-mail, com o relatorio em anexo.

POR QUE EXISTE. O Telegram chega no telefone; o e-mail chega onde o
trabalho acontece, da para encaminhar para outra pessoa e fica
arquivado e pesquisavel sem depender de rolar conversa.

E O MESMO CONTEUDO. O texto e o PDF sao os que o robo ja montou para o
Telegram - nao ha um levantamento proprio aqui. Se os dois canais
tivessem fontes separadas, um dia iam discordar.

COMO ELE SE LIGA. Por tres segredos no repositorio. Enquanto eles nao
existirem, este modulo nao faz nada e nao reclama: o e-mail e opcional,
e a falta dele nao pode derrubar o aviso do Telegram.

    EMAIL_REMETENTE   o endereco que envia (ex.: fulano@gmail.com)
    EMAIL_SENHA_APP   a senha de app gerada no Google, 16 letras
    EMAIL_DESTINO     para quem vai; aceita varios separados por virgula

POR QUE SENHA DE APP, E NAO A SENHA NORMAL. O Google nao deixa programa
nenhum entrar com a senha da conta. A senha de app e um acesso separado,
que so serve para enviar e-mail e pode ser revogado sozinho, sem trocar
a senha de verdade nem derrubar o celular.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage

SERVIDOR = "smtp.gmail.com"
PORTA = 465


def configurado():
    """Os tres segredos estao no lugar?"""
    return all(os.environ.get(k) for k in
               ("EMAIL_REMETENTE", "EMAIL_SENHA_APP", "EMAIL_DESTINO"))


def _destinos():
    bruto = os.environ.get("EMAIL_DESTINO", "")
    return [e.strip() for e in bruto.replace(";", ",").split(",") if e.strip()]


def enviar(assunto, texto, anexo=None):
    """Envia e devolve (ok, recado).

    Nunca levanta excecao: o e-mail e o canal secundario, e problema
    nele nao pode interromper o resto da rodada.
    """
    if not configurado():
        return False, "e-mail nao configurado (faltam os segredos)"

    remetente = os.environ["EMAIL_REMETENTE"].strip()
    senha = os.environ["EMAIL_SENHA_APP"].strip().replace(" ", "")
    destinos = _destinos()
    if not destinos:
        return False, "EMAIL_DESTINO esta vazio"

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = "TMT Price Tracker <%s>" % remetente
    msg["To"] = ", ".join(destinos)
    msg.set_content(texto)

    if anexo and os.path.exists(anexo):
        with open(anexo, "rb") as f:
            msg.add_attachment(f.read(), maintype="application",
                               subtype="pdf",
                               filename=os.path.basename(anexo))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SERVIDOR, PORTA, context=ctx, timeout=60) as s:
            s.login(remetente, senha)
            s.send_message(msg)
        return True, "enviado para %s" % ", ".join(destinos)
    except smtplib.SMTPAuthenticationError:
        # o erro mais provavel, e o que tem conserto conhecido
        return False, ("o Google recusou o login. Confira se EMAIL_SENHA_APP "
                       "e uma SENHA DE APP (16 letras) e nao a senha da "
                       "conta, e se ela foi gerada para a conta de "
                       "EMAIL_REMETENTE")
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)
