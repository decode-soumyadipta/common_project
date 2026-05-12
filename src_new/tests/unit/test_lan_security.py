"""Unit tests for LAN security middleware.

This module provides unit tests for the LAN security middleware that enforces
IP-based access control for the air-gapped government LAN deployment.

Requirements: 16.6, 19.2
"""
from __future__ import annotations

import logging
from typing import Callable
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from src_new.shared.auth.lan_security import (
    LANSecurityMiddleware,
    _extract_client_ip,
    _is_ip_allowed,
    _parse_allowed_hosts,
    get_bind_host,
)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestParseAllowedHosts:
    """Test suite for _parse_allowed_hosts helper function."""

    def test_parse_single_ip(self) -> None:
        """Test parsing a single IP address."""
        result = _parse_allowed_hosts("192.168.1.10")
        assert result == ["192.168.1.10"]

    def test_parse_multiple_ips(self) -> None:
        """Test parsing multiple comma-separated IP addresses."""
        result = _parse_allowed_hosts("192.168.1.10,10.0.0.5,172.16.0.1")
        assert result == ["192.168.1.10", "10.0.0.5", "172.16.0.1"]

    def test_parse_with_whitespace(self) -> None:
        """Test parsing with extra whitespace around IPs."""
        result = _parse_allowed_hosts("  192.168.1.10  ,  10.0.0.5  ")
        assert result == ["192.168.1.10", "10.0.0.5"]

    def test_parse_cidr_ranges(self) -> None:
        """Test parsing CIDR network ranges."""
        result = _parse_allowed_hosts("192.168.1.0/24,10.0.0.0/8")
        assert result == ["192.168.1.0/24", "10.0.0.0/8"]

    def test_parse_ipv6_addresses(self) -> None:
        """Test parsing IPv6 addresses."""
        result = _parse_allowed_hosts("::1,fe80::1")
        assert result == ["::1", "fe80::1"]

    def test_parse_empty_string_fallback_to_localhost(self, caplog) -> None:
        """Test that empty string falls back to localhost-only.
        
        **Validates: Requirements 16.6, 19.2**
        Missing ALLOWED_HOSTS env var should fall back to localhost-only access.
        """
        with caplog.at_level(logging.WARNING):
            result = _parse_allowed_hosts("")
        
        assert result == ["127.0.0.1", "::1"]
        assert "localhost-only" in caplog.text
        assert "ALLOWED_HOSTS is not configured" in caplog.text

    def test_parse_whitespace_only_fallback_to_localhost(self, caplog) -> None:
        """Test that whitespace-only string falls back to localhost-only.
        
        **Validates: Requirements 16.6, 19.2**
        """
        with caplog.at_level(logging.WARNING):
            result = _parse_allowed_hosts("   ,  ,  ")
        
        assert result == ["127.0.0.1", "::1"]
        assert "localhost-only" in caplog.text

    def test_parse_mixed_ipv4_ipv6_cidr(self) -> None:
        """Test parsing mixed IPv4, IPv6, and CIDR ranges."""
        result = _parse_allowed_hosts("192.168.1.10,::1,10.0.0.0/8,fe80::/10")
        assert result == ["192.168.1.10", "::1", "10.0.0.0/8", "fe80::/10"]


