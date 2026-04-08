"""Payment service: QR generation, confirmation, commission triggering.

Russian payment QR uses ГОСТ Р 56042-2014 (СБП-compatible) format:
  ST00012|Name=...|PersonalAcc=...|BankName=...|BIC=...|CorrespAcc=...|PayeeINN=...|
  Sum=...|Purpose=...

For simplicity, we generate a plain-text payment instruction with phone/card
that the master shares with the client. Full bank QR requires merchant credentials.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.audit import log_audit
from app.core.events import Event, event_bus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.payment import Payment
from app.services.commission import calculate_and_save


async def create_payment(
    session: AsyncSession,
    *,
    order_id: int | None = None,
    estimate_id: int | None = None,
    amount: int,
    method: str = "phone",
) -> Payment:
    """Create a pending payment record."""
    if amount <= 0:
        raise ValidationError("Сумма оплаты должна быть больше 0")
    if method not in ("qr", "phone", "card", "cash"):
        raise ValidationError("Метод оплаты: qr, phone, card, cash")

    settings = get_settings()

    # Generate QR payload or phone instruction
    qr_payload = None
    phone_number = None

    if method in ("phone", "qr") and settings.payment_phone:
        phone_number = settings.payment_phone
        qr_payload = _build_payment_text(amount, settings)
    elif method == "cash":
        qr_payload = "Оплата наличными мастеру"

    payment = Payment(
        order_id=order_id,
        estimate_id=estimate_id,
        amount_expected=amount,
        currency=settings.default_currency,
        method=method,
        status="pending",
        qr_payload=qr_payload,
        phone_number=phone_number,
    )
    session.add(payment)
    await session.flush()

    await log_audit(
        session, user_id=None, action="payment.created",
        entity_type="payment", entity_id=payment.id,
        new_value={"amount": amount, "method": method},
    )

    return payment


async def confirm_payment(
    session: AsyncSession,
    *,
    payment_id: int,
    confirmed_by: int,
    amount_paid: int | None = None,
    proof_url: str | None = None,
) -> Payment:
    """Confirm a payment and trigger commission calculation."""
    payment = await _get_payment(session, payment_id)

    if payment.status == "confirmed":
        raise ConflictError("Платёж уже подтверждён")
    if payment.status not in ("pending", "sent"):
        raise ValidationError(f"Нельзя подтвердить платёж в статусе '{payment.status}'")

    payment.status = "confirmed"
    payment.amount_paid = amount_paid or payment.amount_expected
    payment.marked_by = confirmed_by
    payment.paid_at = datetime.now(UTC)
    payment.proof_url = proof_url
    await session.flush()

    # Calculate and save commission
    if payment.order_id:
        from app.models.order import Order
        result = await session.execute(select(Order).where(Order.id == payment.order_id))
        order = result.scalar_one_or_none()
        master_id = order.master_id if order else confirmed_by
    else:
        master_id = confirmed_by

    await calculate_and_save(
        session,
        payment_id=payment.id,
        order_id=payment.order_id,
        master_id=master_id,
        gross_total=payment.amount_paid,
    )

    await log_audit(
        session, user_id=confirmed_by, action="payment.confirmed",
        entity_type="payment", entity_id=payment.id,
        new_value={"amount_paid": payment.amount_paid},
    )

    await event_bus.publish(Event(
        type="payment.confirmed",
        payload={"payment_id": payment.id, "order_id": payment.order_id, "amount": payment.amount_paid},
        actor_id=confirmed_by,
    ))

    return payment


async def get_payment_for_order(session: AsyncSession, order_id: int) -> Payment | None:
    result = await session.execute(
        select(Payment).where(Payment.order_id == order_id).order_by(Payment.id.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def get_payment_info(payment: Payment) -> dict:
    """Build payment info dict for display."""
    settings = get_settings()
    info = {
        "id": payment.id,
        "amount": payment.amount_expected,
        "currency": payment.currency,
        "method": payment.method,
        "status": payment.status,
        "status_label": _status_label(payment.status),
    }

    if payment.method in ("phone", "qr") and payment.phone_number:
        info["phone"] = payment.phone_number
        info["bank_name"] = settings.payment_bank_name
        info["recipient_name"] = settings.payment_recipient_name
        info["instruction"] = payment.qr_payload

    return info


def _build_payment_text(amount: int, settings) -> str:
    """Build human-readable payment instruction."""
    parts = [f"💳 Оплата: {amount}₽"]
    if settings.payment_phone:
        parts.append(f"📱 Телефон: {settings.payment_phone}")
    if settings.payment_bank_name:
        parts.append(f"🏦 Банк: {settings.payment_bank_name}")
    if settings.payment_recipient_name:
        parts.append(f"👤 Получатель: {settings.payment_recipient_name}")
    parts.append("📝 Назначение: Оплата услуг ПриДел")
    return "\n".join(parts)


def _status_label(status: str) -> str:
    return {
        "pending": "⏳ Ожидает оплаты",
        "sent": "📤 Отправлен",
        "confirmed": "✅ Оплачено",
        "failed": "❌ Ошибка",
        "refunded": "↩️ Возврат",
    }.get(status, status)


async def _get_payment(session: AsyncSession, payment_id: int) -> Payment:
    result = await session.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise NotFoundError("Платёж")
    return payment
