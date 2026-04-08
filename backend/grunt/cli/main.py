
import asyncio
import click
import subprocess
import shutil
from contextlib import asynccontextmanager
from importlib.metadata import entry_points
from pathlib import Path


@click.group()
def cli():
    """Ґрунт CLI — інструмент управління фреймворком."""
    pass


def _load_plugins() -> None:
    """Discover and register CLI commands from installed Grunt apps.

    Apps declare their commands in pyproject.toml:

        [project.entry-points."grunt.commands"]
        myapp = "myapp.cli:cli"

    The registered group/command is added to the top-level ``cli`` group.
    """
    for ep in entry_points(group="grunt.commands"):
        try:
            cmd = ep.load()
            if isinstance(cmd, (click.BaseCommand,)):
                cli.add_command(cmd, name=ep.name)
        except Exception as exc:  # noqa: BLE001
            click.echo(f"[warn] grunt.commands plugin '{ep.name}' failed to load: {exc}", err=True)


_load_plugins()


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
@click.option("--no-git", is_flag=True, default=False, help="Не ініціалізувати git репозиторій")
@click.option("--dest", default=None, help="Директорія для створення додатку (за замовчуванням: grunt_apps/)")
def create_app(name: str, no_git: bool, dest: str | None):
    """Інтерактивно створити новий Grunt додаток.

    NAME — назва додатку (snake_case), наприклад: my_crm
    """
    from grunt.utils.boilerplate import make_boilerplate  # noqa: PLC0415

    dest_path = Path(dest) if dest else Path("grunt_apps")
    dest_path.mkdir(parents=True, exist_ok=True)
    make_boilerplate(dest_path, name, no_git=no_git)


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
        from grunt.core.metadata.compiler import sync_table  # noqa: PLC0415

        async with _site_session(site) as (session, eng):
            dt = await doctype_registry.get(name)
            await sync_table(dt, eng, session=session)
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
def doctype_scaffold(name: str, app: str, module: str | None, force: bool):
    """Створити новий DocType з шаблонами.

    Генерує папку структури:
        {app}/doctypes/{Name}/
            ├── {Name}.json          # метадані DocType
            ├── {Name}.py            # контролер з auto-generated типами
            ├── {Name}.js            # client script
            └── __init__.py
    """
    import json  # noqa: PLC0415
    from grunt.utils.codegen import build_controller_context, render_template  # noqa: PLC0415

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

    module_name = module or app
    initial_fields = [{"fieldname": "name", "label": "Назва", "fieldtype": "Data", "required": True}]

    # 1. JSON metadata
    json_content = {
        "name": name,
        "label": name,
        "module": module_name,
        "doctype": "DocType",
        "is_system": False,
        "fields": initial_fields,
    }
    json_file = doctype_dir / f"{name}.json"
    json_file.write_text(json.dumps(json_content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 2. Python controller via Jinja template
    py_ctx = build_controller_context(name, initial_fields)
    py_file = doctype_dir / f"{name}.py"
    py_file.write_text(render_template("doctype/controller.py.jinja", py_ctx), encoding="utf-8")

    # 3. JS client script via Jinja template
    js_file = doctype_dir / f"{name}.js"
    js_file.write_text(render_template("doctype/client_script.js.jinja", {"name": name}), encoding="utf-8")

    # 4. __init__.py
    (doctype_dir / "__init__.py").write_text("", encoding="utf-8")

    try:
        rel_path = doctype_dir.relative_to(Path.cwd())
    except ValueError:
        rel_path = doctype_dir

    click.echo(f"✓ Створено DocType '{name}' в {rel_path}")
    click.echo(f"  ├── {name}.json")
    click.echo(f"  ├── {name}.py  (controller з auto-generated типами)")
    click.echo(f"  ├── {name}.js  (client script)")
    click.echo(f"  └── __init__.py")
    click.echo()
    click.echo("Наступні кроки:")
    click.echo(f"1. Відредагуйте {name}.json для визначення полів")
    click.echo(f"2. Запустіть: grunt doctype sync-types {name} --app {app}")
    click.echo(f"3. Запустіть: grunt serve --reload")


@doctype_group.command("sync-types")
@click.argument("name")
@click.option("--app", default="web", help="Папка app де знаходиться DocType")
@click.option("--all", "all_doctypes", is_flag=True, help="Оновити всі DocTypes в app")
def doctype_sync_types(name: str, app: str, all_doctypes: bool):
    """Оновити auto-generated типи в контролері на основі JSON метаданих.

    Замінює тільки блок між:
        # begin: auto-generated types
        # end: auto-generated types
    Решта коду контролера не чіпається.

    \b
    Приклади:
      grunt doctype sync-types Invoice --app crm
      grunt doctype sync-types --all --app crm
    """
    import json  # noqa: PLC0415
    from grunt.utils.codegen import sync_controller_types  # noqa: PLC0415

    app_path = Path("grunt_apps") / app

    if all_doctypes:
        updated = 0
        skipped = 0
        for json_file in sorted(app_path.glob("doctypes/*/*.json")):
            dt_name = json_file.stem
            py_file = json_file.parent / f"{dt_name}.py"
            if not py_file.exists():
                continue
            try:
                fields = json.loads(json_file.read_text(encoding="utf-8")).get("fields", [])
                changed = sync_controller_types(py_file, dt_name, fields)
                if changed:
                    click.echo(f"  ✓ {dt_name}")
                    updated += 1
                else:
                    skipped += 1
            except Exception as exc:
                click.echo(f"  ! {dt_name}: {exc}", err=True)
        click.echo(f"\nОновлено: {updated}, без змін: {skipped}")
        return

    json_file = app_path / "doctypes" / name / f"{name}.json"
    py_file = app_path / "doctypes" / name / f"{name}.py"

    if not json_file.exists():
        click.echo(f"Помилка: {json_file} не знайдено.", err=True)
        raise SystemExit(1)
    if not py_file.exists():
        click.echo(f"Помилка: {py_file} не знайдено.", err=True)
        raise SystemExit(1)

    fields = json.loads(json_file.read_text(encoding="utf-8")).get("fields", [])
    changed = sync_controller_types(py_file, name, fields)
    if changed:
        click.echo(f"✓ Типи оновлено: {py_file}")
    else:
        click.echo(f"Без змін: {py_file}")


if __name__ == "__main__":
    cli()
