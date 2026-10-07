import unittest
from unittest.mock import patch
from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.test import Client
from werkzeug.wrappers import Response
from waitress.proxy_headers import proxy_headers_middleware


class ServerProxyTests(unittest.TestCase):
    def test_waitress_preserves_only_configured_proxy_headers(self):
        with patch('app.create_app', return_value=Flask(__name__)):
            from run import server_options
        for hops in (0, 1):
            with self.subTest(hops=hops):
                app = Flask(__name__)

                @app.route('/')
                def index():
                    return {'ip': request.remote_addr, 'secure': request.is_secure,
                            'host': request.host}

                if hops:
                    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops)
                client = Client(proxy_headers_middleware(app, **server_options(
                    {'TRUSTED_PROXIES': hops})), Response)
                result = client.get('/', headers={
                    'X-Forwarded-For': '192.0.2.99, 203.0.113.10',
                    'X-Forwarded-Proto': 'https',
                    'X-Forwarded-Host': 'untrusted.example',
                }, environ_overrides={'REMOTE_ADDR': '10.0.0.1'}).json
                self.assertEqual(result['ip'], '203.0.113.10' if hops else '10.0.0.1')
                self.assertEqual(result['secure'], bool(hops))
                self.assertEqual(result['host'], 'localhost')
