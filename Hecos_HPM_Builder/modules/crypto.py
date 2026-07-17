import os
import hashlib
import base64
from pathlib import Path
from modules.logging_sys import log_info, log_error, log_warn, log_debug
from modules.settings import get_trusted_keys_dir, get_private_key_path

try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""): 
            h.update(chunk)
    return h.hexdigest()

def generate_key_pair() -> bool:
    if not HAS_CRYPTO:
        log_error("Package 'cryptography' is not installed.")
        log_info("Run: pip install cryptography")
        return False

    trusted_dir = get_trusted_keys_dir()
    os.makedirs(trusted_dir, exist_ok=True)

    priv_path = get_private_key_path()
    pub_path = trusted_dir / "hpm_public.pem"

    if priv_path.exists():
        log_warn(f"A private key already exists in: {priv_path}")
        ans = input("Do you want to overwrite it? (y/N): ")
        if ans.lower() != 'y':
            return False

    log_info("Generating Ed25519 key pair...")
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    priv_path.parent.mkdir(parents=True, exist_ok=True)
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    with open(priv_path, "wb") as f:
        f.write(priv_bytes)

    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open(pub_path, "wb") as f:
        f.write(pub_bytes)

    log_info("Keys generated successfully!")
    log_info(f"Private: {priv_path}")
    log_info(f"Public: {pub_path}")
    return True

def sign_payload(payload_bytes: bytes) -> str:
    if not HAS_CRYPTO:
        log_error("Cryptography not available. Cannot sign.")
        return None

    priv_key_path = get_private_key_path()
    if not priv_key_path.exists():
        log_error(f"Private key not found in: {priv_key_path}")
        return None

    log_debug(f"Using private key: {priv_key_path}")
    
    try:
        with open(priv_key_path, "rb") as key_file:
            private_key = serialization.load_pem_private_key(key_file.read(), password=None)
        signature_bytes = private_key.sign(payload_bytes)
        return base64.b64encode(signature_bytes).decode('utf-8')
    except Exception as e:
        log_error(f"Error signing: {e}")
        return None

def verify_signature(payload_bytes: bytes, signature_b64: str) -> bool:
    if not HAS_CRYPTO:
        log_error("Cryptography not available. Cannot verify signature.")
        return False

    trusted_dir = get_trusted_keys_dir()
    pub_key_path = None
    
    # Cerca chiave pubblica
    if (trusted_dir / "hpm_public.pem").exists():
        pub_key_path = trusted_dir / "hpm_public.pem"
    else:
        for f in trusted_dir.glob("*.pem"):
            if b"PUBLIC KEY" in f.read_bytes():
                pub_key_path = f
                break

    if not pub_key_path:
        log_error(f"No public key found in {trusted_dir}")
        return False

    try:
        with open(pub_key_path, "rb") as key_file:
            public_key = serialization.load_pem_public_key(key_file.read())
        signature_bytes = base64.b64decode(signature_b64)
        public_key.verify(signature_bytes, payload_bytes)
        return True
    except Exception as e:
        log_error(f"Invalid signature or verification error: {e}")
        return False
