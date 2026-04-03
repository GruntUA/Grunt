
import asyncio
import click
import subprocess
import shutil
from contextlib import asynccontextmanager
from pathlib import Path


@click.group()
def cli():
    """Ґрунт CLI — інструмент управління фреймворком."""
    pass


# ── Shared helpers ────────────────────────────────────────────────────────────


@asynccontextmanager
async def _site_session(site: str | None):
    """Async context manager: initialise site, load DocType registry, yield session."""
    from grunt.core.site.manager import site_manager, current_site  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.startup import load_core_doctypes  # noqa: PLC0415

    target_site = site or (site_manager.get_sites() or [None])[0]
    if target_site is None:
        click.echo("Помилка: сайт не знайдено.", err=True)
        raise SystemExit(1)

    token = current_site.set(target_site)
    try:
        eng = site_manager.get_engine(target_site)
        maker = site_manager.get_session_maker(target_site)
        async with maker() as session:
            await doctype_registry.load_all(session)
            await load_core_doctypes(session, eng)
            yield session, eng
    finally:
        current_site.reset(token)


# ── Top-level commands ────────────────────────────────────────────────────────


@cli.command()
def init():
    """Ініціалізація проєкту (створення .env, БД та адміна)."""
    click.echo("Ініціалізація Ґрунт...")
    click.echo("Готово.")


@cli.command()
@click.option("--port", default=8000, help="Порт для API")
@click.option("--reload", is_flag=True, help="Режим перезавантаження")
def serve(port, reload):
    """Запуск сервера FastAPI."""
    click.echo(f"Запуск сервера на порту {port}...")
    cmd = ["uvicorn", "grunt.main:app", "--port", str(port)]
    if reload:
        cmd += [
            "--reload",
            "--reload-include", "*.js",
            "--reload-include", "*.json",
            "--reload-dir", str(Path(__file__).parents[3]),  # backend/
        ]
        grunt_apps = Path("grunt_apps")
        if grunt_apps.exists():
            cmd += ["--reload-dir", str(grunt_apps)]
    subprocess.run(cmd)


@cli.command()
def worker():
    """Запуск воркера фонових завдань (TaskIQ)."""
    click.echo("Запуск воркера TaskIQ...")
    from grunt.core.tasks.registry import discover_tasks  # noqa: PLC0415

    apps_dir = Path("grunt_apps")
    discover_tasks(apps_dir)
    subprocess.run(["taskiq", "worker", "grunt.core.tasks.broker:broker"])


# ── User management group ─────────────────────────────────────────────────────


@cli.group("users")
def users_group():
    """Керування користувачами."""
    pass


@users_group.command("create")
@click.option("--email", prompt="Email")
@click.option("--password", prompt="Пароль", hide_input=True, confirmation_prompt=True)
@click.option("--full-name", prompt="Повне ім'я")
@click.option("--site", default=None, help="Назва сайту")
def users_create(email, password, full_name, site):
    """Створити нового користувача."""

    async def _run():
        from grunt.core.auth.service import create_user, get_user_by_email  # noqa: PLC0415

        async with _site_session(site) as (session, _eng):
            if await get_user_by_email(email, session) is not None:
                click.echo(f"Помилка: користувач '{email}' вже існує.", err=True)
                raise SystemExit(1)
            user = await create_user(email, password, full_name, session)
            await session.commit()

        label = "superadmin" if user.is_superadmin else "user"
        click.echo(f"Створено {label}: {user.email} ({user.full_name})")

    asyncio.run(_run())


@users_group.command("list")
@click.option("--site", default=None, help="Назва сайту")
def users_list(site):
    """Показати список всіх користувачів."""

    async def _run():
        from grunt.core.auth.service import list_users  # noqa: PLC0415

        async with _site_session(site) as (session, _eng):
            users = await list_users(session)

        if not users:
            click.echo("Користувачів немає.")
            return

        click.echo(f"{'Email':<35} {'Ім\'я':<25} {'Ролі':<20} Суперадмін")
        click.echo("-" * 90)
        for u in users:
            roles = ", ".join(u.roles) or "—"
            superadmin = "так" if u.is_superadmin else ""
            click.echo(f"{u.email:<35} {u.full_name:<25} {roles:<20} {superadmin}")

    asyncio.run(_run())


