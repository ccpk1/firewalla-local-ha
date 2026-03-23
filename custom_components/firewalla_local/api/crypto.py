"""Cryptography helpers for the Firewalla Local API boundary."""

from __future__ import annotations

import base64
from typing import cast

from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .models import GeneratedKeys


def generate_firewalla_keys() -> GeneratedKeys:
    """Generate the RSA keypair formatted for Firewalla ETP."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return GeneratedKeys(private_pem=private_pem, public_pem=public_pem)


def derive_qr_bootstrap_key(license_value: str, seed: str) -> str:
    """Return the pre-pairing AES material derived from the QR code."""
    return f"{license_value[:8]}{seed}"


def derive_aes256_key(key_material: str) -> bytes:
    """Mirror the NodeJS SecureUtil AES key derivation behavior."""
    key = key_material[:32].encode("utf-8")
    if len(key) != 32:
        raise ValueError(
            "Derived AES key material must be at least 32 UTF-8 bytes long"
        )
    return key


def aes256_cbc_encrypt_to_base64(plaintext: str, key_material: str) -> str:
    """Encrypt a UTF-8 string with AES-256-CBC and return base64 ciphertext."""
    key = derive_aes256_key(key_material)
    iv = bytes(16)

    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("utf-8")


def aes256_cbc_decrypt_from_base64(ciphertext: str, key_material: str) -> str:
    """Decrypt a base64 AES-256-CBC payload using the NodeJS key contract."""
    key = derive_aes256_key(key_material)
    iv = bytes(16)

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(base64.b64decode(ciphertext))
    padded_plaintext += decryptor.finalize()

    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
    return plaintext.decode("utf-8")


def rsa_decrypt_base64(ciphertext: str, private_pem: str) -> str:
    """Decrypt base64 RSA ciphertext using Node's default OAEP/SHA-1 behavior."""
    private_key = cast(
        RSAPrivateKey,
        serialization.load_pem_private_key(
            private_pem.encode("utf-8"),
            password=None,
        ),
    )
    plaintext = private_key.decrypt(
        base64.b64decode(ciphertext),
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA1()),
            algorithm=hashes.SHA1(),
            label=None,
        ),
    )
    return plaintext.decode("utf-8")
