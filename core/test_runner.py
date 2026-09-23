"""
Test runner que usa un MEDIA_ROOT temporal para no dejar archivos subidos en media/.
"""

import shutil
import tempfile

from django.conf import settings
from django.test.runner import DiscoverRunner


class TempMediaDiscoverRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._original_media_root = settings.MEDIA_ROOT
        self._temp_media_root = tempfile.mkdtemp(prefix='sidered-test-media-')
        settings.MEDIA_ROOT = self._temp_media_root

    def teardown_test_environment(self, **kwargs):
        settings.MEDIA_ROOT = self._original_media_root
        shutil.rmtree(self._temp_media_root, ignore_errors=True)
        super().teardown_test_environment(**kwargs)