@users_group.command("set-password")
@click.argument("email")
@click.option("--password", prompt="Новий пароль", hide_input=True, confirmation_prompt=True)
@click.option("--site", default=None, help="Назва сайту")
def users_set_password(email, password, site):
    """Змінити пароль користувача."""

    async def _run():
        from grunt.core.auth.service import get_user_by_email, hash_password, _user_table  # noqa: PLC0415
        from sqlalchemy import update  # noqa: PLC0415

        async with _site_session(site) as (session, _eng):
            user = await get_user_by_email(email, session)
            if user is None:
                click.echo(f"Помилка: користувача '{email}' не знайдено.", err=True)
                raise SystemExit(1)

            table = _user_table()
            await session.execute(
                update(table)
                .where(table.c.id == user.id)
                .values(hashed_password=hash_password(password))
            )
            await session.commit()

        click.echo(f"Пароль змінено для {email}.")

    asyncio.run(_run())


# ── DB group ─────────────────────────────────────────────────────────────────


@cli.group("db")
def db_group():
    """Команди управління базою даних."""
    pass


@db_group.command("migrate")
def db_migrate():
    """Запустити Alembic міграції (upgrade head)."""
    click.echo("Запуск міграцій...")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=False,
    )
    raise SystemExit(result.returncode)


@db_group.command("backup")
@click.option("--output", "-o", default=None, help="Файл для резервної копії (за замовчуванням: grunt_backup_<timestamp>.sql)")
@click.option("--site", default=None, help="Назва сайту")
def db_backup(output, site):
    """Створити резервну копію бази даних (pg_dump або sqlite3)."""
    from datetime import datetime  # noqa: PLC0415

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_name = f"grunt_backup_{timestamp}.sql"
    out_path = output or default_name

    async def _run():
        from grunt.config import settings  # noqa: PLC0415

        db_url: str = settings.database_url  # type: ignore[attr-defined]

        if db_url.startswith("postgresql"):
            if shutil.which("pg_dump") is None:
                click.echo("Помилка: pg_dump не знайдено.", err=True)
                raise SystemExit(1)
            # Extract connection params from URL
            result = subprocess.run(
                ["pg_dump", db_url, "--file", out_path],
                capture_output=False,
            )
            if result.returncode == 0:
                click.echo(f"Резервна копія збережена: {out_path}")
            raise SystemExit(result.returncode)

        elif db_url.startswith("sqlite"):
            # sqlite:///path/to/db.sqlite3
            db_file = db_url.replace("sqlite:///", "").replace("sqlite://", "")
            if not Path(db_file).exists():
                click.echo(f"Помилка: файл БД не знайдено: {db_file}", err=True)
                raise SystemExit(1)
            if shutil.which("sqlite3") is not None:
                result = subprocess.run(
                    ["sqlite3", db_file, f".output {out_path}", ".dump", ".quit"],
                    capture_output=False,
                )
                if result.returncode == 0:
                    click.echo(f"Резервна копія збережена: {out_path}")
                raise SystemExit(result.returncode)
            else:
                # Fallback: file copy
                shutil.copy2(db_file, out_path)
                click.echo(f"Файл БД скопійовано: {out_path}")
        else:
            click.echo(f"Непідтримуваний тип БД: {db_url}", err=True)
            raise SystemExit(1)

    asyncio.run(_run())


# ── create-app command ────────────────────────────────────────────────────────


