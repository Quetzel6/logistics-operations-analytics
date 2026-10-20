import io
import json
import socket
import ssl
import unittest
import urllib.error
from assistant import transport_error

class TransportTests(unittest.TestCase):
    def test_quota_machine_code_only(self):
        body={'error':{'code':'insufficient_quota','type':'rate_limit_error','message':'SECRET key customer details'}}
        e=urllib.error.HTTPError('https://api.openai.com/v1/responses',429,'SECRET',{},io.BytesIO(json.dumps(body).encode()))
        self.assertEqual(transport_error(e),'provider_http_429_insufficient_quota')
    def test_unknown_code_redacted(self):
        body={'error':{'code':'SECRET_TOKEN','type':'SECRET_TYPE','message':'SECRET'}}
        e=urllib.error.HTTPError('https://api.openai.com',400,'SECRET',{},io.BytesIO(json.dumps(body).encode()))
        self.assertEqual(transport_error(e),'provider_http_400_unclassified')
    def test_non_json_error(self):
        e=urllib.error.HTTPError('https://api.openai.com',502,'SECRET',{},io.BytesIO(b'<html>SECRET</html>'))
        self.assertEqual(transport_error(e),'provider_http_502_unclassified')
    def test_tls_verification_failure(self):
        e=urllib.error.URLError(ssl.SSLCertVerificationError('SECRET'))
        self.assertEqual(transport_error(e),'provider_tls_certificate_failed')
    def test_timeout_and_dns(self):
        self.assertEqual(transport_error(urllib.error.URLError(TimeoutError('SECRET'))),'provider_timeout')
        self.assertEqual(transport_error(urllib.error.URLError(socket.gaierror('SECRET'))),'provider_dns_failed')

if __name__=='__main__':unittest.main()
