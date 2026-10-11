"""Transport and bounded data validation for reviewed registration resources."""

import base64
import binascii
import re
import zlib
from .contract import AdmissionError, digest, inspect_data, json_data


def registration_data(content, spec, product_base, report_path):
    if (
        not isinstance(spec["maximum_decoded_bytes"], int)
        or not 0 < spec["maximum_decoded_bytes"] <= 4194304
    ):
        raise AdmissionError("registration exceeds reviewed decoded-byte budget")
    variable = spec["variable"]
    if not re.fullmatch(r"__[A-Z][A-Z0-9_]+__", variable):
        raise AdmissionError("unreviewed registration identifier")
    prefix = (
        f"globalThis.{variable}=globalThis.{variable}||[];globalThis.{variable}.push("
    )
    try:
        text = content.decode()
    except UnicodeError as error:
        raise AdmissionError("registration encoding") from error
    if not text.startswith(prefix) or not text.endswith(");\n"):
        raise AdmissionError("unreviewed registration executable wrapper")
    envelope = json_data(text[len(prefix) : -3])
    encoding = envelope.get("payload_encoding")
    payload_member = (
        "payload_gzip_base64" if encoding == "gzip_base64" else "payload_json"
    )
    if encoding not in ("gzip_base64", "json") or set(envelope) != {
        "asset_key",
        "payload_encoding",
        payload_member,
        "payload_sha256",
    }:
        raise AdmissionError("unknown registration envelope")
    if (
        envelope["asset_key"] != spec["asset_key"]
        or envelope["payload_sha256"] != spec["payload_sha256"]
    ):
        raise AdmissionError("registration ownership differs")
    try:
        if encoding == "gzip_base64":
            encoded = base64.b64decode(envelope[payload_member], validate=True)
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            raw = decoder.decompress(encoded, spec["maximum_decoded_bytes"] + 1)
            if (
                len(raw) > spec["maximum_decoded_bytes"]
                or not decoder.eof
                or decoder.unused_data
                or decoder.unconsumed_tail
            ):
                raise AdmissionError("gzip output budget or trailing data")
        else:
            raw = envelope[payload_member].encode()
    except AdmissionError:
        raise
    except (ValueError, TypeError, binascii.Error, zlib.error) as error:
        raise AdmissionError("invalid registration transport") from error
    if (
        len(raw) != spec["decoded_bytes"]
        or len(raw) > spec["maximum_decoded_bytes"]
        or digest(raw) != spec["payload_sha256"]
    ):
        raise AdmissionError("decoded payload identity or budget differs")
    document = json_data(raw)
    inspect_data(document, product_base, report_path)
    return {
        "asset_key": spec["asset_key"],
        "encoding": encoding,
        "decoded_bytes": len(raw),
        "payload_sha256": digest(raw),
    }
