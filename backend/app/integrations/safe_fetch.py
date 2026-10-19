import http.client
import ipaddress
import socket
import ssl
import threading
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from app.config import get_settings
from app.schemas import ToolResult

MAX_BYTES = 512_000
USER_AGENT = "QimaResearchBot/1.0"


def validate_target(url: str, approved: set[str]) -> tuple[str, str, str]:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Only HTTPS URLs without credentials on port 443 are allowed")
    if host not in approved or host in {"localhost", "metadata.google.internal"}:
        raise ValueError("Source domain is not approved")
    answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    addresses = {str(a[4][0]) for a in answers}
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("Private, local, link-local or reserved target blocked")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return host, sorted(addresses)[0], path


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: int):
        self.tls_context = ssl.create_default_context()
        super().__init__(host, timeout=timeout, context=self.tls_context)
        self.address = address

    def connect(self):
        # Pin the checked IP; TLS still validates the original hostname. No second DNS lookup.
        sock = socket.create_connection((self.address, 443), self.timeout)
        self.sock = self.tls_context.wrap_socket(sock, server_hostname=self.host)


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


class SafeHTTPWebsiteFetcher:
    _last: dict[str, float] = {}
    _lock = threading.Lock()

    def _get(self, host: str, address: str, path: str):
        connection = PinnedHTTPSConnection(host, address, get_settings().tool_timeout_seconds)
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,text/plain",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("Response too large")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise ValueError("Compressed content is unsupported")
            return response.status, response.getheader("Content-Type", ""), body
        finally:
            connection.close()

    def fetch(self, url: str) -> ToolResult:
        approved = {x.strip().lower() for x in get_settings().approved_fetch_domains.split(",") if x.strip()}
        host, address, path = validate_target(url, approved)
        with self._lock:
            if time.monotonic() - self._last.get(host, 0) < 2:
                raise ValueError("Source rate limit; retry later")
            self._last[host] = time.monotonic()
        status, _, body = self._get(host, address, "/robots.txt")
        if status == 200:
            robots = RobotFileParser()
            robots.parse(body.decode("utf-8", errors="replace").splitlines())
            if not robots.can_fetch(USER_AGENT, url):
                raise ValueError("Source robots policy disallows fetching")
        elif status != 404:
            raise ValueError("Cannot verify robots policy")
        status, content_type, body = self._get(host, address, path)
        if status != 200:
            raise ValueError("Source failed or redirected; redirects require separately approved URL")
        if content_type.split(";")[0] not in {"text/html", "text/plain"}:
            raise ValueError("Unsupported source content type")
        parser = VisibleText()
        parser.feed(body.decode("utf-8", errors="replace"))
        # Ephemeral model input only; checkpoints retain factual summaries, not complete pages.
        excerpt = " ".join(" ".join(parser.parts).split())[:8000]
        return ToolResult(
            availability="AVAILABLE",
            provider="approved_https",
            items=[{"source_url": url, "untrusted_excerpt": excerpt}],
        )
