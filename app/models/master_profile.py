"""Master profile: personal data and bank details for estimates and payments."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class MasterProfile(Base, TimestampMixin):
    """Extended profile for masters — personal data + bank details.

    Used in PDF/XLSX estimate exports and QR code generation.
    """
    __tablename__ = "master_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    # ─── Personal data (for document headers) ───
    full_name: Mapped[str | None] = mapped_column(String(200))  # ФИО
    phone: Mapped[str | None] = mapped_column(String(20))  # +7...
    email: Mapped[str | None] = mapped_column(String(200))
    telegram_username: Mapped[str | None] = mapped_column(String(100))  # @username
    company_name: Mapped[str | None] = mapped_column(String(200))  # ИП / ООО
    inn: Mapped[str | None] = mapped_column(String(12))  # ИНН
    address: Mapped[str | None] = mapped_column(Text)  # Юридический адрес
    specialization: Mapped[str | None] = mapped_column(String(200))  # Электрик, Сантехник

    # ─── Bank details (for QR code + payment) ───
    bank_name: Mapped[str | None] = mapped_column(String(200))  # Сбербанк
    bik: Mapped[str | None] = mapped_column(String(9))  # БИК
    correspondent_account: Mapped[str | None] = mapped_column(String(20))  # Корр. счёт
    settlement_account: Mapped[str | None] = mapped_column(String(20))  # Расчётный счёт
    card_number: Mapped[str | None] = mapped_column(String(19))  # Номер карты (для перевода)
    sbp_phone: Mapped[str | None] = mapped_column(String(20))  # Телефон для СБП
    payment_recipient: Mapped[str | None] = mapped_column(String(200))  # Получатель (ФИО или ИП)

    # Relationship
    user = relationship("User", backref="master_profile", uselist=False)
