from django.http import HttpRequest


def build_message(text: str, msg_type: str) -> dict[str, str]:
    return {"text": text, "type": msg_type}


def pop_messages(request: HttpRequest, key: str = "_bld_msg") -> list:
    return request.session.pop(key, [])
