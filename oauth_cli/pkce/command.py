import hashlib
import json
import logging
import webbrowser
from base64 import urlsafe_b64encode
from http.server import HTTPServer
from random import getrandbits
from sys import exit, stdout
from urllib.parse import urlencode, urlparse
from uuid import uuid4
from oauth_cli.util import get_listen_port_from_url

import click

from oauth_cli.config import setting
from oauth_cli.pkce.callback import PKCEAccessTokenCallbackHandler


class PKCEGetIdTokenCommand(object):
    def __init__(self):
        self.client_id = setting.CLIENT_ID
        self.scope = "openid profile"
        self.tokens = {}
        self.state = str(uuid4())
        self.verifier = self.b64encode(bytearray(getrandbits(8) for _ in range(32)))
        self.challenge = self.b64encode(hashlib.sha256(self.verifier.encode('ascii')).digest())
        self.callback_url = setting.attributes.get('pkce_callback_url',
                                                   f'http://localhost:{setting.LISTEN_PORT}/callback')

    @property
    def token_url(self):
        return f'{setting.IDP_URL}/oauth/token'

    @property
    def authorize_url(self):
        return f'{setting.IDP_URL}/authorize'

    @property
    def listen_port(self):
        return get_listen_port_from_url(self.callback_url)

    def set_tokens(self, tokens):
        self.tokens = tokens

    def accept_access_code(self):
        PKCEAccessTokenCallbackHandler.client_id = setting.CLIENT_ID
        PKCEAccessTokenCallbackHandler.token_url = self.token_url
        PKCEAccessTokenCallbackHandler.callback_url = self.callback_url
        PKCEAccessTokenCallbackHandler.verifier = self.verifier
        PKCEAccessTokenCallbackHandler.state = self.state
        PKCEAccessTokenCallbackHandler.handler = (lambda tokens: self.set_tokens(tokens))
        httpd = HTTPServer(('0.0.0.0', self.listen_port), PKCEAccessTokenCallbackHandler)
        try:
            httpd.handle_request()
        finally:
            httpd.server_close()

    @property
    def query_parameters(self):
        return {
            "response_type": "code",
            "scope": self.scope,
            "client_id": self.client_id,
            "code_challenge": self.challenge,
            "code_challenge_method": "S256",
            "redirect_uri": self.callback_url,
            "state": self.state
        }

    @property
    def url(self):
        return self.authorize_url + '?' + urlencode(self.query_parameters);

    def request_authorization(self):
        logging.debug('url = %s', self.url)
        webbrowser.open(self.url)
        self.accept_access_code()

    @staticmethod
    def b64encode(s):
        return urlsafe_b64encode(s).decode('ascii').strip("=")

    def run(self):
        self.request_authorization()
        if self.tokens:
            json.dump(self.tokens, stdout)
        else:
            logging.error('no token retrieved')
            exit(1)


class PKCEGetAccessTokenCommand(PKCEGetIdTokenCommand):
    def __init__(self):
        super(PKCEGetAccessTokenCommand, self).__init__()
        self.audience = setting.attributes.get('audience')
        self.scope = setting.attributes.get('scope', 'profile')

    @property
    def query_parameters(self):
        result = super(PKCEGetAccessTokenCommand, self).query_parameters
        result.update({"audience": self.audience, "scope": self.scope})
        return result

    def run(self):
        if not self.audience:
            logging.error('audience is required')
            exit(1)
        super(PKCEGetAccessTokenCommand, self).run()


@click.command('get-access-jwt', help='get an access JWT')
@click.option('--audience', help='to obtain an access token for. default from ~/.oauth-cli.ini')
@click.option('--scope', help='of the access token')
def get_access_token(audience, scope):
    cmd = PKCEGetAccessTokenCommand()
    if audience:
        cmd.audience = audience
    if scope:
        cmd.scope = scope
    cmd.run()


@click.command('get-id-jwt', help='get an id JWT')
def get_id_token():
    cmd = PKCEGetIdTokenCommand()
    cmd.run()
