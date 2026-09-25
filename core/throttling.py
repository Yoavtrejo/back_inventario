"""
Límites de intentos para el login: por IP (holgado, en la escuela muchos alumnos comparten IP)
y por usuario intentado (frena la fuerza bruta contra una cuenta aunque cambie de IP).
"""

import hashlib

from rest_framework.throttling import SimpleRateThrottle


class LoginIPThrottle(SimpleRateThrottle):
    scope = 'login_ip'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class LoginUsernameThrottle(SimpleRateThrottle):
    scope = 'login_username'

    def get_cache_key(self, request, view):
        username = str(request.data.get('username') or '').strip().lower()
        if not username:
            return None
        ident = hashlib.sha256(username.encode()).hexdigest()
        return self.cache_format % {'scope': self.scope, 'ident': ident}
