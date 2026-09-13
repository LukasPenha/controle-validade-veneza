"""Gmail HTTPS transport, limited to the gmail.send OAuth scope."""
import base64
import requests
from flask import current_app


def send_gmail(message):
    config = current_app.config
    try:
        token = requests.post('https://oauth2.googleapis.com/token', data={
            'client_id': config['GMAIL_CLIENT_ID'], 'client_secret': config['GMAIL_CLIENT_SECRET'],
            'refresh_token': config['GMAIL_REFRESH_TOKEN'], 'grant_type':'refresh_token'},
            timeout=(5,15), allow_redirects=False)
        if token.status_code != 200:
            raise ValueError('Não foi possível autorizar o Gmail.')
        access = token.json().get('access_token')
        if not access:
            raise ValueError('Resposta de autorização inválida.')
    except requests.RequestException:
        # No message was submitted yet: safe to retry.
        raise ValueError('Autorização do Gmail indisponível.') from None
    try:
        response = requests.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
            headers={'Authorization':'Bearer '+access},
            json={'raw':base64.urlsafe_b64encode(message.as_bytes()).decode('ascii')},
            timeout=(5,20), allow_redirects=False)
    except requests.RequestException:
        raise TimeoutError('Entrega não confirmada pelo Gmail.') from None
    if response.status_code >= 500:
        raise TimeoutError('Entrega não confirmada pelo Gmail.')
    if response.status_code != 200:
        raise ValueError('Gmail recusou o envio.')
    try:
        if not response.json().get('id'):
            raise TimeoutError('Gmail retornou confirmação inválida.')
    except ValueError:
        raise TimeoutError('Gmail retornou confirmação inválida.') from None
