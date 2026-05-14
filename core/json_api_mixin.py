"""
DRF mixin to normalize API payloads to the project JSON contract.

Success: {"success": true, "data": <payload>}
Error: {"success": false, "error_code": str, "message": str}
"""

from __future__ import annotations

from typing import Any, Mapping

from rest_framework.response import Response


def _flatten_validation_message(error_payload: Any) -> str:
    """Build a single human-readable message from DRF validation errors."""
    if isinstance(error_payload, str):
        return error_payload
    if isinstance(error_payload, list):
        parts: list[str] = []
        for item in error_payload:
            parts.append(_flatten_validation_message(item))
        return "; ".join(part for part in parts if part)
    if isinstance(error_payload, Mapping):
        segments: list[str] = []
        for field_name, nested in error_payload.items():
            nested_text = _flatten_validation_message(nested)
            if nested_text:
                segments.append(f"{field_name}: {nested_text}")
        return "; ".join(segments)
    return str(error_payload)


class WrappedStandardApiMixin:
    """
    Wraps successful and typical error DRF responses in the standard envelope.

    Notes:
    - Assumes views return normal DRF Response objects with a `.data` payload.
    - Does not attempt to wrap streaming or file responses.
    """

    def finalize_response(
        self,
        request: Any,
        response: Response,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)

        if getattr(response, "data", None) is None:
            return response

        status_code = int(response.status_code)

        if 200 <= status_code < 300:
            if isinstance(response.data, Mapping) and response.data.get("success") is True:
                return response
            response.data = {"success": True, "data": response.data}
            return response

        error_code = "REQUEST_FAILED"
        message = "The request could not be completed."

        if isinstance(response.data, Mapping):
            if "detail" in response.data and len(response.data) == 1:
                error_code = "API_ERROR"
                message = str(response.data["detail"])
            else:
                error_code = "VALIDATION_ERROR"
                message = _flatten_validation_message(response.data) or message

        response.data = {
            "success": False,
            "error_code": error_code,
            "message": message,
        }
        return response
