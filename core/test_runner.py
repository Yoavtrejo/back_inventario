"""
Test runner que usa un MEDIA_ROOT temporal para no dejar archivos subidos en media/
y sube los límites globales anon/user para que la suite completa no choque con ellos.
"""

import shutil
import tempfile

from django.conf import settings
from django.test.runner import DiscoverRunner
from rest_framework.settings import api_settings


class TempMediaDiscoverRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._original_media_root = settings.MEDIA_ROOT
        self._temp_media_root = tempfile.mkdtemp(prefix='sidered-test-media-')
        settings.MEDIA_ROOT = self._temp_media_root
        # Los tests de límites específicos (login, recuperación) usan sus propios scopes
        rates = api_settings.DEFAULT_THROTTLE_RATES
        self._original_rates = {scope: rates[scope] for scope in ('anon', 'user')}
        rates.update({'anon': '100000/minute', 'user': '100000/minute'})

    def teardown_test_environment(self, **kwargs):
        settings.MEDIA_ROOT = self._original_media_root
        api_settings.DEFAULT_THROTTLE_RATES.update(self._original_rates)
        shutil.rmtree(self._temp_media_root, ignore_errors=True)
        super().teardown_test_environment(**kwargs)
