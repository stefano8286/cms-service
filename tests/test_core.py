import tempfile
import unittest
from pathlib import Path

from cms_service.core import (
    ResolutionResult,
    ResolverError,
    ServiceResolver,
)


SAMPLE_SERVICES = """# Sample services file for testing
tcpmux          1/tcp                           # TCP port service multiplexer
compressnet     2/tcp                           # Management Utility
http            80/tcp    www http www-http    # World Wide Web
http            80/udp    www http www-http    # World Wide Web
ssh             22/tcp                         # SSH Remote Login Protocol
domain          53/tcp    nameserver dns
domain          53/udp    nameserver dns
imap            143/tcp   imap2
sftp            115/tcp
quasar-server   7777/tcp
"""


class TestParsing(unittest.TestCase):
    def _write_tmp(self, content: str) -> str:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix="_services", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.flush()
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def test_loads_from_explicit_path(self) -> None:
        path = self._write_tmp(SAMPLE_SERVICES)
        resolver = ServiceResolver(path=path)
        rec = resolver.resolve("http", "tcp")
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.name, "http")
        self.assertEqual(rec.port, 80)
        self.assertEqual(rec.protocol, "tcp")

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(ResolverError):
            ServiceResolver(path="/nonexistent/path/to/services")


class TestResolve(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix="_services", delete=False, encoding="utf-8"
        )
        tmp.write(SAMPLE_SERVICES)
        tmp.flush()
        tmp.close()
        cls.path = tmp.name
        cls.resolver = ServiceResolver(path=cls.path)

    @classmethod
    def tearDownClass(cls) -> None:
        Path(cls.path).unlink(missing_ok=True)

    def test_tcp_and_udp_same_port(self) -> None:
        tcp = self.resolver.resolve("http", "tcp")
        self.assertIsNotNone(tcp)
        assert tcp is not None
        self.assertEqual(tcp.port, 80)
        self.assertEqual(tcp.protocol, "tcp")

        udp = self.resolver.resolve("http", "udp")
        self.assertIsNotNone(udp)
        assert udp is not None
        self.assertEqual(udp.port, 80)
        self.assertEqual(udp.protocol, "udp")

    def test_no_protocol_returns_first_match(self) -> None:
        # http appears as tcp then udp in the file; first is tcp
        rec = self.resolver.resolve("http")
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.protocol, "tcp")

    def test_case_insensitive_name(self) -> None:
        rec = self.resolver.resolve("HTTP", "tcp")
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.port, 80)

    def test_case_insensitive_protocol(self) -> None:
        rec = self.resolver.resolve("ssh", "TCP")
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.port, 22)

    def test_unknown_name_returns_none(self) -> None:
        self.assertIsNone(self.resolver.resolve("nonexistent-service"))

    def test_name_valid_protocol_not_found_returns_none(self) -> None:
        self.assertIsNone(self.resolver.resolve("ssh", "udp"))

    def test_high_port(self) -> None:
        rec = self.resolver.resolve("quasar-server", "tcp")
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.port, 7777)


class TestResolveAll(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix="_services", delete=False, encoding="utf-8"
        )
        tmp.write(SAMPLE_SERVICES)
        tmp.flush()
        tmp.close()
        cls.path = tmp.name
        cls.resolver = ServiceResolver(path=cls.path)

    @classmethod
    def tearDownClass(cls) -> None:
        Path(cls.path).unlink(missing_ok=True)

    def test_returns_multiple_protocols(self) -> None:
        recs = self.resolver.resolve_all("http")
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0].protocol, "tcp")
        self.assertEqual(recs[1].protocol, "udp")

    def test_filter_by_protocol(self) -> None:
        recs = self.resolver.resolve_all("domain", "udp")
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].port, 53)
        self.assertEqual(recs[0].protocol, "udp")

    def test_single_entry_returns_list_of_one(self) -> None:
        recs = self.resolver.resolve_all("ssh")
        self.assertEqual(len(recs), 1)

    def test_unknown_returns_empty_list(self) -> None:
        recs = self.resolver.resolve_all("nope")
        self.assertEqual(recs, [])


class TestEdgeCases(unittest.TestCase):
    def _write_tmp(self, content: str) -> str:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix="_services", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.flush()
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def test_blank_lines_and_comments_ignored(self) -> None:
        content = "\n\n# just a comment\n   # indented comment\nhttp 80/tcp\n"
        resolver = ServiceResolver(path=self._write_tmp(content))
        rec = resolver.resolve("http")
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.port, 80)

    def test_inline_comment_stripped(self) -> None:
        content = "http 80/tcp    # inline comment\n"
        resolver = ServiceResolver(path=self._write_tmp(content))
        rec = resolver.resolve("http")
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.port, 80)

    def test_aliases_after_port_are_ignored(self) -> None:
        # http has aliases www http www-http; only the primary name is stored
        content = "http 80/tcp www http www-http\n"
        resolver = ServiceResolver(path=self._write_tmp(content))
        rec = resolver.resolve("http")
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.name, "http")
        self.assertEqual(rec.port, 80)

    def test_malformed_no_protocol_raises(self) -> None:
        content = "badname 80\n"
        with self.assertRaises(ResolverError):
            ServiceResolver(path=self._write_tmp(content))

    def test_malformed_invalid_port_raises(self) -> None:
        content = "badname xx/tcp\n"
        with self.assertRaises(ResolverError):
            ServiceResolver(path=self._write_tmp(content))

    def test_port_out_of_range_raises(self) -> None:
        content = "badname 99999/tcp\n"
        with self.assertRaises(ResolverError):
            ServiceResolver(path=self._write_tmp(content))

    def test_resolution_result_is_frozen(self) -> None:
        content = "http 80/tcp\n"
        resolver = ServiceResolver(path=self._write_tmp(content))
        rec = resolver.resolve("http")
        assert rec is not None
        with self.assertRaises(Exception):
            rec.port = 81  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
