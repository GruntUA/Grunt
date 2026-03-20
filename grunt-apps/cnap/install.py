"""
Встановлює ЦНАП app через API Ґрунту.
Запуск: python grunt-apps/cnap/install.py
Сервер має бути запущений на :8000.
"""

import json
import sys
from pathlib import Path

import httpx

API = "http://localhost:8000"


def get_token() -> str:
    """Читає ~/.grunt_token або питає логін."""
    token_file = Path.home() / ".grunt_token"
    if token_file.exists():
        return token_file.read_text().strip()
    print("Потрібна авторизація.")
    email = input("Email: ")
    password = input("Password: ")
    r = httpx.post(
        f"{API}/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    token_file.write_text(token)
    return token


def install() -> None:
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    app_dir = Path(__file__).parent

    # 1. Створити ролі
    roles = ["ЦНАП Оператор", "ЦНАП Керівник", "ЦНАП Адміністратор"]
    print("\n--- Створення ролей ---")
    for role in roles:
        r = httpx.post(
            f"{API}/api/v1/auth/roles",
            json={"name": role, "description": f"Роль: {role}"},
            headers=headers,
        )
        if r.status_code in (200, 201):
            print(f"  + {role}")
        elif r.status_code == 409:
            print(f"  ~ {role} (вже існує)")
        else:
            print(f"  ! {role}: {r.text}")

    # 2. Встановити DocTypes (порядок важливий через Link-залежності)
    doctype_order = [
        "ServiceCategory",
        "AdminService",
        "Applicant",
        "AppealDocument",
        "Appeal",
    ]
    print("\n--- Встановлення DocTypes ---")
    doctypes_dir = app_dir / "registry" / "doctypes"
    for name in doctype_order:
        dt_file = doctypes_dir / f"{name}.json"
        if not dt_file.exists():
            print(f"  ! {name}.json не знайдено")
            continue
        dt = json.loads(dt_file.read_text(encoding="utf-8"))
        r = httpx.post(
            f"{API}/api/v1/meta/doctypes",
            json=dt,
            headers=headers,
            timeout=30,
        )
        if r.status_code in (200, 201):
            print(f"  + {name}")
        elif r.status_code == 409:
            r2 = httpx.put(
                f"{API}/api/v1/meta/doctypes/{name}",
                json=dt,
                headers=headers,
                timeout=30,
            )
            print(
                f"  ~ {name} (оновлено)"
                if r2.status_code == 200
                else f"  ! {name}: {r2.text}"
            )
        else:
            print(f"  ! {name}: {r.text}")

    # 3. Завантажити fixtures
    print("\n--- Завантаження довідників ---")
    fixtures_dir = app_dir / "registry" / "fixtures"
    for fixture_file in sorted(fixtures_dir.glob("*.json")):
        data = json.loads(fixture_file.read_text(encoding="utf-8"))
        doctype = data.get("doctype")
        records = data.get("records", [])
        ok = 0
        for rec in records:
            r = httpx.post(
                f"{API}/api/v1/docs/{doctype}",
                json=rec,
                headers=headers,
            )
            if r.status_code in (200, 201):
                ok += 1
        print(f"  + {fixture_file.stem}: {ok}/{len(records)} записів")

    # 4. Встановити звіти
    print("\n--- Встановлення звітів ---")
    reports_dir = app_dir / "registry" / "reports"
    if reports_dir.exists():
        for report_file in reports_dir.glob("*.json"):
            report = json.loads(report_file.read_text(encoding="utf-8"))
            r = httpx.post(
                f"{API}/api/v1/reports",
                json=report,
                headers=headers,
            )
            if r.status_code in (200, 201, 409):
                print(f"  + {report['title']}")
            else:
                print(f"  ! {report['title']}: {r.text}")

    # 5. Зареєструвати сторінки додатку
    print("\n--- Реєстрація сторінок ---")
    app_pages = [
        {
            "route": "/dashboard",
            "title": "Дашборд",
            "icon": "📊",
            "component": "cnap/CnapDashboard",
            "app": "cnap",
            "sidebar_section": "ЦНАП",
            "sidebar_order": 0,
            "is_default_home": True,
        },
    ]
    for page in app_pages:
        r = httpx.post(
            f"{API}/api/v1/pages",
            json=page,
            headers=headers,
        )
        if r.status_code in (200, 201):
            print(f"  + {page['title']} ({page['route']})")
        else:
            print(f"  ! {page['title']}: {r.text}")

    print("\n=== ЦНАП app встановлено! ===")
    print("\nПерейди до:")
    print("  /dashboard      -> Дашборд ЦНАП")
    print("  /Appeal         -> Реєстр звернень")
    print("  /Applicant      -> Заявники")
    print("  /AdminService   -> Послуги")
    print("  /reports        -> Звіти")


if __name__ == "__main__":
    install()
