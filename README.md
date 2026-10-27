# cms-service

Resolves IANA service names to their canonical port numbers and protocols using the host operating system's built-in `services` file — no bundled data, no network calls.

```python
from cms_service import ServiceResolver

resolver = ServiceResolver()

rec = resolver.resolve("http", "tcp")
print(rec.port)      # 80
print(rec.protocol)  # tcp

# without a protocol, the first match (in file order) is returned
rec = resolver.resolve("http")
print(rec.port)  # 80

# every record for a name
for r in resolver.resolve_all("domain"):
    print(r.name, r.port, r.protocol)
```

## Exports

- `ServiceResolver(path: str | None = None)` — constructor. When `path` is `None`, checks `/etc/services`, `/usr/share/services/services`, and `/usr/local/etc/services` in order, using the first that exists.
- `ServiceResolver.resolve(name: str, protocol: str | None = None) -> ResolutionResult | None` — returns the first matching record, or `None`.
- `ServiceResolver.resolve_all(name: str, protocol: str | None = None) -> list[ResolutionResult]` — returns every matching record in file order.
- `ResolutionResult` — frozen dataclass with `name: str`, `port: int`, `protocol: str`.
- `ResolverError` — raised when the services file is missing or malformed.

## Why

The problem is simple: given a string like `"ssh"`, what port does it use? You can hardcode 22, but that breaks for less common services and rots if assignments change. The host's `services` file is the local source of truth, maintained by the OS, reflecting IANA assignments. Reading it at construction keeps lookups fast and avoids repeated disk I/O.

The trade-off: the data is only as good as the host file. A minimal container may ship a stripped `/etc/services` missing entries you expect. If the file is absent entirely, the constructor raises `ResolverError` rather than silently returning wrong answers.

## Edge cases

A service name can appear on multiple lines for different protocols (`http` is defined for both `tcp` and `udp`, often at the same port). `resolve` without a protocol returns whichever appears first in the file — this is deterministic but depends on file ordering. If you need all records, use `resolve_all`. Service names and protocols are compared case-insensitively; the returned record preserves the original casing from the file. Port 0 is permitted (it is a valid IANA reserved value); ports outside 0–65535 cause `ResolverError`.