class TestIsIpAllowed:
    """Test suite for _is_ip_allowed helper function."""

    def test_allowed_single_ipv4_match(self) -> None:
        """Test that an allowed IPv4 address passes.
        
        **Validates: Requirements 16.6, 19.2**
        Allowed IP should pass through the middleware.
        """
        allowed = ["192.168.1.10"]
        assert _is_ip_allowed("192.168.1.10", allowed) is True

    def test_allowed_single_ipv4_no_match(self) -> None:
        """Test that a disallowed IPv4 address is blocked.
        
        **Validates: Requirements 16.6, 19.2**
        Blocked IP should return 403 Forbidden.
        """
        allowed = ["192.168.1.10"]
        assert _is_ip_allowed("192.168.1.20", allowed) is False

    def test_allowed_cidr_range_match(self) -> None:
        """Test that an IP within a CIDR range is allowed."""
        allowed = ["192.168.1.0/24"]
        assert _is_ip_allowed("192.168.1.50", allowed) is True
        assert _is_ip_allowed("192.168.1.1", allowed) is True
        assert _is_ip_allowed("192.168.1.254", allowed) is True

    def test_allowed_cidr_range_no_match(self) -> None:
        """Test that an IP outside a CIDR range is blocked."""
        allowed = ["192.168.1.0/24"]
        assert _is_ip_allowed("192.168.2.50", allowed) is False
        assert _is_ip_allowed("10.0.0.1", allowed) is False

    def test_allowed_multiple_ranges(self) -> None:
        """Test matching against multiple CIDR ranges."""
        allowed = ["192.168.1.0/24", "10.0.0.0/8", "172.16.0.0/12"]
        assert _is_ip_allowed("192.168.1.100", allowed) is True
        assert _is_ip_allowed("10.5.10.20", allowed) is True
        assert _is_ip_allowed("172.20.0.1", allowed) is True
        assert _is_ip_allowed("8.8.8.8", allowed) is False

    def test_allowed_ipv6_match(self) -> None:
        """Test that an allowed IPv6 address passes."""
        allowed = ["::1", "fe80::1"]
        assert _is_ip_allowed("::1", allowed) is True
        assert _is_ip_allowed("fe80::1", allowed) is True

    def test_allowed_ipv6_no_match(self) -> None:
        """Test that a disallowed IPv6 address is blocked."""
        allowed = ["::1"]
        assert _is_ip_allowed("fe80::1", allowed) is False

    def test_allowed_ipv6_cidr_range(self) -> None:
        """Test IPv6 CIDR range matching."""
        allowed = ["fe80::/10"]
        assert _is_ip_allowed("fe80::1", allowed) is True
        assert _is_ip_allowed("fe80::abcd:1234", allowed) is True
        assert _is_ip_allowed("::1", allowed) is False

    def test_invalid_client_ip_format(self, caplog) -> None:
        """Test that invalid IP format is rejected."""
        allowed = ["192.168.1.0/24"]
        with caplog.at_level(logging.WARNING):
            result = _is_ip_allowed("not-an-ip", allowed)
        
        assert result is False
        assert "Could not parse client IP address" in caplog.text

    def test_invalid_allowed_hosts_entry_skipped(self, caplog) -> None:
        """Test that invalid entries in allowed list are skipped."""
        allowed = ["192.168.1.10", "invalid-entry", "10.0.0.0/8"]
        with caplog.at_level(logging.DEBUG):
            # Should match the valid entries
            assert _is_ip_allowed("192.168.1.10", allowed) is True
            assert _is_ip_allowed("10.0.0.5", allowed) is True
            # Should not match invalid entry
            assert _is_ip_allowed("invalid-entry", allowed) is False

    def test_localhost_ipv4(self) -> None:
        """Test localhost IPv4 address matching."""
        allowed = ["127.0.0.1"]
        assert _is_ip_allowed("127.0.0.1", allowed) is True

    def test_localhost_ipv6(self) -> None:
        """Test localhost IPv6 address matching."""
        allowed = ["::1"]
        assert _is_ip_allowed("::1", allowed) is True


class TestExtractClientIp:
    """Test suite for _extract_client_ip helper function."""

    def test_extract_from_x_forwarded_for_single(self) -> None:
        """Test extracting IP from X-Forwarded-For header with single IP."""
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "192.168.1.10"}
        request.client = None
        
        result = _extract_client_ip(request)
        assert result == "192.168.1.10"

    def test_extract_from_x_forwarded_for_chain(self) -> None:
        """Test extracting IP from X-Forwarded-For header with proxy chain."""
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "192.168.1.10, 10.0.0.5, 172.16.0.1"}
        request.client = None
        
        # Should return the first IP in the chain (original client)
        result = _extract_client_ip(request)
        assert result == "192.168.1.10"

    def test_extract_from_x_forwarded_for_with_whitespace(self) -> None:
        """Test extracting IP from X-Forwarded-For with extra whitespace."""
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "  192.168.1.10  ,  10.0.0.5  "}
        request.client = None
        
        result = _extract_client_ip(request)
        assert result == "192.168.1.10"

    def test_extract_from_request_client(self) -> None:
        """Test extracting IP from request.client when no X-Forwarded-For."""
        request = Mock(spec=Request)
        request.headers = {}
        request.client = Mock()
        request.client.host = "192.168.1.10"
        
        result = _extract_client_ip(request)
        assert result == "192.168.1.10"

    def test_extract_unknown_when_no_client_info(self) -> None:
        """Test returning 'unknown' when no client information available."""
        request = Mock(spec=Request)
        request.headers = {}
        request.client = None
        
        result = _extract_client_ip(request)
        assert result == "unknown"

    def test_extract_unknown_when_client_has_no_host(self) -> None:
        """Test returning 'unknown' when client exists but has no host."""
        request = Mock(spec=Request)
        request.headers = {}
        request.client = Mock()
        request.client.host = None
        
        result = _extract_client_ip(request)
        assert result == "unknown"

    def test_x_forwarded_for_takes_precedence(self) -> None:
        """Test that X-Forwarded-For takes precedence over request.client."""
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "192.168.1.10"}
        request.client = Mock()
        request.client.host = "10.0.0.5"
        
        result = _extract_client_ip(request)
        assert result == "192.168.1.10"


