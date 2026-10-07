"""
Envío de correos desde las vistas sin afectar la respuesta.

send_in_background ejecuta la función de envío después del commit de la transacción y, si
EMAIL_ASYNC está activo, en un hilo aparte: la petición no espera al servidor SMTP (~6 s con
Gmail) y una falla de correo (SMTPException, OSError, timeout) solo se registra en el log.
"""

import logging
import threading

from django.conf import settings
from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)


def _run_safely(func, args, kwargs):
    try:
        func(*args, **kwargs)
    except Exception:
        logger.exception('Falló el envío de correo (%s)', getattr(func, '__name__', func))


def _run_in_thread(func, args, kwargs):
    try:
        _run_safely(func, args, kwargs)
    finally:
        # El hilo abre su propia conexión a la BD si el correo la necesita
        close_old_connections()


def send_in_background(func, *args, **kwargs):
    def start():
        if settings.EMAIL_ASYNC:
            threading.Thread(target=_run_in_thread, args=(func, args, kwargs), daemon=True).start()
        else:
            _run_safely(func, args, kwargs)

    transaction.on_commit(start)
