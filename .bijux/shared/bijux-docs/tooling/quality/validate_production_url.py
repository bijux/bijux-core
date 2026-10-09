#!/usr/bin/env python3
"""Reject development origins before production documentation builds."""
from __future__ import annotations
import argparse
import ipaddress
import socket
from urllib.parse import urlsplit


def development_host(hostname: str) -> bool:
    """Classify literal/local names without contacting DNS or assuming a public origin."""
    hostname = hostname.rstrip('.').lower()
    if hostname == 'localhost' or hostname.endswith(('.localhost', '.invalid', '.internal', '.test', '.local', '.lan', '.home', '.home.arpa')):
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            # Browsers accept shortened, decimal and octal IPv4 literal forms.
            address = ipaddress.ip_address(socket.inet_aton(hostname))
        except OSError:
            return '.' not in hostname or all(part.isdigit() for part in hostname.split('.'))
    return not address.is_global or address.is_multicast


def validate(url: str, *, allow_empty: bool = False) -> str:
    if not url and allow_empty:
        return url
    parsed = urlsplit(url)
    hostname = parsed.hostname or ''
    if (parsed.scheme != 'https' or not hostname or parsed.username is not None
            or parsed.password is not None or parsed.port is not None
            or parsed.query or parsed.fragment or not url.endswith('/')
            or hostname == 'localhost' or hostname.endswith('.localhost')
            or any(ord(c) <= 32 or c in '%\\' for c in url)
            or any(part in {'.', '..'} for part in parsed.path.split('/'))):
        raise ValueError('Production site URL must be normalized public HTTPS with a trailing slash')
    if development_host(hostname):
        raise ValueError('Production site URL cannot use a local/private/reserved/development hostname')
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('urls', nargs='+')
    parser.add_argument('--allow-empty', action='store_true')
    args = parser.parse_args()
    try:
        for url in args.urls:
            validate(url, allow_empty=args.allow_empty)
    except ValueError as exc:
        parser.exit(1, f'ERROR: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
