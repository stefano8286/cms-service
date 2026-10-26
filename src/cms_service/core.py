"""Resolve IANA service names to canonical ports and protocols.

This module reads the host operating system's services file, which is the
same data the IANA publishes, and builds an in-memory lookup table. Each
service name maps to one or more records giving the port and protocol.

The services file can define the same name for multiple protocols (e.g.
``http 80/tcp`` and ``http 80/udp``) or different ports for different
protocols. ``resolve`` returns the first record encountered for the
requested protocol; if no protocol is specified, the first record for
the name (in file order) is returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence


DEFAULT_SERVICES_PATHS: Sequence[str] = (
    "/etc/services",
    "/usr/share/services/services",
    "/usr/local/etc/services",
)


@dataclass(frozen=True)
class ResolutionResult:
    """A single resolved record.

    Attributes:
        name: the service name as it appears in the services file.
        port: the canonical IANA port number (1-65535).
        protocol: the transport protocol (``tcp``, ``udp``, etc.).
    """

    name: str
    port: int
    protocol: str


class ResolverError(Exception):
    """Raised when the services file is missing or unparseable."""


class ServiceResolver:
    """Resolve IANA service names to ports and protocols.

    Args:
        path: path to a services file. When omitted, the resolver checks
            ``DEFAULT_SERVICES_PATHS`` and uses the first that exists. A
            missing file or a line that fails to parse raises
            ``ResolverError``.

    The file is read once at construction; subsequent calls to ``resolve``
    are cheap in-memory lookups. This is deliberate: re-reading on every
    lookup would be wasteful for a data source that never changes during
    a process lifetime.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        resolved_path = self._locate_file(path)
        self._records: List[ResolutionResult] = self._parse_file(resolved_path)

    @staticmethod
    def _locate_file(path: Optional[str]) -> Path:
        if path is not None:
            p = Path(path)
            if not p.is_file():
                raise ResolverError(f"services file not found: {path}")
            return p
        for candidate in DEFAULT_SERVICES_PATHS:
            p = Path(candidate)
            if p.is_file():
                return p
        raise ResolverError(
            "no services file found at any default path: "
            + ", ".join(DEFAULT_SERVICES_PATHS)
        )

    @staticmethod
    def _parse_file(path: Path) -> List[ResolutionResult]:
        records: List[ResolutionResult] = []
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line_no, raw in enumerate(fh, 1):
                    stripped = raw.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    comment_idx = raw.find("#")
                    if comment_idx != -1:
                        line = raw[:comment_idx].strip()
                    else:
                        line = stripped
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) < 2:
                        raise ResolverError(
                            f"malformed line {line_no} in {path}: {raw.strip()}"
                        )
                    name = parts[0]
                    port_protocol = parts[1]
                    if "/" not in port_protocol:
                        raise ResolverError(
                            f"malformed line {line_no} in {path}: "
                            f"missing protocol delimiter in {port_protocol!r}"
                        )
                    port_str, _, protocol = port_protocol.partition("/")
                    try:
                        port = int(port_str)
                    except ValueError:
                        raise ResolverError(
                            f"malformed line {line_no} in {path}: "
                            f"invalid port {port_str!r}"
                        )
                    if not (0 <= port <= 65535):
                        raise ResolverError(
                            f"malformed line {line_no} in {path}: "
                            f"port out of range: {port}"
                        )
                    records.append(
                        ResolutionResult(name=name, port=port, protocol=protocol)
                    )
        except OSError as exc:
            raise ResolverError(f"cannot read services file {path}: {exc}") from exc
        return records

    def resolve(
        self, name: str, protocol: Optional[str] = None
    ) -> Optional[ResolutionResult]:
        """Look up a service name.

        Args:
            name: the service name, e.g. ``"http"``. The lookup is
                case-insensitive, matching the convention that service
                names in the services file are lower-case and callers
                may not know that.
            protocol: optional protocol filter (``"tcp"``, ``"udp"``).
                Also case-insensitive.

        Returns:
            ``ResolutionResult`` for the first match, or ``None`` if the
            name (and protocol, if given) is not found.
        """
        needle = name.lower()
        proto = protocol.lower() if protocol else None
        for rec in self._records:
            if rec.name.lower() != needle:
                continue
            if proto is not None and rec.protocol.lower() != proto:
                continue
            return rec
        return None

    def resolve_all(
        self, name: str, protocol: Optional[str] = None
    ) -> List[ResolutionResult]:
        """Return every record matching ``name`` (and optionally protocol).

        A name can appear multiple times in the services file. This
        returns them all in file order.
        """
        needle = name.lower()
        proto = protocol.lower() if protocol else None
        return [
            rec
            for rec in self._records
            if rec.name.lower() == needle
            and (proto is None or rec.protocol.lower() == proto)
        ]