# ---------------------------------------------------------------------------
# Middleware integration tests
# ---------------------------------------------------------------------------


class TestLANSecurityMiddleware:
    """Test suite for LANSecurityMiddleware integration."""

    @pytest.fixture
    def app_with_middleware(self) -> FastAPI:
        """Create a FastAPI app with LAN security middleware for testing."""
        app = FastAPI()
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}
        
        return app

    def test_allowed_ip_passes_through(self, app_with_middleware: FastAPI) -> None:
        """Test that an allowed IP can access the endpoint.
        
        **Validates: Requirements 16.6, 19.2**
        Allowed IP should pass through the middleware successfully.
        """
        # Mock settings to use a specific allowed host
        with patch("src_new.shared.auth.lan_security.settings") as mock_settings:
            mock_settings.allowed_hosts = "192.168.1.10"
            
            # Add middleware after patching settings
            app_with_middleware.add_middleware(LANSecurityMiddleware)
            client = TestClient(app_with_middleware)
            
            # Simulate request from allowed IP
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "192.168.1.10"}
            )
            
            assert response.status_code == 200
            assert response.json() == {"message": "success"}

    def test_blocked_ip_returns_403(self, app_with_middleware: FastAPI, caplog) -> None:
        """Test that a blocked IP receives 403 Forbidden.
        
        **Validates: Requirements 16.6, 19.2**
        Blocked IP should return 403 Forbidden response.
        """
        with patch("src_new.shared.auth.lan_security.settings") as mock_settings:
            mock_settings.allowed_hosts = "192.168.1.10"
            
            app_with_middleware.add_middleware(LANSecurityMiddleware)
            client = TestClient(app_with_middleware)
            
            with caplog.at_level(logging.WARNING):
                # Simulate request from blocked IP
                response = client.get(
                    "/test",
                    headers={"X-Forwarded-For": "10.0.0.5"}
                )
            
            assert response.status_code == 403
            assert "Forbidden" in response.json()["detail"]
            assert response.json()["client_ip"] == "10.0.0.5"
            
            # Verify that the attempt was logged
            assert "Unauthorized access attempt" in caplog.text
            assert "10.0.0.5" in caplog.text

    def test_cidr_range_allowed(self, app_with_middleware: FastAPI) -> None:
        """Test that IPs within a CIDR range are allowed."""
        with patch("src_new.shared.auth.lan_security.settings") as mock_settings:
            mock_settings.allowed_hosts = "192.168.1.0/24"
            
            app_with_middleware.add_middleware(LANSecurityMiddleware)
            client = TestClient(app_with_middleware)
            
            # Test multiple IPs within the range
            for ip in ["192.168.1.1", "192.168.1.100", "192.168.1.254"]:
                response = client.get(
                    "/test",
                    headers={"X-Forwarded-For": ip}
                )
                assert response.status_code == 200, f"IP {ip} should be allowed"

    def test_cidr_range_blocked(self, app_with_middleware: FastAPI) -> None:
        """Test that IPs outside a CIDR range are blocked."""
        with patch("src_new.shared.auth.lan_security.settings") as mock_settings:
            mock_settings.allowed_hosts = "192.168.1.0/24"
            
            app_with_middleware.add_middleware(LANSecurityMiddleware)
            client = TestClient(app_with_middleware)
            
            # Test IPs outside the range
            for ip in ["192.168.2.1", "10.0.0.1", "8.8.8.8"]:
                response = client.get(
                    "/test",
                    headers={"X-Forwarded-For": ip}
                )
                assert response.status_code == 403, f"IP {ip} should be blocked"

    def test_localhost_fallback_when_allowed_hosts_empty(
        self, app_with_middleware: FastAPI
    ) -> None:
        """Test that empty ALLOWED_HOSTS falls back to localhost-only.
        
        **Validates: Requirements 16.6, 19.2**
        Missing ALLOWED_HOSTS env var should fall back to localhost-only access.
        """
        with patch("src_new.shared.auth.lan_security.settings") as mock_settings:
            mock_settings.allowed_hosts = ""
            
            app_with_middleware.add_middleware(LANSecurityMiddleware)
            client = TestClient(app_with_middleware)
            
            # Test that localhost IPv4 is allowed
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "127.0.0.1"}
            )
            assert response.status_code == 200
            
            # Test that IPv6 localhost is allowed
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "::1"}
            )
            assert response.status_code == 200
            
            # Test that other IPs are blocked (fallback to localhost-only)
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "192.168.1.10"}
            )
            assert response.status_code == 403

    def test_multiple_allowed_hosts(self, app_with_middleware: FastAPI) -> None:
        """Test middleware with multiple allowed hosts."""
        with patch("src_new.shared.auth.lan_security.settings") as mock_settings:
            mock_settings.allowed_hosts = "192.168.1.10,10.0.0.5,172.16.0.1"
            
            app_with_middleware.add_middleware(LANSecurityMiddleware)
            client = TestClient(app_with_middleware)
            
            # Test each allowed IP
            for ip in ["192.168.1.10", "10.0.0.5", "172.16.0.1"]:
                response = client.get(
                    "/test",
                    headers={"X-Forwarded-For": ip}
                )
                assert response.status_code == 200, f"IP {ip} should be allowed"
            
            # Test blocked IP
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "8.8.8.8"}
            )
            assert response.status_code == 403

    def test_ipv6_addresses(self, app_with_middleware: FastAPI) -> None:
        """Test middleware with IPv6 addresses."""
        with patch("src_new.shared.auth.lan_security.settings") as mock_settings:
            mock_settings.allowed_hosts = "::1,fe80::1"
            
            app_with_middleware.add_middleware(LANSecurityMiddleware)
            client = TestClient(app_with_middleware)
            
            # Test allowed IPv6 addresses
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "::1"}
            )
            assert response.status_code == 200
            
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "fe80::1"}
            )
            assert response.status_code == 200
            
            # Test blocked IPv6 address
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "2001:db8::1"}
            )
            assert response.status_code == 403

    def test_middleware_logs_initialization(
        self, app_with_middleware: FastAPI
    ) -> None:
        """Test that middleware initializes correctly with allowed hosts."""
        with patch("src_new.shared.auth.lan_security.settings") as mock_settings:
            mock_settings.allowed_hosts = "192.168.1.0/24,10.0.0.0/8"
            
            # Middleware should initialize without errors
            app_with_middleware.add_middleware(LANSecurityMiddleware)
            client = TestClient(app_with_middleware)
            
            # Verify that IPs in the allowed ranges can access
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "192.168.1.50"}
            )
            assert response.status_code == 200
            
            response = client.get(
                "/test",
                headers={"X-Forwarded-For": "10.5.10.20"}
            )
            assert response.status_code == 200


