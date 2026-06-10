import asyncio
from pathlib import Path

import click

from grunt.cli.utils import _site_session
from grunt.utils.strings import to_snake_case


@click.group("doctype")
def doctype_group():
    """Команди управління DocType."""
    pass


@doctype_group.command("sync")
@click.argument("name")
@click.option("--site", default=None, help="Назва сайту")
def doctype_sync(name: str, site: str | None):
    """Синхронізувати DocType: перечитати JSON з диску, оновити БД і схему таблиці."""

    async def _run():
        import json

        from grunt.metadata.doctype import DocType
        from grunt.metadata.registry import doctype_registry
        from grunt.startup.doctypes import _find_doctype_dirs

        # Find JSON file across all grunt/*/doctypes/ and app doctypes/
        json_file = None
        from grunt.site.manager import site_manager

        search_dirs = list(_find_doctype_dirs())
        # Also search installed app doctypes
        if site_manager.bench_dir:
            for app_dir in sorted((site_manager.bench_dir / "apps").iterdir()):
                dt_dir = app_dir / app_dir.name / "doctypes"
                if dt_dir.is_dir():
                    search_dirs.append(dt_dir)
                dt_dir2 = app_dir / "doctypes"
                if dt_dir2.is_dir():
                    search_dirs.append(dt_dir2)

        for dt_dir in search_dirs:
            candidate = dt_dir / name / f"{name}.json"
            if candidate.exists():
                json_file = candidate
                break
            # Fallback: snake_case filename
            snake = to_snake_case(name)
            candidate2 = dt_dir / name / f"{snake}.json"
            if candidate2.exists():
                json_file = candidate2
                break

        if json_file is None:
            click.echo(f"Помилка: JSON-файл для '{name}' не знайдено.", err=True)
            raise SystemExit(1)

        dt_data = json.loads(json_file.read_text(encoding="utf-8"))
        dt = DocType.model_validate(dt_data)

        async with _site_session(site) as (session, eng):
            from sqlalchemy import select

            from grunt.db.system_tables import GruntMetaDoctype

            exists = await session.scalar(
                select(GruntMetaDoctype.c.name).where(GruntMetaDoctype.c.name == dt.name)
            )
            if exists:
                await doctype_registry.update(dt, session, eng)
                action = "оновлено"
            else:
                await doctype_registry.register(dt, session, eng)
                action = "зареєстровано"
            await session.commit()

        click.echo(f"DocType '{name}' {action} з {json_file.relative_to(json_file.parents[3])}.")

    asyncio.run(_run())


@doctype_group.command("list")
@click.option("--site", default=None, help="Назва сайту")
def doctype_list(site: str | None):
    """Показати список всіх DocTypes."""

    async def _run():
        from grunt.metadata.registry import doctype_registry

        async with _site_session(site) as (session, _eng):
            all_dts = await doctype_registry.list_all()
            if not all_dts:
                click.echo("DocTypes не знайдено.")
                return
            click.echo(f"{'Назва':<35} {'Модуль':<20}")
            click.echo("-" * 55)
            for dt in sorted(all_dts, key=lambda d: d.name):
                click.echo(f"{dt.name:<35} {dt.module:<20}")

    asyncio.run(_run())


@doctype_group.command("scaffold")
@click.argument("name")
@click.option(
    "--app", default="web", help="Папка app куди розмістити DocType (за замовчуванням: web)"
)
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
    import json

    from grunt.utils.codegen import build_controller_context, render_template

    if not name or name[0].islower():
        click.echo("Помилка: ім'я DocType повинно починатися з великої літери.", err=True)
        raise SystemExit(1)

    from grunt.site.manager import site_manager

    app_path = site_manager.bench_dir / "apps" / app
    if not app_path.exists():
        click.echo(f"Помилка: app '{app}' не знайдено по шляху {app_path}.", err=True)
        raise SystemExit(1)

    doctype_dir = app_path / "doctypes" / name
    if doctype_dir.exists() and not force:
        click.echo(
            f"Помилка: папка {doctype_dir} вже існує. Використайте --force для перезаписання.",
            err=True,
        )
        raise SystemExit(1)

    doctype_dir.mkdir(parents=True, exist_ok=True)

    module_name = module or app
    initial_fields = [
        {"fieldname": "name", "label": "Назва", "fieldtype": "Data", "required": True}
    ]

    # 1. JSON metadata
    json_content = {
        "name": name,
        "label": name,
        "module": module_name,
        "doctype": "DocType",
        "fields": initial_fields,
    }
    json_file = doctype_dir / f"{to_snake_case(name)}.json"
    json_file.write_text(
        json.dumps(json_content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 2. Python controller via Jinja template
    py_ctx = build_controller_context(name, initial_fields)
    py_file = doctype_dir / f"{to_snake_case(name)}.py"
    py_file.write_text(render_template("doctype/controller.py.jinja", py_ctx), encoding="utf-8")

    # 3. JS client script via Jinja template
    js_file = doctype_dir / f"{to_snake_case(name)}.js"
    js_file.write_text(
        render_template("doctype/client_script.js.jinja", {"name": name}), encoding="utf-8"
    )

    # 4. __init__.py
    (doctype_dir / "__init__.py").write_text("", encoding="utf-8")

    try:
        rel_path = doctype_dir.relative_to(Path.cwd())
    except ValueError:
        rel_path = doctype_dir

    click.echo(f"✓ Створено DocType '{name}' в {rel_path}")
    click.echo(f"  ├── {to_snake_case(name)}.json")
    click.echo(f"  ├── {to_snake_case(name)}.py  (controller з auto-generated типами)")
    click.echo(f"  ├── {to_snake_case(name)}.js  (client script)")
    click.echo("  └── __init__.py")
    click.echo()
    click.echo("Наступні кроки:")
    click.echo(f"1. Відредагуйте {name}.json для визначення полів")
    click.echo(f"2. Запустіть: grunt doctype sync-types {name} --app {app}")
    click.echo("3. Запустіть: grunt serve --reload")


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
    import json

    from grunt.site.manager import site_manager
    from grunt.utils.codegen import sync_controller_types

    app_path = site_manager.bench_dir / "apps" / app

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
