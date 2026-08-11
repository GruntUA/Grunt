"""Controller for User.

Lifecycle hooks — override any method to add custom logic:
  before_insert  — before a NEW document is saved to DB
  after_insert   — after a NEW document is saved to DB
  validate       — runs before every save (insert or update), raise to block
  before_save    — before an EXISTING document is updated
  after_save     — after an EXISTING document is updated
  before_delete  — before document is deleted
  after_delete   — after document is deleted

Access fields:
  self.field_name          — read field value
  self.field_name = value  — set field value
  self.data                — full document dict
  self.doctype             — DocType name ("User")
  self.user                — current User (or None)
  self.session             — async SQLAlchemy session (for advanced queries)
"""

from __future__ import annotations

from datetime import date, datetime

from grunt.document.base import Document


class User(Document):

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    last_name: str | None  # Прізвище
    first_name: str | None  # Ім'я
    middle_name: str | None  # По-батькові
    full_name: str | None  # Повне ім'я
    avatar: str | None  # Фото профілю
    email: str | None  # Email
    phone: str | None  # Телефон
    birth_date: date | None  # Дата народження
    gender: str | None  # Стать
    timezone: str | None  # Часовий пояс
    last_login: datetime | None  # Останній вхід
    bio: str | None  # Коротка біографія
    is_active: bool | None  # Активний
    is_superadmin: bool | None  # Суперадмін
    password: str | None  # Встановити пароль
    hashed_password: str | None  # Хешований пароль
    mfa_enabled: bool | None  # MFA увімкнено
    mfa_setup_button: None  # Керування MFA
    mfa_secret: str | None  # Секрет MFA
    mfa_backup_codes: dict | None  # Хеші резервних кодів
    mfa_backup_display: Any | None  # Резервні коди
    login_attempts: int | None  # Невдалі спроби входу
    locked_until: datetime | None  # Акаунт заблоковано до
    theme: str | None  # Тема оформлення
    language: str | None  # Мова
    refresh_token: str | None  # Токен оновлення (Refresh)
    refresh_token_expires_at: datetime | None  # Час дії Refresh токену
    reset_token: str | None  # Токен відновлення пароля
    reset_token_expires_at: datetime | None  # Час дії токену відновлення

    # end: auto-generated types

            async def validate(self) -> None:
        """Runs before every save — raise an exception to block."""
        pass

    async def before_save(self) -> None:
        """Runs before an existing document is updated."""
        pass

    async def after_save(self) -> None:
        """Runs after document is saved to the database."""
        pass
