import pytest
from argon2 import PasswordHasher

from app.cli import random_password
from app.security import hash_password, token_hash, validate_password, verify_password


def test_password_is_argon2id_hash() -> None:
    hashed = hash_password("Correct-Horse-42-Battery")
    assert hashed.startswith("$argon2id$")
    assert PasswordHasher().verify(hashed, "Correct-Horse-42-Battery")
    assert verify_password(hashed, "Correct-Horse-42-Battery")
    assert not verify_password(hashed, "wrong")


def test_password_policy() -> None:
    with pytest.raises(ValueError):
        validate_password("Short-42")
    validate_password("Short-420")


def test_token_hash_is_stable_and_not_plaintext() -> None:
    assert token_hash("secret") == token_hash("secret")
    assert token_hash("secret") != "secret"


def test_generated_admin_password_always_matches_policy() -> None:
    for _ in range(20):
        password = random_password()
        validate_password(password)
        assert len(password) == 24