# ---------------------------------------------------------------------------
# Bind host helper tests
# ---------------------------------------------------------------------------


class TestGetBindHost:
    """Test suite for get_bind_host helper function."""

    def test_bind_to_api_host_by_default(self) -> None:
        """Test that services bind to api_host by default."""
        with patch("src_new.shared.auth.lan_security.settings") as mock_settings:
            mock_settings.api_host = "192.168.1.10"
            mock_settings.bind_all_interfaces = False
            
            result = get_bind_host()
            assert result == "192.168.1.10"

    def test_bind_to_all_interfaces_when_enabled(self, caplog) -> None:
        """Test that services bind to 0.0.0.0 when BIND_ALL_INTERFACES=true."""
        with patch("src_new.shared.auth.lan_security.settings") as mock_settings:
            mock_settings.api_host = "192.168.1.10"
            mock_settings.bind_all_interfaces = True
            
            with caplog.at_level(logging.WARNING):
                result = get_bind_host()
            
            assert result == "0.0.0.0"
            assert "BIND_ALL_INTERFACES=true" in caplog.text
            assert "firewall rules" in caplog.text

    def test_localhost_binding(self) -> None:
        """Test binding to localhost."""
        with patch("src_new.shared.auth.lan_security.settings") as mock_settings:
            mock_settings.api_host = "127.0.0.1"
            mock_settings.bind_all_interfaces = False
            
            result = get_bind_host()
            assert result == "127.0.0.1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
