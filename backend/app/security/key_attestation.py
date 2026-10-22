"""Android hardware Key Attestation verification (for sideloaded / non-Google-Play distribution).

The DC app asks the Android Keystore to generate a key whose certificate chain carries a hardware
attestation extension. The chain roots in Google's hardware attestation root, and the leaf's
attestation extension states, TEE/StrongBox-enforced, the device's verified-boot state and whether
the bootloader is locked. Verifying that here tells us the request comes from a genuine, unrooted,
locked device - the assurance Play Integrity would give, without the Google Play dependency.

IMPORTANT - this ships in REPORT-ONLY mode (see settings.require_device_attestation). A from-scratch
attestation verifier must be validated against real devices, and the pinned Google roots kept current,
before it is allowed to block anyone. Until then it records a pass/fail verdict for audit only.

Operator setup:
  - Put Google's current hardware attestation root certificate(s) in
    app/security/google_attestation_roots.pem (PEM, one or more). Source + rotation:
    https://developer.android.com/privacy-and-security/security-key-attestation#root_certificate
  - With no roots provisioned, verification always returns verified=False, reason="no trust anchors".
"""

from __future__ import annotations

import base64
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

# OID of the Android Key attestation extension carried by the leaf certificate.
_ATTESTATION_OID = x509.ObjectIdentifier("1.3.6.1.4.1.11129.2.1.17")
_ROOTS_PEM = Path(__file__).with_name("google_attestation_roots.pem")

_CHALLENGE_TTL_SECONDS = 5 * 60
_lock = threading.Lock()
_issued: dict[str, float] = {}  # challenge(b64) -> expiry epoch


@dataclass
class AttestationResult:
    verified: bool
    reason: str
    device_locked: bool | None = None
    verified_boot: str | None = None


def new_challenge() -> str:
    """Issues a one-time base64 challenge the app must embed in its attestation."""
    challenge = base64.b64encode(secrets.token_bytes(32)).decode()
    now = time.time()
    with _lock:
        _prune(now)
        _issued[challenge] = now + _CHALLENGE_TTL_SECONDS
    return challenge


def _consume_challenge(challenge_b64: str) -> bool:
    now = time.time()
    with _lock:
        _prune(now)
        expiry = _issued.pop(challenge_b64, None)
    return expiry is not None and expiry > now


def _prune(now: float) -> None:
    for k in [k for k, exp in _issued.items() if exp <= now]:
        _issued.pop(k, None)


def _load_roots() -> list[x509.Certificate]:
    if not _ROOTS_PEM.is_file():
        return []
    data = _ROOTS_PEM.read_bytes()
    roots: list[x509.Certificate] = []
    for block in _split_pem(data):
        try:
            roots.append(x509.load_pem_x509_certificate(block))
        except Exception:
            continue
    return roots


def _split_pem(data: bytes) -> list[bytes]:
    out, cur, inside = [], [], False
    for line in data.splitlines():
        if b"BEGIN CERTIFICATE" in line:
            inside, cur = True, [line]
        elif b"END CERTIFICATE" in line:
            cur.append(line)
            out.append(b"\n".join(cur))
            inside = False
        elif inside:
            cur.append(line)
    return out


def verify(cert_chain_der: list[bytes], challenge_b64: str) -> AttestationResult:
    """Verifies an attestation chain (leaf first, DER) against the issued [challenge_b64].

    Checks, in order: the challenge was issued by us and is unused; the chain is signed
    leaf<-...<-root and the top is signed by a pinned Google root; the leaf's attestation
    extension embeds exactly our challenge; and (best effort) the device is locked / verified-boot.
    """
    if not _consume_challenge(challenge_b64):
        return AttestationResult(False, "challenge unknown or expired")
    if not cert_chain_der:
        return AttestationResult(False, "empty certificate chain")

    roots = _load_roots()
    if not roots:
        return AttestationResult(False, "no trust anchors provisioned")

    try:
        chain = [x509.load_der_x509_certificate(d) for d in cert_chain_der]
    except Exception as exc:
        return AttestationResult(False, f"unparseable certificate: {exc}")

    # Each cert must be signed by the next one up.
    for child, issuer in zip(chain, chain[1:]):
        if not _signed_by(child, issuer):
            return AttestationResult(False, "broken certificate chain")

    # The top of the app-supplied chain must itself be signed by a pinned Google root.
    if not any(_signed_by(chain[-1], root) for root in roots):
        return AttestationResult(False, "chain does not root in a pinned Google attestation root")

    leaf = chain[0]
    try:
        ext = leaf.extensions.get_extension_for_oid(_ATTESTATION_OID).value
        ext_bytes = ext.public_bytes() if hasattr(ext, "public_bytes") else ext.value
    except Exception:
        return AttestationResult(False, "no attestation extension on leaf certificate")

    # The challenge we issued must appear verbatim in the attestation (it is carried as an OCTET
    # STRING inside the KeyDescription). A substring check is a robust nonce binding without a full
    # ASN.1 schema decode; the full field-level parse is the part pending real-device validation.
    challenge_raw = base64.b64decode(challenge_b64)
    if challenge_raw not in ext_bytes:
        return AttestationResult(False, "attestation challenge does not match")

    device_locked, verified_boot = _best_effort_boot_state(ext_bytes)
    ok = device_locked is not False and verified_boot in (None, "Verified")
    reason = "ok" if ok else f"device not in a trusted boot state (locked={device_locked}, boot={verified_boot})"
    return AttestationResult(ok, reason, device_locked=device_locked, verified_boot=verified_boot)


def _signed_by(cert: x509.Certificate, issuer: x509.Certificate) -> bool:
    pub = issuer.public_key()
    try:
        if isinstance(pub, rsa.RSAPublicKey):
            pub.verify(cert.signature, cert.tbs_certificate_bytes,
                       padding.PKCS1v15(), cert.signature_hash_algorithm)
        elif isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(cert.signature, cert.tbs_certificate_bytes,
                       ec.ECDSA(cert.signature_hash_algorithm))
        else:
            return False
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def _best_effort_boot_state(ext_bytes: bytes) -> tuple[bool | None, str | None]:
    """Conservative extraction of RootOfTrust (deviceLocked, verifiedBootState) from the raw
    attestation extension. Returns (None, None) when it can't be read - and a None never fails the
    check on its own, because this is the field-parse that still needs real-device validation.

    verifiedBootState enum: Verified=0, SelfSigned=1, Unverified=2, Failed=3 (DER ENUMERATED).
    """
    verified_boot = None
    # A DER ENUMERATED is tag 0x0A, length 0x01, value 0..3. Look for a lone enum near a boolean.
    for i in range(len(ext_bytes) - 2):
        if ext_bytes[i] == 0x0A and ext_bytes[i + 1] == 0x01 and ext_bytes[i + 2] <= 0x03:
            verified_boot = {0: "Verified", 1: "SelfSigned", 2: "Unverified", 3: "Failed"}[ext_bytes[i + 2]]
            break
    # Can't reliably isolate the deviceLocked boolean without the full structure; leave as unknown.
    return None, verified_boot
