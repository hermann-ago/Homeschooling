"""Optional LAN HTTPS listener sharing the existing app, records and workers.

Only the public home certificate is downloadable. Private keys are encrypted;
their passwords use the host's existing DPAPI secret store. Trust installation
is always a separate, explicit action on each client device.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import Context
from datetime import datetime, timedelta, timezone
import ipaddress
import logging
import secrets
import socket

from .network import is_private
from .secrets import read_secret, write_secret

log = logging.getLogger(__name__)
DEFAULT_PORT = 8443


def local_names():
    names = ['localhost', socket.gethostname().lower(), socket.gethostname().lower() + '.local', '127.0.0.1']
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(('10.255.255.255', 1))
            names.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        names += [row[4][0] for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                  if is_private(row[4][0])]
    except OSError:
        pass
    return list(dict.fromkeys(names))


def files(config):
    folder = config.dir / 'https'
    return {name: folder / filename for name, filename in {
        'root': 'home-root.pem', 'download': 'Homeschooling-home-certificate.cer',
        'root_key': 'home-root-key.pem', 'cert': 'server.pem', 'key': 'server-key.pem'}.items()}


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.chmod(0o600)
    temporary.replace(path)


def _password(config, name, create=False):
    path = config.secrets_dir / ('https-' + name + '-password')
    value = read_secret(path) if path.exists() else None
    if value is None:
        if not create:
            raise ValueError('The home HTTPS key password is missing. Restore the local HTTPS files together.')
        value = secrets.token_urlsafe(48).encode()
        write_secret(path, value)
    return value


def ensure_certificate(config, names=None):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    paths = files(config)
    now = datetime.now(timezone.utc)
    names = names or local_names()
    if paths['root'].exists():
        root = x509.load_pem_x509_certificate(paths['root'].read_bytes())
        root_key = serialization.load_pem_private_key(paths['root_key'].read_bytes(), _password(config, 'root'))
        if root_key.public_key().public_numbers() != root.public_key().public_numbers():
            raise ValueError('The home HTTPS certificate and private key do not match. Restore them together.')
        if root.not_valid_after_utc <= now + timedelta(days=30):
            raise ValueError('The home certificate is expiring. Renew it and approve the new certificate on family devices.')
    else:
        if paths['root_key'].exists() or paths['cert'].exists():
            raise ValueError('The home HTTPS certificate files are incomplete. Restore them together; trust was not changed.')
        root_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Homeschooling home network')])
        root = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(root_key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=None, decipher_only=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), critical=False)
            .sign(root_key, hashes.SHA256()))
        _save(paths['root_key'], root_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(_password(config, 'root', create=True))))
        _save(paths['root'], root.public_bytes(serialization.Encoding.PEM))
    _save(paths['download'], root.public_bytes(serialization.Encoding.DER))
    existing = None
    if paths['cert'].exists() and paths['key'].exists():
        existing = x509.load_pem_x509_certificate(paths['cert'].read_bytes())
        sans = existing.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        known = set(sans.get_values_for_type(x509.DNSName)) | {str(v) for v in sans.get_values_for_type(x509.IPAddress)}
        saved_key = serialization.load_pem_private_key(paths['key'].read_bytes(), _password(config, 'server'))
        if (existing.not_valid_after_utc > now + timedelta(days=30) and set(names) <= known
                and saved_key.public_key().public_numbers() == existing.public_key().public_numbers()):
            return paths
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sans = []
    for name in names:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            sans.append(x509.DNSName(name))
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Homeschooling')]))
        .issuer_name(root.subject).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(min(now + timedelta(days=365), root.not_valid_after_utc))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True,
            data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
            encipher_only=None, decipher_only=None), critical=True)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
        .sign(root_key, hashes.SHA256()))
    _save(paths['key'], leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(_password(config, 'server', create=True))))
    _save(paths['cert'], leaf.public_bytes(serialization.Encoding.PEM))
    return paths


def certificate_info(config):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    paths = files(config)
    if not paths['root'].exists() or not paths['cert'].exists():
        return None
    root = x509.load_pem_x509_certificate(paths['root'].read_bytes())
    leaf = x509.load_pem_x509_certificate(paths['cert'].read_bytes())
    sans = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return {'fingerprint': root.fingerprint(hashes.SHA256()).hex().upper(),
        'expires': root.not_valid_after_utc.isoformat(),
        'names': sans.get_values_for_type(x509.DNSName) + [str(v) for v in sans.get_values_for_type(x509.IPAddress)]}


class SecureListener:
    def __init__(self, app, ctx):
        self.app, self.ctx = app, ctx
        self.server = self.task = None
        self.error = None

    @property
    def running(self):
        return bool(self.server and self.server.started and self.task and not self.task.done())

    async def start(self):
        import uvicorn
        if self.running:
            return
        port = self.ctx.config.get('https', {}).get('port', DEFAULT_PORT)
        if not isinstance(port, int) or not 1024 <= port <= 65535 or port == self.ctx.config.get('port'):
            raise ValueError('Choose a separate secure port between 1024 and 65535.')
        paths = ensure_certificate(self.ctx.config)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(('0.0.0.0', port))
            listener.listen(128)
            listener.setblocking(False)
        except OSError:
            listener.close()
            raise ValueError(f'The secure home port {port} is already in use.') from None
        class SharedAppServer(uvicorn.Server):
            @contextmanager
            def capture_signals(self):
                # The main HTTP server owns shutdown and the shared app lifespan.
                yield
        self.server = SharedAppServer(uvicorn.Config(self.app, host='0.0.0.0', port=port, lifespan='off',
            proxy_headers=False, ssl_certfile=str(paths['cert']), ssl_keyfile=str(paths['key']),
            ssl_keyfile_password=_password(self.ctx.config, 'server').decode(), access_log=False))
        async def serve():
            try:
                await self.server.serve(sockets=[listener])
            except SystemExit as exc:
                raise RuntimeError('The secure listener could not start.') from exc
            finally:
                listener.close()
        # Enabling from a request must not pin its test-mode or operation context
        # onto every connection accepted by this long-lived listener.
        self.task = asyncio.create_task(serve(), context=Context())
        for _ in range(250):
            if self.running:
                self.error = None
                return
            if self.task.done():
                await self.task
                raise ValueError('The secure listener stopped during startup.')
            await asyncio.sleep(.02)
        await self.stop()
        raise ValueError('The secure listener did not become ready.')

    async def stop(self):
        if self.task:
            self.server.should_exit = True
            try:
                await asyncio.wait_for(self.task, timeout=10)
            except asyncio.CancelledError:
                self.task.cancel()
                raise
            except Exception:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
            self.task = self.server = None


def manager(app, ctx):
    value = getattr(app.state, 'secure_listener', None)
    if value is None:
        value = app.state.secure_listener = SecureListener(app, ctx)
    return value