@cli.command("create-app")
@click.argument("name")
def create_app(name: str):
    """Створити новий Grunt додаток з базовою структурою.

    NAME — назва додатку (snake_case), наприклад: my_crm
    """
    app_dir = Path("grunt_apps") / name
    if app_dir.exists():
        click.echo(f"Помилка: директорія '{app_dir}' вже існує.", err=True)
        raise SystemExit(1)

    label = name.replace("_", " ").title()

    # Scaffold directory structure
    (app_dir / "doctypes").mkdir(parents=True)
    (app_dir / "tasks").mkdir(parents=True)
    (app_dir / "hooks").mkdir(parents=True)

    # __init__.py
    (app_dir / "__init__.py").write_text(
        f'"""Grunt app: {label}"""\n\n__version__ = "0.1.0"\n'
    )

    # app.json — app manifest
    (app_dir / "app.json").write_text(
        f'{{\n  "name": "{name}",\n  "label": "{label}",\n  "version": "0.1.0",\n'
        f'  "description": "{label} Grunt app",\n  "author": ""\n}}\n'
    )

    # tasks/__init__.py
    (app_dir / "tasks" / "__init__.py").write_text("")

    # tasks/tasks.py — sample task
    (app_dir / "tasks" / "tasks.py").write_text(
        f'"""Background tasks for {label}."""\nfrom grunt.core.tasks.broker import retryable_task\n\n\n'
        f'# @retryable_task()\n# async def my_task():\n#     pass\n'
    )

    # hooks/__init__.py
    (app_dir / "hooks" / "__init__.py").write_text("")

    # hooks/hooks.py — sample hooks
    (app_dir / "hooks" / "hooks.py").write_text(
        f'"""Hooks for {label}."""\n\n\n'
        f'# Register hooks in grunt_apps/{name}/hooks/hooks.py\n'
        f'# Example:\n'
        f'# from grunt.core.hooks import on\n'
        f'#\n'
        f'# @on("after_insert", doctype="MyDocType")\n'
        f'# async def handle_insert(doc, user, **kwargs):\n'
        f'#     pass\n'
    )

    click.echo(f"Додаток '{name}' створено в {app_dir}/")
    click.echo("Структура:")
    for p in sorted(app_dir.rglob("*")):
        click.echo(f"  {p.relative_to(app_dir.parent)}")


# ── app group ────────────────────────────────────────────────────────────────


@cli.group("app")
def app_group():
    """Керування встановленими додатками."""
    pass


@app_group.command("install")
@click.argument("name")
@click.option("--site", default=None, help="Назва сайту")
def app_install(name: str, site: str | None):
    """Встановити додаток та одразу зареєструвати його workspace."""

    async def _run():
        import json  # noqa: PLC0415

        from grunt.core.site.manager import site_manager, current_site  # noqa: PLC0415
        from grunt.core.startup import load_core_doctypes, seed_app_workspaces  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.core.db.base import Base  # noqa: PLC0415

        target_site = site or (site_manager.get_sites() or [None])[0]
        if target_site is None:
            click.echo("Помилка: сайт не знайдено.", err=True)
            raise SystemExit(1)

        # Validate app exists
        app_dir = site_manager.bench_dir / "apps" / name
        app_json = app_dir / "app.json"
        if not app_dir.is_dir():
            click.echo(f"Помилка: директорія '{app_dir}' не існує.", err=True)
            raise SystemExit(1)
        if not app_json.exists():
            click.echo(f"Помилка: '{app_json}' не знайдено.", err=True)
            raise SystemExit(1)

        app_meta = json.loads(app_json.read_text(encoding="utf-8"))

        # Update grunt.site installed_apps
        site_file = site_manager.sites_dir / target_site / "grunt.site"
        site_config = json.loads(site_file.read_text(encoding="utf-8"))
        installed = site_config.get("installed_apps", [])
        if name not in installed:
            installed.append(name)
            site_config["installed_apps"] = installed
            site_file.write_text(json.dumps(site_config, ensure_ascii=False, indent=2), encoding="utf-8")

        # Seed workspace immediately (no server restart needed)
        token = current_site.set(target_site)
        try:
            eng = site_manager.get_engine(target_site)
            maker = site_manager.get_session_maker(target_site)

            async with eng.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async with maker() as session:
                await load_core_doctypes(session, eng)
                await doctype_registry.load_all(session)
                await seed_app_workspaces(session, target_site)
                await session.commit()
        finally:
            current_site.reset(token)

        title = app_meta.get("title", name)
        click.echo(f"✓ Додаток {title} встановлено на сайт {target_site}")
        all_apps = site_config.get("installed_apps", [])
        click.echo(f"  Додатки: {', '.join(all_apps)}")

    asyncio.run(_run())


