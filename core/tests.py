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
