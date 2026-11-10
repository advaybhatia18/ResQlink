import json
import logging
import time
import uuid
from collections import defaultdict, deque


LOGGER = logging.getLogger("resqlink.requests")
WINDOW_SECONDS = 60
MAX_REQUEST_BODY_BYTES = 1_048_576
GENERAL_REQUESTS_PER_MINUTE = 120
AUTH_REQUESTS_PER_MINUTE = 10
AUTH_PATHS = {"/login", "/register", "/password-recovery", "/password-update"}


class RequestControlsMiddleware:
    def __init__(self, app):
        self.app = app
        self._request_times = defaultdict(deque)

    @staticmethod
    async def _respond(send, status_code, detail, request_id, retry_after=None):
        headers = [
            (b"content-type", b"application/json"),
            (b"cache-control", b"no-store"),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
            (b"x-request-id", request_id.encode("ascii")),
        ]
        if retry_after is not None:
            headers.append((b"retry-after", str(retry_after).encode("ascii")))
        body = json.dumps({"detail": detail}).encode("utf-8")
        headers.append((b"content-length", str(len(body)).encode("ascii")))
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": headers,
        })
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _log(request_id, method, path, status_code, started_at):
        LOGGER.info(json.dumps({
            "event": "http_request",
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
        }, separators=(",", ":")))

    def _rate_limit(self, scope, path, now):
        client = scope.get("client")
        client_key = client[0] if client else "unknown"
        is_auth_path = path in AUTH_PATHS
        limit = AUTH_REQUESTS_PER_MINUTE if is_auth_path else GENERAL_REQUESTS_PER_MINUTE
        bucket_name = path if is_auth_path else "general"
        bucket = self._request_times[(client_key, bucket_name)]
        cutoff = now - WINDOW_SECONDS
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return max(1, int(WINDOW_SECONDS - (now - bucket[0])))
        bucket.append(now)

        if len(self._request_times) > 10_000:
            for key, times in list(self._request_times.items()):
                while times and times[0] <= cutoff:
                    times.popleft()
                if not times:
                    self._request_times.pop(key, None)
        return None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        started_at = time.monotonic()
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        status_code = 500

        async def send_with_headers(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"x-request-id", request_id.encode("ascii")),
                ])
                message["headers"] = headers
            await send(message)

        async def reject(status, detail, retry_after=None):
            nonlocal status_code
            status_code = status
            await self._respond(send, status, detail, request_id, retry_after)

        try:
            length_values = [
                value for key, value in scope.get("headers", [])
                if key.lower() == b"content-length"
            ]
            if length_values:
                try:
                    content_length = int(length_values[-1])
                except ValueError:
                    await reject(400, "Invalid Content-Length")
                    return
                if content_length < 0 or content_length > MAX_REQUEST_BODY_BYTES:
                    await reject(413, "Request body is too large")
                    return

            retry_after = self._rate_limit(scope, path, time.monotonic())
            if retry_after is not None:
                await reject(429, "Too many requests. Retry later.", retry_after)
                return

            body = bytearray()
            disconnected = False
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    disconnected = True
                    break
                body.extend(message.get("body", b""))
                if len(body) > MAX_REQUEST_BODY_BYTES:
                    await reject(413, "Request body is too large")
                    return
                if not message.get("more_body", False):
                    break

            if disconnected:
                return

            body_sent = False

            async def replay_body():
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {
                        "type": "http.request",
                        "body": bytes(body),
                        "more_body": False,
                    }
                return {"type": "http.disconnect"}

            await self.app(scope, replay_body, send_with_headers)
        finally:
            self._log(request_id, method, path, status_code, started_at)