@app_group.command("uninstall")
@click.argument("name")
@click.option("--site", default=None, help="Назва сайту")
def app_uninstall(name: str, site: str | None):
    """Видалити додаток із сайту (workspace та запис зберігаються)."""

    async def _run():
        import json  # noqa: PLC0415

        from grunt.core.site.manager import site_manager  # noqa: PLC0415

        target_site = site or (site_manager.get_sites() or [None])[0]
        if target_site is None:
            click.echo("Помилка: сайт не знайдено.", err=True)
            raise SystemExit(1)

        site_file = site_manager.sites_dir / target_site / "grunt.site"
        site_config = json.loads(site_file.read_text(encoding="utf-8"))
        installed = site_config.get("installed_apps", [])

        if name not in installed:
            click.echo(f"Помилка: додаток '{name}' не встановлено.", err=True)
            raise SystemExit(1)
        if name == "grunt":
            click.echo("Помилка: базовий додаток grunt не можна видалити.", err=True)
            raise SystemExit(1)

        installed.remove(name)
        site_config["installed_apps"] = installed
        site_file.write_text(json.dumps(site_config, ensure_ascii=False, indent=2), encoding="utf-8")

        click.echo(f"✓ Додаток '{name}' видалено з сайту {target_site}")
        click.echo(f"  Додатки: {', '.join(installed)}")

    asyncio.run(_run())


@app_group.command("list")
@click.option("--site", default=None, help="Назва сайту")
def app_list(site: str | None):
    """Показати встановлені додатки."""
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415
    from grunt.core.site.manager import site_manager  # noqa: PLC0415

    target_site = site or (site_manager.get_sites() or [None])[0]
    if target_site is None:
        click.echo("Помилка: сайт не знайдено.", err=True)
        raise SystemExit(1)

    site_file = site_manager.sites_dir / target_site / "grunt.site"
    site_config = json.loads(site_file.read_text(encoding="utf-8"))
    apps = site_config.get("installed_apps", [])
    click.echo(f"Сайт: {target_site}")
    for a in apps:
        click.echo(f"  • {a}")


# ── doctype group ─────────────────────────────────────────────────────────────


@cli.group("doctype")
def doctype_group():
    """Команди управління DocType."""
    pass


@doctype_group.command("sync")
@click.argument("name")
@click.option("--site", default=None, help="Назва сайту")
def doctype_sync(name: str, site: str | None):
    """Синхронізувати конкретний DocType зі схемою БД."""

    async def _run():
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.core.metadata.sync import sync_doctype  # noqa: PLC0415

        async with _site_session(site) as (session, eng):
            dt = await doctype_registry.get(name)
            await sync_doctype(dt, session, eng)
            await session.commit()
            click.echo(f"DocType '{name}' синхронізовано.")

    asyncio.run(_run())


@doctype_group.command("list")
@click.option("--site", default=None, help="Назва сайту")
def doctype_list(site: str | None):
    """Показати список всіх DocTypes."""

    async def _run():
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        async with _site_session(site) as (session, _eng):
            all_dts = doctype_registry.all()
            if not all_dts:
                click.echo("DocTypes не знайдено.")
                return
            click.echo(f"{'Назва':<35} {'Модуль':<20} {'Система'}")
            click.echo("-" * 65)
            for dt in sorted(all_dts, key=lambda d: d.name):
                is_sys = "так" if getattr(dt, "is_system", False) else ""
                click.echo(f"{dt.name:<35} {dt.module:<20} {is_sys}")

    asyncio.run(_run())


