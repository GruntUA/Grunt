"""Grunt Python API — Практичний посібник для розробників.

Цей модуль надає простий, високорівневий API для розробки додатків без необхідності
управління session, engine та user вручну.

ПЕРЕВАГА: Код стає чистішим, зрозумілішим і простішим для розумення.
"""

# ─────────────────────────────────────────────────────────────────────────────
# 1. ІМПОРТИ
# ─────────────────────────────────────────────────────────────────────────────

# Все, що вам потрібно, імпортується з головного модуля:
from grunt import (
    Doc,
    db,
    msgprint,
    throw,
    notify,
    can_read,
    can_write,
    get_current_user,
)

# ─────────────────────────────────────────────────────────────────────────────
# 2. РОБОТА З ДОКУМЕНТАМИ
# ─────────────────────────────────────────────────────────────────────────────

# Отримати документ
async def example_get_document():
    """Отримати документ за ID."""
    # Простий доступ без передачі session
    user = await Doc.get("User", "test@example.com")
    print(f"Email: {user['email']}, Ім'я: {user['full_name']}")


# Створити новий документ
async def example_create_document():
    """Створити новий документ."""
    contract = await Doc.create("Contract", {
        "party": "ABC Inc",
        "amount": 5000,
        "currency": "USD",
        "status": "Draft"
    })
    print(f"Створено контракт: {contract['id']}")


#改 змінити документ
async def example_update_document():
    """Отримати, змінити і зберегти документ."""
    contract = await Doc.get("Contract", "CTR-2026-001")

    # Змінити значення
    contract["status"] = "Active"
    contract["amount"] = 10000

    # Зберегти
    await contract.save()
    msgprint("Контракт оновлено", type="success")


# Зберегти з перевіркою
async def example_save_with_validation():
    """Зберегти документ після валідації."""
    invoice = await Doc.get("Invoice", "INV-2026-001")

    # Перевірити дозволи
    if not await can_write("Invoice", invoice['id']):
        throw("Немає прав для редагування цього рахунку")

    # Змінити
    invoice["status"] = "Submitted"

    # Зберегти з обробкою помилок
    try:
        await invoice.save()
        msgprint(f"Рахунок {invoice['name']} збережено")
    except Exception as e:
        throw(f"Помилка збереження: {str(e)}")


# Подати документ (workflow)
async def example_submit_document():
    """Подати документ (перейти в стан Submitted)."""
    invoice = await Doc.get("Invoice", "INV-2026-001")
    await invoice.submit()
    msgprint("Рахунок поданий до затвердження")


# Видалити документ
async def example_delete_document():
    """Видалити документ."""
    await Doc.delete("Contract", "CTR-2026-001")
    msgprint("Контракт видалено")


