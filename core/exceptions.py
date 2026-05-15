"""
Custom Exception Handler
Wraps all DRF exceptions in a consistent JSON response format.

Standard DRF error format (inconsistent):
    {"detail": "Not found."}
    {"field": ["This field is required."]}

Our unified format:
    {
        "error": true,
        "message": "Validation failed.",
        "details": {
            "field_name": ["Error message here."]
        }
    }

This makes frontend error handling predictable across all API calls.
"""
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """
    Call DRF's default handler first, then reshape the response
    into our unified error format.
    """
    response = exception_handler(exc, context)

    if response is not None:
        original_data = response.data

        # Build a unified error payload
        error_payload = {
            "error": True,
            "message": _extract_message(original_data),
            "details": original_data if isinstance(original_data, dict) else {},
        }

        response.data = error_payload

    return response


def _extract_message(data):
    """
    Pull the most useful single-line message out of DRF's error data.

    DRF can return:
        {"detail": "Not found."}
        {"field": ["This field is required."]}
        ["Error message."]
        "Error message."
    """
    if isinstance(data, dict):
        # Prefer the 'detail' key (DRF standard for non-field errors)
        if "detail" in data:
            return str(data["detail"])
        # Otherwise take the first field error
        first_key = next(iter(data), None)
        if first_key:
            value = data[first_key]
            if isinstance(value, list) and value:
                return str(value[0])
            return str(value)
    elif isinstance(data, list) and data:
        return str(data[0])
    elif isinstance(data, str):
        return data

    return "An error occurred."