@doctype_group.command("scaffold")
@click.argument("name")
@click.option("--app", default="web", help="Папка app куди розмістити DocType (за замовчуванням: web)")
@click.option("--module", default=None, help="Модуль (за замовчуванням: app name)")
@click.option("--force", is_flag=True, help="Перезаписати існуючі файли")
def doctype_scaffold(name: str, app: str, module: str, force: bool):
    """Створити новий DocType з шаблонами.

    Генерує папку структури:
        {app}/doctypes/{Name}/
            ├── {Name}.json          # метадані DocType
            ├── {Name}.py            # контроллер з auto-generated типами
            ├── {Name}.js            # client script
            └── __init__.py
    """
    import json  # noqa: PLC0415
    from datetime import datetime  # noqa: PLC0415

    # Validate name
    if not name or name[0].islower():
        click.echo("Помилка: ім'я DocType повинно починатися з великої літери.", err=True)
        raise SystemExit(1)

    app_path = Path("grunt_apps") / app
    if not app_path.exists():
        click.echo(f"Помилка: app '{app}' не знайдено по шляху {app_path}.", err=True)
        raise SystemExit(1)

    doctype_dir = app_path / "doctypes" / name
    if doctype_dir.exists() and not force:
        click.echo(f"Помилка: папка {doctype_dir} вже існує. Використайте --force для перезаписання.", err=True)
        raise SystemExit(1)

    doctype_dir.mkdir(parents=True, exist_ok=True)

    # Module name (default to app name)
    module_name = module or app

    # JSON template
    json_content = f"""{{
  "name": "{name}",
  "label": "{name}",
  "module": "{module_name}",
  "doctype": "DocType",
  "is_system": false,
  "fields": [
    {{"fieldname": "name", "label": "Назва", "fieldtype": "Data", "required": true}}
  ]
}}"""

    # Write JSON first so we can read it to generate types
    json_file = doctype_dir / f"{name}.json"
    json_file.write_text(json_content, encoding="utf-8")

    # Parse JSON to get fields for type generation
    doctype_data = json.loads(json_content)
    type_hints = _generate_type_hints(name, doctype_data.get("fields", []))

    # Python controller template with auto-generated types
    py_content = f'''"""{name} controller.

Бізнес-логіка для DocType {name}.
"""

from __future__ import annotations

{type_hints}


class {name}Controller:
    """Контроллер для {name} документів."""

    async def before_save(self):
        """Викликається перед збереженням."""
        pass

    async def after_save(self):
        """Викликається після збереження."""
        pass

    async def before_delete(self):
        """Викликається перед видаленням."""
        pass
'''

    # JavaScript template
    js_content = f'''/**
 * {name} Client Script
 *
 * Викликається на UI сторінці при редагуванні {name}.
 */

function on_load(frm) {{
    // Код що виконується при завантаженні форми
    console.log('Loaded {name}', frm.doc)
}}

function on_save(frm) {{
    // Код що виконується при збереженні форми
    console.log('Saved {name}', frm.doc)
}}
'''

    # Write files
    py_file = doctype_dir / f"{name}.py"
    js_file = doctype_dir / f"{name}.js"
    init_file = doctype_dir / "__init__.py"

    py_file.write_text(py_content, encoding="utf-8")
    js_file.write_text(js_content, encoding="utf-8")
    init_file.write_text("", encoding="utf-8")

    # Try to show relative path, fallback to absolute
    try:
        rel_path = doctype_dir.relative_to(Path.cwd())
    except ValueError:
        rel_path = doctype_dir

    click.echo(f"✓ Створено DocType '{name}' в {rel_path}")
    click.echo(f"  ├── {name}.json")
    click.echo(f"  ├── {name}.py (з auto-generated типами)")
    click.echo(f"  ├── {name}.js")
    click.echo(f"  └── __init__.py")
    click.echo()
    click.echo("Наступні кроки:")
    click.echo(f"1. Відредагуйте {name}.json для визначення полів")
    click.echo(f"2. Запустіть: grunt doctype generate-types {name} --app {app}")
    click.echo(f"3. Запустіть: grunt serve --reload")
    click.echo(f"4. Перейдіть на http://localhost:8000/desk/list/{name}")


