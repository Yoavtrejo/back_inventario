from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from core.security import INSECURE_SECRET_KEY, check_secret_key, env_list


class SecretKeyCheckTests(SimpleTestCase):
    def test_production_requires_own_secret_key(self) -> None:
        for key in ("", INSECURE_SECRET_KEY):
            with self.assertRaises(ImproperlyConfigured):
                check_secret_key(key, debug=False)

    def test_debug_or_custom_key_is_allowed(self) -> None:
        check_secret_key(INSECURE_SECRET_KEY, debug=True)
        check_secret_key("una-clave-propia-y-larga", debug=False)

    def test_env_list(self) -> None:
        self.assertEqual(env_list(" a, b ,,c "), ["a", "b", "c"])
        self.assertEqual(env_list(""), [])


class ProtectedFileTests(SimpleTestCase):
    def setUp(self) -> None:
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        self.storage = default_storage
        self.pdf = default_storage.save("resources/guia.pdf", ContentFile(b"%PDF-1.4"))
        self.html = default_storage.save("submissions_student/ataque.html", ContentFile(b"<script>alert(1)</script>"))

    def tearDown(self) -> None:
        for name in (self.pdf, self.html):
            self.storage.delete(name)

    def get(self, url):
        return self.client.get(url)

    def test_signed_url_serves_file_inline(self) -> None:
        from core.files import protected_file_url

        response = self.get(protected_file_url(self.pdf))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4")
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response["Content-Disposition"].startswith("inline"))
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_active_content_is_forced_as_attachment(self) -> None:
        from core.files import protected_file_url

        response = self.get(protected_file_url(self.html))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))
        self.assertIn("sandbox", response["Content-Security-Policy"])

    def test_tampered_or_mismatched_links_are_404(self) -> None:
        from core.files import INVALID_LINK_MESSAGE, protected_file_url

        url = protected_file_url(self.pdf)
        prefix, token, filename = url.rsplit("/", 2)
        tampered = f"{prefix}/{token[:-2]}xx/{filename}"
        response = self.get(tampered)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content.decode(), INVALID_LINK_MESSAGE)
        # Un token válido no sirve para pedir otro archivo cambiando el nombre
        self.assertEqual(self.get(f"{prefix}/{token}/otro.pdf").status_code, 404)

    def test_expired_link_is_404(self) -> None:
        import time
        from unittest import mock
        from django.conf import settings
        from core.files import protected_file_url

        url = protected_file_url(self.pdf)
        with mock.patch("django.core.signing.time.time", return_value=time.time() + settings.FILE_URL_MAX_AGE + 5):
            self.assertEqual(self.get(url).status_code, 404)

    def test_media_is_not_served_directly(self) -> None:
        self.assertEqual(self.get(f"/media/{self.pdf}").status_code, 404)
