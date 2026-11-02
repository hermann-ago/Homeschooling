import hashlib
import ssl
import asyncio
import json
import socket
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
import httpx
import request_context

from config import HostConfig
from security import https
from security.network import same_origin
from security.secrets import read_secret


def test_certificate_keys_are_encrypted_root_is_stable_and_new_addresses_renew_only_leaf(tmp_path):
    config = HostConfig(tmp_path / 'host')
    paths = https.ensure_certificate(config, ['localhost', '127.0.0.1', '192.168.1.5'])
    before = paths['root'].read_bytes()
    key = paths['key'].read_bytes()
    assert b'ENCRYPTED PRIVATE KEY' in key and b'ENCRYPTED PRIVATE KEY' in paths['root_key'].read_bytes()
    password = read_secret(config.secrets_dir / 'https-server-password')
    private = serialization.load_pem_private_key(key, password)
    cert = x509.load_pem_x509_certificate(paths['cert'].read_bytes())
    assert private.public_key().public_numbers() == cert.public_key().public_numbers()
    ssl.create_default_context(cafile=str(paths['root'])).load_cert_chain(paths['cert'], paths['key'], password.decode())
    info = https.certificate_info(config)
    assert hashlib.sha256(paths['download'].read_bytes()).hexdigest().upper() == info['fingerprint']
    assert https.ensure_certificate(config, ['localhost', '127.0.0.1', '192.168.1.5'])['key'].read_bytes() == key
    https.ensure_certificate(config, ['localhost', '127.0.0.1', '192.168.1.6'])
    assert paths['root'].read_bytes() == before and paths['key'].read_bytes() != key
    assert '192.168.1.6' in https.certificate_info(config)['names']


def test_only_host_can_enable_and_only_public_certificate_is_downloadable(harness, monkeypatch):
    h = harness
    remote = TestClient(h.app, base_url='http://192.168.15.5:8000', client=('192.168.15.9', 1234))
    listener = https.manager(h.app, h.ctx)
    async def start():
        https.ensure_certificate(h.config, ['localhost', '192.168.15.5'])
        listener.server = SimpleNamespace(started=True)
        listener.task = SimpleNamespace(done=lambda: False)
    monkeypatch.setattr(listener, 'start', start)
    assert remote.get('/api/network/camera').json()['running'] is False
    assert remote.get('/api/network/camera/certificate').status_code == 404
    assert remote.post('/api/network/camera/enable').status_code == 403
    assert h.call('POST', '/api/network/camera/enable', role='tutor').status_code == 403
    enabled = h.call('POST', '/api/network/camera/enable')
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()['running'] and h.config.get('https')['enabled']
    details = remote.get('/api/network/camera').json()
    assert details['secure_url'] == 'https://192.168.15.5:8443/'
    certificate = remote.get(details['certificate_download'])
    assert certificate.status_code == 200 and x509.load_der_x509_certificate(certificate.content)
    assert b'PRIVATE KEY' not in certificate.content
    assert remote.get('/api/network/camera/server-key.pem').status_code == 404
    assert https.manager(h.app, h.ctx).ctx is h.ctx


def test_secure_connections_preserve_remote_identity_and_validate_origin_scheme(harness):
    remote = TestClient(harness.app, base_url='https://192.168.15.5:8443', client=('192.168.15.9', 1234))
    assert remote.get('/api/session').json()['host'] is False
    assert remote.put('/api/ai/key', json={'provider': 'inworld', 'key': 'synthetic-key-never-real'}).status_code == 403
    denied = remote.post('/api/children', json={'name': 'Not added'}, headers={'Origin': 'http://192.168.15.5:8443'})
    assert denied.status_code == 403 and 'Changes must come' in denied.text
    allowed = remote.post('/api/children', json={'name': 'Synthetic learner'}, headers={'Origin': 'https://192.168.15.5:8443'})
    assert allowed.status_code == 201, allowed.text
    assert same_origin('https://192.168.15.5:8443', '192.168.15.5:8443', 'https')
    assert not same_origin('http://192.168.15.5:8443', '192.168.15.5:8443', 'https')


def test_real_tls_listener_verifies_certificate_and_does_not_inherit_enabling_request(tmp_path):
    config = HostConfig(tmp_path / 'host')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    config.update(https={'port': port})
    async def app(scope, receive, send):
        current = request_context.current()
        await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'application/json')]})
        await send({'type': 'http.response.body', 'body': json.dumps({'request': current.key if current else None}).encode()})
    listener = https.SecureListener(app, SimpleNamespace(config=config))
    async def verify():
        marker = request_context.begin(request_context.RequestContext('must-not-leak'))
        try:
            await listener.start()
        finally:
            request_context.end(marker)
        try:
            assert listener.running and listener.server.config.lifespan == 'off'
            assert listener.server.config.proxy_headers is False and listener.server.config.app is app
            trust = ssl.create_default_context(cafile=str(https.files(config)['root']))
            async with httpx.AsyncClient(verify=trust, trust_env=False) as client:
                reply = await client.get(f'https://localhost:{port}/')
            assert reply.status_code == 200 and reply.json() == {'request': None}
        finally:
            await listener.stop()
        assert not listener.running
    asyncio.run(verify())