# Список документів
async def example_list_documents():
    """Отримати список документів з фільтрами."""
    # Все активні рахунки
    active_invoices = await Doc.list(
        "Invoice",
        filters={"status": "Active"},
        order_by="date",
        limit=50
    )

    print(f"Знайдено {len(active_invoices)} активних рахунків")
    for invoice in active_invoices:
        print(f"  - {invoice['name']}: {invoice['amount']}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. ПРОСТИЙ ДОСТУП ДО БД
# ─────────────────────────────────────────────────────────────────────────────

# Отримати одне значення
async def example_get_value():
    """Отримати значення однієї поля."""
    name = await db.get_value("User", "test@example.com", "full_name")
    print(f"Ім'я користувача: {name}")


# Встановити одне значення
async def example_set_value():
    """Встановити значення поля без отримання всього документа."""
    await db.set_value("User", "test@example.com", "status", "Active")
    msgprint("Статус користувача оновлено")


# Перевірити існування
async def example_check_exists():
    """Перевірити чи існує документ."""
    exists = await db.exists("User", "nonexistent@example.com")

    if exists:
        msgprint("Користувач знайдено")
    else:
        msgprint("Користувач не знайдено", type="warning")


# Рахувати записи
async def example_count_records():
    """Порахувати записи з фільтром."""
    active_count = await db.count("User", {"status": "Active"})
    print(f"Активних користувачів: {active_count}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. ДОЗВОЛИ І БЕЗПЕКА
# ─────────────────────────────────────────────────────────────────────────────

# Перевірити дозволи перед операцією
async def example_check_permissions():
    """Перевірити дозволи перед операцією."""
    # Перевірити дозвіл на читання
    can_read_contract = await can_read("Contract", "CTR-001")
    if not can_read_contract:
        throw("Немає доступу до цього контракту")

    # Перевірити дозвіл на запис
    can_edit = await can_write("Contract", "CTR-001")
    if not can_edit:
        msgprint("Ви можете тільки переглядати цей контракт (read-only)", type="warning")

    # Отримати інформацію про поточного користувача
    user = await get_current_user()
    print(f"Користувач: {user.email}")
    print(f"Ролі: {user.roles}")
    print(f"Суперадмін: {user.is_superadmin}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. ПОВІДОМЛЕННЯ І СПОВІЩЕННЯ
# ─────────────────────────────────────────────────────────────────────────────

# Показати повідомлення в UI
async def example_show_messages():
    """Показати різні типи повідомлень."""

    # Інформаційне
    msgprint("Операція в процесі...", type="info")

    # Успіх
    msgprint("Документ збережено!", type="success")

    # Попередження
    msgprint("Будьте обережні при редагуванні!", type="warning")

    # Помилка (але не зупиняє виконання)
    msgprint("Сталася проблема при відправленні email", type="error")


# Викинути помилку (зупинить виконання)
async def example_throw_error():
    """Викинути помилку і зупинити операцію."""

    contract = await Doc.get("Contract", "CTR-001")

    if contract["amount"] <= 0:
        throw("Сума контракту не може бути меншою за нуль", code="INVALID_AMOUNT")

    # Цей код не буде виконаний, якщо throw() був викликаний
    await contract.save()


# Відправити в-app сповіщення
async def example_send_notification():
    """Відправити сповіщення користувачу."""

    await notify(
        title="Новий рахунок",
        message="Вам надійшов новий рахунок від ABC Inc",
        doctype="Invoice",
        doc_id="INV-2026-005"
    )

    # Або для багатьох користувачів
    # await notify_all(
    #     title="Обслуговування",
    #     message="Сервер будуть оновлювати о 22:00",
    #     roles=["Admin", "Manager"]
    # )


# ─────────────────────────────────────────────────────────────────────────────
# 6. РЕАЛЬНІ ПРИКЛАДИ ДЛЯ DOCTYPES
# ─────────────────────────────────────────────────────────────────────────────

# Приклад 1: before_save hook
class Contract:
    """Контроллер для DocType Contract."""

    async def before_save(self):
        """Викликається перед збереженням."""
        from grunt import Doc, db, msgprint, throw

        # Перевірити що сума позитивна
        if self.doc['amount'] <= 0:
            throw("Сума контракту повинна бути > 0")

        # Перевірити що контрагент існує
        if not await db.exists("Party", self.doc['party']):
            throw(f"Контрагент {self.doc['party']} не знайдено в системі")

        # Отримати контрагента для отримання додаткової інформації
        party = await Doc.get("Party", self.doc['party'])

        # Встановити статус контрагента з контракту
        await db.set_value("Party", self.doc['party'], "last_contract_date", self.doc['date'])

        msgprint("Контракт валіден і готовий до збереження")


# Приклад 2: after_save hook
class Invoice:
    """Контроллер для DocType Invoice."""

    async def after_save(self):
        """Викликається після збереження."""
        from grunt import Doc, db, notify, queue_email, can_read

        # Якщо рахунок поданий - відправити повідомлення
        if self.doc.get('docstatus') == 1:  # Submitted

            # Отримати контрагента
            party = await Doc.get("Party", self.doc['party'])

            # Перевірити дозволи перед відправленням
            if await can_read("Party", party['id']):
                # Відправити in-app сповіщення
                await notify(
                    title="Новий рахунок поданий",
                    message=f"Рахунок {self.doc['name']} від {party['name']} готовий",
                    doctype="Invoice",
                    doc_id=self.doc['id']
                )

                # Додати email в чергу
                # await queue_email(
                #     recipient=party['contact_email'],
                #     subject=f"Рахунок {self.doc['name']}",
                #     body=f"Ваш рахунок на суму {self.doc['amount']} готовий до оплати"
                # )


# Приклад 3: Custom button in client script
class User:
    """Контроллер для DocType User."""

    async def on_load(self):
        """Викликається при завантаженні форми."""
        from grunt import msgprint

        # Не дозволити редагувати email для звичайних користувачів
        # (це буде реалізовано на фронтенді через client script)

        current_user = await self.get_current_user()
        if not current_user.is_superadmin and current_user.email != self.doc.get('email'):
            msgprint("Ви можете редагувати тільки свій профіль", type="warning")


# ─────────────────────────────────────────────────────────────────────────────
# 6. КОМЕНТАРІ ТА АКТИВНІСТЬ
# ─────────────────────────────────────────────────────────────────────────────

# Додати коментар до документа
async def example_add_comment():
    """Додати коментар до документа."""

    invoice = await Doc.get("Invoice", "INV-2026-001")

    # Додати коментар
    comment = await invoice.add_comment("Рахунок затверджено фінансистом")
    print(f"Comment added: {comment.text}")

    # Додати приватний коментар (видимий тільки для власника та суперадміна)
    private_comment = await invoice.add_comment(
        "Це приватна нотатка",
        is_private=True
    )


# Отримати коментарі документа
async def example_get_comments():
    """Отримати і показати коментарі."""

    invoice = await Doc.get("Invoice", "INV-2026-001")

    # Отримати всі коментарі
    comments = await invoice.get_comments()
    print(f"Коментарів: {len(comments)}")

    for comment in comments:
        privacy = " (приватний)" if comment.is_private else ""
        print(f"{comment.author_name}: {comment.text}{privacy}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. ЛОГУВАННЯ АКТИВНОСТІ
# ─────────────────────────────────────────────────────────────────────────────

from grunt import log_activity, get_activity_log

# Залогувати дію на документі
async def example_log_activity():
    """Залогувати дію для аудиту."""

    invoice = await Doc.get("Invoice", "INV-2026-001")

    # Залогувати дію
    await log_activity(
        doctype="Invoice",
        doc_id=invoice["id"],
        action="submitted",
        details={
            "old_status": "Draft",
            "new_status": "Submitted",
            "submitted_by": "accounting@company.com"
        }
    )

    # Залогувати видалення
    await log_activity(
        doctype="Invoice",
        doc_id=invoice["id"],
        action="deleted",
        details={"reason": "Duplicate entry"}
    )


# Отримати лог активності
async def example_get_activity_log():
    """Отримати історію активності документа."""

    invoice = await Doc.get("Invoice", "INV-2026-001")

    # Отримати останні 50 дій
    activity = await get_activity_log(
        doctype="Invoice",
        doc_id=invoice["id"],
        limit=50
    )

    for entry in activity:
        print(f"{entry.action} by {entry.user_email} at {entry.created_at}")
        if entry.details:
            print(f"  Details: {entry.details}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. МАСОВІ ОПЕРАЦІЇ (BATCH)
# ─────────────────────────────────────────────────────────────────────────────

# Встановити одне значення для кількох документів
async def example_set_value_batch():
    """Масово оновити значення поля для групи документів."""

    # Отримати список потрібних рахунків
    invoice_ids = ["INV-001", "INV-002", "INV-003", "INV-004", "INV-005"]

    # Встановити статус "Paid" для всіх
    count = await Doc.set_value_batch(
        doctype="Invoice",
        field="status",
        value="Paid",
        doc_ids=invoice_ids
    )

    print(f"✅ Updated {count}/{len(invoice_ids)} invoices to 'Paid'")

    # Масово встановити дату оплати
    from datetime import datetime

    payment_date = datetime.now().isoformat()
    count = await Doc.set_value_batch(
        doctype="Invoice",
        field="payment_date",
        value=payment_date,
        doc_ids=invoice_ids
    )

    # Масово встановити відповідального
    count = await Doc.set_value_batch(
        doctype="Invoice",
        field="owner",
        value="accounting@company.com",
        doc_ids=invoice_ids
    )


# Видалити кілька документів
async def example_delete_many():
    """Видалити групу документів."""

    # Отримати список для видалення
    old_invoices = await Doc.list(
        "Invoice",
        filters={"status": "Cancelled", "date__lt": "2023-01-01"},
        limit=1000
    )

    invoice_ids = [inv["id"] for inv in old_invoices]

    # Видалити їх
    deleted_count = await Doc.delete_many(
        doctype="Invoice",
        doc_ids=invoice_ids
    )

    print(f"✅ Deleted {deleted_count} cancelled invoices")


# ─────────────────────────────────────────────────────────────────────────────
# 9. РЕАЛЬНІ ПРИКЛАДИ З КОМЕНТАРЯМИ ТА АКТИВНІСТЮ
# ─────────────────────────────────────────────────────────────────────────────

# Приклад: Автоматизований workflow із коментарями
async def example_workflow_with_comments():
    """Приклад: замовлення проходить через approve-reject workflow."""

    order = await Doc.get("Order", "ORD-2026-001")

    # Перевірити дозволи
    if not await can_write("Order", order["id"]):
        throw("You don't have permission to approve orders")

    # Перевірити валідність
    if order["amount"] <= 0:
        throw("Order amount must be positive")

    # Додати коментар
    await order.add_comment("Order received and queued for approval")

    # Залогувати дію
    await log_activity(
        doctype="Order",
        doc_id=order["id"],
        action="received",
        details={"amount": order["amount"], "customer": order["customer_name"]}
    )

    # Оновити статус
    order["status"] = "Pending Review"
    await order.save()

    # Додати коментар про дію
    await order.add_comment("Order status updated to 'Pending Review'")

    # Залогувати оновлення
    await log_activity(
        doctype="Order",
        doc_id=order["id"],
        action="status_changed",
        details={"new_status": "Pending Review"}
    )

    # Відправити сповіщення
    await notify(
        title="Order Received",
        message=f"Order {order['name']} for {order['customer_name']} ready for review",
        doctype="Order",
        doc_id=order["id"]
    )


# Приклад: Масовий import з логуванням
async def example_bulk_import_with_logging():
    """Приклад: import 1000 рахунків із логуванням."""

    import csv
    from datetime import datetime

    imported_count = 0
    failed_count = 0

    # Читати CSV файл
    with open("invoices.csv", "r") as f:
        reader = csv.DictReader(f)
        invoice_ids = []

        for row in reader:
            try:
                # Створити рахунок
                invoice = await Doc.create("Invoice", {
                    "customer": row["customer"],
                    "amount": float(row["amount"]),
                    "date": row["date"],
                    "status": "Draft"
                })

                invoice_ids.append(invoice["id"])
                imported_count += 1

                # Залогувати успішне створення
                await log_activity(
                    doctype="Invoice",
                    doc_id=invoice["id"],
                    action="imported",
                    details={"source": "csv_import", "customer": row["customer"]}
                )

            except Exception as e:
                failed_count += 1
                # Залогувати помилку
                import structlog
                logger = structlog.get_logger()
                logger.error("import_failed", row=row, error=str(e))

    # Після імпорту - масово встановити дату імпорту
    if invoice_ids:
        await Doc.set_value_batch(
            doctype="Invoice",
            field="import_date",
            value=datetime.now().isoformat(),
            doc_ids=invoice_ids
        )

    msgprint(
        f"✅ Import complete: {imported_count} created, {failed_count} failed",
        type="success"
    )



# ─────────────────────────────────────────────────────────────────────────────
# 8. TIPS & BEST PRACTICES
# ─────────────────────────────────────────────────────────────────────────────

"""
РЕКОМЕНДАЦІЇ ДЛЯ РОЗРОБНИКІВ:

1. Завжди перевіряйте дозволи перед операціями:
   if not await can_write("DocType", doc_id):
       throw("Немає прав")

2. Використовуйте try-except для обробки помилок:
   try:
       await doc.save()
   except Exception as e:
       throw(f"Помилка збереження: {e}")

3. Показуйте інформативні повідомлення користувачам:
   msgprint("Документ збережено", type="success")

4. Не захаращуйте код - Grunt API робить його чистішим:
   # ХХХ Плохо:
   from grunt.core.document.service import DocumentService
   svc = DocumentService(session, engine)
   doc = await svc.get_document("User", user_id, user)

   # ✅ Добре:
   doc = await Doc.get("User", user_id)

5. Використовуйте фільтри при отриманні списків:
   invoices = await Doc.list("Invoice", {"status": "Pending"})

6. Кешируйте результати якщо їх будете використовувати кілька разів:
   user = await Doc.get("User", user_id)
   name = user['full_name']
   email = user['email']
   # Замість кількох вызовів get_value()

7. Завжди проверяйте існування документів перед операціями:
   if await db.exists("Contract", contract_id):
       contract = await Doc.get("Contract", contract_id)
   else:
       throw("Контракт не знайдено")
"""

# ─────────────────────────────────────────────────────────────────────────────
# КОНТАКТИ І ДОПОМОГА
# ─────────────────────────────────────────────────────────────────────────────

"""
Для більшої інформації див.:
- docs/api.md — повна документація API
- examples/ — готові примеры
- tests/ — тести з прикладами використання

Питання? Откройте issue на GitHub!
"""
