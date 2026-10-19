# -*- coding: utf-8 -*-
"""Manda a mensagem do dia por e-mail, com o relatorio em anexo.

POR QUE EXISTE. O Telegram chega no telefone; o e-mail chega onde o
trabalho acontece, da para encaminhar para outra pessoa e fica
arquivado e pesquisavel sem depender de rolar conversa.

E O MESMO CONTEUDO. O texto e o PDF sao os que o robo ja montou para o
Telegram - nao ha um levantamento proprio aqui. Se os dois canais
tivessem fontes separadas, um dia iam discordar.

DOIS CAMINHOS, E ELE ESCOLHE SOZINHO.

    Resend   uma chave de API, e so. Nao depende de conta Google, de
             verificacao em duas etapas nem de senha de app. O endereco
             que envia e generico, mas o NOME que aparece na caixa de
             entrada e "TMT Price Tracker".

    Gmail    manda do proprio endereco, com cara institucional, mas
             exige verificacao em duas etapas ligada e uma senha de app
             gerada na conta - e o Google bloqueia essa pagina em conta
             que ele nao reconhece no navegador.

O Resend vem primeiro porque foi o que funcionou. Se um dia a senha de
app existir, basta gravar os segredos do Gmail e ele passa a usar esse
caminho, sem tocar em codigo.

OPCIONAL POR CONSTRUCAO. Sem segredo nenhum, este modulo nao faz nada e
nao reclama: o e-mail e o canal secundario, e a falta dele nao pode
derrubar o aviso do Telegram.
"""
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

SMTP_SERVIDOR = "smtp.gmail.com"
SMTP_PORTA = 465
RESEND_API = "https://api.resend.com/emails"

# O nome que aparece na caixa de entrada. O endereco pode ser generico;
# o nome e o que o leitor ve primeiro.
REMETENTE_NOME = "TMT Price Tracker"

# Endereco que o Resend libera sem dominio proprio. Com dominio
# verificado, basta gravar RESEND_REMETENTE e ele usa o seu.
RESEND_PADRAO = "onboarding@resend.dev"


def _destinos():
    bruto = os.environ.get("EMAIL_DESTINO", "")
    return [e.strip() for e in bruto.replace(";", ",").split(",") if e.strip()]


def caminho():
    """Qual via esta configurada: 'resend', 'gmail' ou None."""
    if not _destinos():
        return None
    if os.environ.get("RESEND_API_KEY"):
        return "resend"
    if os.environ.get("EMAIL_REMETENTE") and os.environ.get("EMAIL_SENHA_APP"):
        return "gmail"
    return None


def configurado():
    return caminho() is not None


def _por_resend(assunto, texto, anexo):
    import base64

    chave = os.environ["RESEND_API_KEY"].strip()
    de = os.environ.get("RESEND_REMETENTE", "").strip() or RESEND_PADRAO
    corpo = {
        "from": "%s <%s>" % (REMETENTE_NOME, de),
        "to": _destinos(),
        "subject": assunto,
        "text": texto,
    }
    if anexo and os.path.exists(anexo):
        with open(anexo, "rb") as f:
            corpo["attachments"] = [{
                "filename": os.path.basename(anexo),
                "content": base64.b64encode(f.read()).decode(),
            }]

    req = urllib.request.Request(
        RESEND_API, data=json.dumps(corpo).encode("utf-8"), method="POST")
    req.add_header("Authorization", "Bearer " + chave)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
        return True, "enviado por Resend para %s" % ", ".join(_destinos())
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")[:200]
        if e.code == 403 and "testing emails" in detalhe:
            # a limitacao do plano sem dominio, que tem conserto conhecido
            return False, ("o Resend so entrega no endereco da propria conta "
                           "enquanto nao houver dominio verificado. Troque o "
                           "EMAIL_DESTINO para o e-mail usado no cadastro, ou "
                           "verifique um dominio em resend.com/domains")
        return False, "Resend HTTP %s: %s" % (e.code, detalhe)
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


def _por_gmail(assunto, texto, anexo):
    remetente = os.environ["EMAIL_REMETENTE"].strip()
    senha = os.environ["EMAIL_SENHA_APP"].strip().replace(" ", "")

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = "%s <%s>" % (REMETENTE_NOME, remetente)
    msg["To"] = ", ".join(_destinos())
    msg.set_content(texto)
    if anexo and os.path.exists(anexo):
        with open(anexo, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype="pdf",
                               filename=os.path.basename(anexo))
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVIDOR, SMTP_PORTA, context=ctx,
                              timeout=60) as s:
            s.login(remetente, senha)
            s.send_message(msg)
        return True, "enviado por Gmail para %s" % ", ".join(_destinos())
    except smtplib.SMTPAuthenticationError:
        return False, ("o Google recusou o login. EMAIL_SENHA_APP tem de ser "
                       "uma SENHA DE APP de 16 letras, gerada na conta de "
                       "EMAIL_REMETENTE - nao a senha da conta")
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


def enviar(assunto, texto, anexo=None):
    """Envia e devolve (ok, recado). Nunca levanta excecao."""
    via = caminho()
    if via is None:
        return False, "e-mail nao configurado"
    try:
        return _por_resend(assunto, texto, anexo) if via == "resend" \
            else _por_gmail(assunto, texto, anexo)
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)
