import os
import hashlib
import base64
from pathlib import Path
from modules.logging_sys import log_info, log_error, log_warn, log_debug
from modules.settings import get_trusted_keys_dir

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
        log_error("Il pacchetto 'cryptography' non e' installato.")
        log_info("Esegui: pip install cryptography")
        return False

    trusted_dir = get_trusted_keys_dir()
    os.makedirs(trusted_dir, exist_ok=True)
    priv_path = trusted_dir / "hpm_private.pem"
    pub_path = trusted_dir / "hpm_public.pem"

    if priv_path.exists():
        log_warn(f"Una chiave privata esiste gia' in: {priv_path}")
        ans = input("Vuoi sovrascriverla? (s/N): ")
        if ans.lower() != 's':
            return False

    log_info("Generazione coppia di chiavi Ed25519 in corso...")
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

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

    log_info("Chiavi generate con successo!")
    log_info(f"Privata: {priv_path}")
    log_info(f"Pubblica: {pub_path}")
    return True

def sign_payload(payload_bytes: bytes) -> str:
    if not HAS_CRYPTO:
        log_error("Cryptography non disponibile. Firma impossibile.")
        return None

    trusted_dir = get_trusted_keys_dir()
    priv_key_path = None
    
    # Cerca chiave
    if (trusted_dir / "hpm_private.pem").exists():
        priv_key_path = trusted_dir / "hpm_private.pem"
    else:
        for f in trusted_dir.glob("*.pem"):
            if b"PRIVATE KEY" in f.read_bytes():
                priv_key_path = f
                break

    if not priv_key_path:
        log_error(f"Nessuna chiave privata trovata in {trusted_dir}")
        return None

    log_debug(f"Usando la chiave privata: {priv_key_path}")
    
    try:
        with open(priv_key_path, "rb") as key_file:
            private_key = serialization.load_pem_private_key(key_file.read(), password=None)
        signature_bytes = private_key.sign(payload_bytes)
        return base64.b64encode(signature_bytes).decode('utf-8')
    except Exception as e:
        log_error(f"Errore durante la firma: {e}")
        return None

def verify_signature(payload_bytes: bytes, signature_b64: str) -> bool:
    if not HAS_CRYPTO:
        log_error("Cryptography non disponibile. Impossibile verificare la firma.")
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
        log_error(f"Nessuna chiave pubblica trovata in {trusted_dir}")
        return False

    try:
        with open(pub_key_path, "rb") as key_file:
            public_key = serialization.load_pem_public_key(key_file.read())
        signature_bytes = base64.b64decode(signature_b64)
        public_key.verify(signature_bytes, payload_bytes)
        return True
    except Exception as e:
        log_error(f"Firma non valida o errore di verifica: {e}")
        return False
