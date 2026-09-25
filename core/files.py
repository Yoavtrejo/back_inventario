"""
Descarga protegida de archivos subidos (MEDIA_ROOT ya no se sirve públicamente).

Los serializers devuelven, solo a quien puede ver el objeto, una URL firmada y temporal:
/api/files/<token>/<nombre_archivo>. El token firmado es la autorización, así que el enlace
funciona en <a href> e <img src> sin cabecera Authorization.
"""

import mimetypes
import os

from django.conf import settings
from django.core import signing
from django.core.files.storage import default_storage
from django.db import models
from django.http import FileResponse, HttpResponseNotFound
from django.urls import reverse
from rest_framework import serializers

SIGNING_SALT = 'sidered.protected-file'
INVALID_LINK_MESSAGE = 'El enlace del archivo no es válido o ya venció. Recarga la página.'
# Tipos que se muestran en el navegador; el resto se descarga como adjunto (evita HTML/SVG activos)
INLINE_CONTENT_TYPES = {'application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'image/webp'}


def protected_file_url(file_name, request=None):
    token = signing.dumps(file_name, salt=SIGNING_SALT, compress=True)
    url = reverse('protected-file', kwargs={'token': token, 'filename': os.path.basename(file_name)})
    return request.build_absolute_uri(url) if request else url


class ProtectedFileRepresentationMixin:
    def to_representation(self, value):
        if not value:
            return None
        return protected_file_url(value.name, self.context.get('request'))


class ProtectedFileField(ProtectedFileRepresentationMixin, serializers.FileField):
    pass


class ProtectedImageField(ProtectedFileRepresentationMixin, serializers.ImageField):
    pass


class ProtectedFilesMixin:
    """Para ModelSerializers: sus FileField/ImageField se exponen como URLs firmadas."""
    serializer_field_mapping = {
        **serializers.ModelSerializer.serializer_field_mapping,
        models.FileField: ProtectedFileField,
        models.ImageField: ProtectedImageField,
    }


def protected_file(request, token, filename):
    try:
        file_name = signing.loads(token, salt=SIGNING_SALT, max_age=settings.FILE_URL_MAX_AGE)
    except signing.BadSignature:  # incluye SignatureExpired
        return _not_found()
    if os.path.basename(file_name) != filename or not default_storage.exists(file_name):
        return _not_found()

    content_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
    response = FileResponse(
        default_storage.open(file_name, 'rb'),
        content_type=content_type,
        as_attachment=content_type not in INLINE_CONTENT_TYPES,
        filename=filename,
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    response['Cache-Control'] = 'private, max-age=300'
    return response


def _not_found():
    return HttpResponseNotFound(INVALID_LINK_MESSAGE, content_type='text/plain; charset=utf-8')