@doctype_group.command("generate-types")
@click.argument("name")
@click.option("--app", default="web", help="Папка app де знаходиться DocType")
def doctype_generate_types(name: str, app: str):
    """Регенерувати auto-generated типи для існуючого DocType.

    Читає JSON файл і оновлює type hints у .py контролері.
    """
    import json  # noqa: PLC0415

    app_path = Path("grunt_apps") / app
    doctype_dir = app_path / "doctypes" / name
    json_file = doctype_dir / f"{name}.json"
    py_file = doctype_dir / f"{name}.py"

    if not json_file.exists():
        click.echo(f"Помилка: DocType JSON не знайдено: {json_file}", err=True)
        raise SystemExit(1)

    if not py_file.exists():
        click.echo(f"Помилка: DocType контроллер не знайдено: {py_file}", err=True)
        raise SystemExit(1)

    # Read JSON and generate types
    doctype_data = json.loads(json_file.read_text(encoding="utf-8"))
    type_hints = _generate_type_hints(name, doctype_data.get("fields", []))

    # Read current Python file
    py_content = py_file.read_text(encoding="utf-8")

    # Remove old type hints block if exists
    if "# begin: auto-generated types" in py_content:
        start = py_content.find("# begin: auto-generated types")
        end = py_content.find("# end: auto-generated types")
        if start != -1 and end != -1:
            # Keep everything before begin marker and after end marker
            before = py_content[:start].rstrip()
            after = py_content[end:].split("\n", 1)[1] if "\n" in py_content[end:] else ""
            py_content = before + "\n\n" + type_hints + "\n\n" + after

            py_file.write_text(py_content, encoding="utf-8")
            click.echo(f"✓ Типи оновлено для {name}")
            return

    # If no marker found, insert after imports
    lines = py_content.split("\n")
    insert_pos = 0

    # Find position after __future__ imports and blank lines
    for i, line in enumerate(lines):
        if line.startswith("from __future__"):
            insert_pos = i + 1
        elif line.strip() and not line.startswith("from ") and not line.startswith("import "):
            break

    # Insert type hints after imports
    lines.insert(insert_pos + 1, "")
    lines.insert(insert_pos + 2, type_hints)
    lines.insert(insert_pos + 3, "")

    py_file.write_text("\n".join(lines), encoding="utf-8")
    click.echo(f"✓ Типи додано для {name}")


def _generate_type_hints(doctype_name: str, fields: list) -> str:
    """Generate auto-typed field annotations from a DocType definition.

    Maps fieldtype to Python type hints.
    """
    # Fieldtype to Python type mapping
    fieldtype_map = {
        "Data": "str | None",
        "Text": "str | None",
        "LongText": "str | None",
        "Int": "int | None",
        "Float": "float | None",
        "Check": "bool | None",
        "Date": "str | None",  # ISO date string
        "Datetime": "str | None",  # ISO datetime string
        "Time": "str | None",
        "Link": "str | None",
        "MultiLink": "list[str] | None",
        "Attach": "str | None",
        "Image": "str | None",
        "Select": "str | None",
        "RichText": "str | None",
        "JSON": "dict | None",
        "Code": "str | None",
        "Color": "str | None",
        "Signature": "str | None",
        "Geolocation": "str | None",
        "HTMLEditor": "str | None",
        "BarCode": "str | None",
        "Rating": "int | None",
        "Percent": "float | None",
        "Duration": "float | None",
    }

    # Collect field type annotations (skip structural fields)
    field_lines = []
    for field in fields:
        fieldname = field.get("fieldname", "")
        fieldtype = field.get("fieldtype", "Data")

        # Skip structural fields
        if fieldtype in ("Section", "Column", "Tab", "Table", "Empty"):
            continue

        # Skip standard fields
        if fieldname in ("name", "docstatus", "idx", "owner", "creation", "modified", "modified_by"):
            continue

        py_type = fieldtype_map.get(fieldtype, "Any | None")
        field_lines.append(f"\t\t{fieldname}: {py_type}")

    # Build the type hints block
    type_block = f"""# begin: auto-generated types
# This code is auto-generated. Do not modify anything in this block.

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
	from typing import DF

	class {doctype_name}:
		\"\"\"Type hints for {doctype_name} fields.\"\"\"

{chr(10).join(field_lines) if field_lines else chr(9)*2 + 'name: str | None'}

# end: auto-generated types"""

    return type_block


if __name__ == "__main__":
    cli()
