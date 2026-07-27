import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerificationError:
        return False


def validate_password(password: str) -> None:
    if len(password) < 14:
        raise ValueError("Пароль должен содержать не менее 14 символов")
    if password.lower() == password or password.upper() == password:
        raise ValueError("Пароль должен содержать буквы разного регистра")
    if not any(char.isdigit() for char in password):
        raise ValueError("Пароль должен содержать цифру")


def new_token(size: int = 32) -> str:
    return secrets.token_urlsafe(size)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
