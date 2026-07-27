import argparse
import getpass
import secrets
import string
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import EnrollmentToken, User
from app.security import hash_password, new_token, token_hash, validate_password


def random_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(24))


def password_input(generate: bool) -> tuple[str, bool]:
    if generate:
        return random_password(), True
    password = getpass.getpass("Пароль: ")
    if password != getpass.getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают")
    return password, False


def admin_create(login: str, generate: bool) -> None:
    password, generated = password_input(generate)
    validate_password(password)
    with SessionLocal.begin() as db:
        if db.scalar(select(User).where(User.login == login)):
            raise SystemExit(f"Пользователь {login!r} уже существует")
        db.add(
            User(
                login=login,
                password_hash=hash_password(password),
                role="admin",
                must_change_password=generated,
            )
        )
    print(f"Администратор {login!r} создан.")
    if generated:
        print(f"Временный пароль (показывается один раз): {password}")


def admin_reset_password(login: str) -> None:
    password, _ = password_input(False)
    validate_password(password)
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.login == login))
        if not user:
            raise SystemExit(f"Пользователь {login!r} не найден")
        user.password_hash = hash_password(password)
        user.must_change_password = False
    print(f"Пароль пользователя {login!r} изменён.")


def enrollment_create(server_name: str, platform: str) -> None:
    token = new_token()
    expires_at = datetime.now(UTC) + timedelta(minutes=get_settings().enrollment_ttl_minutes)
    with SessionLocal.begin() as db:
        db.add(
            EnrollmentToken(
                token_hash=token_hash(token),
                server_name=server_name,
                platform=platform,
                expires_at=expires_at,
            )
        )
    print(f"Enrollment token (показывается один раз): {token}")
    print(f"Действует до: {expires_at.isoformat()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("admin-create")
    create.add_argument("--login", default="admin")
    create.add_argument("--generate", action="store_true")

    reset = commands.add_parser("admin-reset-password")
    reset.add_argument("--login", default="admin")

    enrollment = commands.add_parser("enrollment-create")
    enrollment.add_argument("--server-name", required=True)
    enrollment.add_argument("--platform", choices=["ubuntu", "openwrt", "routeros"], required=True)

    args = parser.parse_args()
    if args.command == "admin-create":
        admin_create(args.login, args.generate)
    elif args.command == "admin-reset-password":
        admin_reset_password(args.login)
    else:
        enrollment_create(args.server_name, args.platform)


if __name__ == "__main__":
    main()

