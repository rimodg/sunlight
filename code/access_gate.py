"""Optional personal-deployment access gate.

Hosted deployments require a password. Local installations can omit it.
This is browser Basic authentication over the hosting provider's HTTPS,
not institutional SSO, role-based authorization, or an audit identity system.
"""
import base64
import binascii
import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class PersonalAccessGate(BaseHTTPMiddleware):
    def __init__(self, app, username, password):
        super().__init__(app)
        self.username = username.encode('utf-8')
        self.password = password.encode('utf-8')

    async def dispatch(self, request, call_next):
        # Health contains no submitted records and must remain reachable by
        # the hosting platform's readiness checker.
        if request.url.path == '/health':
            return await call_next(request)
        supplied_user = supplied_password = b''
        try:
            scheme, encoded = request.headers.get('authorization', '').split(' ', 1)
            if scheme.lower() == 'basic':
                decoded = base64.b64decode(encoded, validate=True)
                supplied_user, supplied_password = decoded.split(b':', 1)
        except (ValueError, binascii.Error):
            pass
        user_matches = hmac.compare_digest(supplied_user, self.username)
        password_matches = hmac.compare_digest(supplied_password, self.password)
        if not (user_matches and password_matches):
            return Response('Sign in to SUNLIGHT.', status_code=401,
                            headers={'WWW-Authenticate': 'Basic realm="SUNLIGHT", charset="UTF-8"',
                                     'Cache-Control': 'no-store'})
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response


def configure_access_gate(app, environ=None):
    env = os.environ if environ is None else environ
    password = env.get('SUNLIGHT_ACCESS_PASSWORD', '')
    required = env.get('SUNLIGHT_AUTH_REQUIRED', '').lower() in {'1', 'true', 'yes'}
    if required and not password:
        raise RuntimeError('SUNLIGHT_ACCESS_PASSWORD must be set when SUNLIGHT_AUTH_REQUIRED is enabled')
    if password:
        app.add_middleware(PersonalAccessGate,
                           username=env.get('SUNLIGHT_ACCESS_USER') or 'sunlight', password=password)
