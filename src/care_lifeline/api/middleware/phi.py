from __future__ import annotations

from care_lifeline.safety.phi import mask

_METHODS_WITH_BODY = ("POST", "PUT", "PATCH")


class PHIMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("method") not in _METHODS_WITH_BODY:
            await self.app(scope, receive, send)
            return

        async def new_receive():
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                if body:
                    try:
                        text = body.decode("utf-8")
                    except UnicodeDecodeError:
                        text = body.decode("utf-8", "replace")
                    message["body"] = mask(text).encode("utf-8")
            return message

        await self.app(scope, new_receive, send)
