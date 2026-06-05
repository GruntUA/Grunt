import json
import os
from pathlib import Path

import click


def _parse_skill_name(skill_md: Path) -> str | None:
    content = skill_md.read_text(encoding="utf-8")
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return None


def _claude_skills_dir() -> Path:
    return Path.home() / ".claude" / "skills"


def _install_app_skills(app_dir: Path) -> list[str]:
    skills_src = app_dir / "skills"
    if not skills_src.is_dir():
        return []

    lock_file = app_dir / "skills-lock.json"
    lock: dict = (
        json.loads(lock_file.read_text(encoding="utf-8"))
        if lock_file.exists()
        else {"version": 1, "skills": {}}
    )

    claude_skills = _claude_skills_dir()
    claude_skills.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    for skill_dir in sorted(skills_src.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            click.echo(f"  [skip] {skill_dir.name}: SKILL.md не знайдено")
            continue

        name = _parse_skill_name(skill_md)
        if not name:
            click.echo(f"  [skip] {skill_dir.name}: поле name: відсутнє у frontmatter")
            continue

        target = claude_skills / name
        if target.exists() or target.is_symlink():
            target.unlink()
        os.symlink(skill_dir.resolve(), target)

        lock["skills"][name] = {
            "sourceType": "local",
            "path": str(skill_dir.relative_to(app_dir)),
            "linkedTo": str(target),
        }
        installed.append(name)
        click.echo(f"  {click.style('✓', fg='green')} {name}  →  {target}")

    if installed:
        lock_file.write_text(json.dumps(lock, indent=2, ensure_ascii=False), encoding="utf-8")

    return installed


@click.group("skills")
def skills_group():
    """Керування AI скілами додатків."""
    pass


@skills_group.command("install")
@click.argument("app_name", required=False)
def skills_install(app_name: str | None):
    """Встановити скіли з додатку (або всіх додатків).

    APP_NAME — назва додатку (опційно). Якщо не вказано — сканує всі додатки.
    """
    from grunt.site.manager import site_manager  # noqa: PLC0415

    apps_dir = site_manager.bench_dir / "apps"

    if app_name:
        app_dirs = [apps_dir / app_name]
        if not app_dirs[0].is_dir():
            click.echo(f"Помилка: додаток '{app_name}' не знайдено.", err=True)
            raise SystemExit(1)
    else:
        app_dirs = sorted(d for d in apps_dir.iterdir() if d.is_dir() and not d.name.startswith("."))

    total: list[str] = []
    for app_dir in app_dirs:
        names = _install_app_skills(app_dir)
        if names:
            click.echo(f"[{app_dir.name}] встановлено: {', '.join(names)}")
        total.extend(names)

    if not total:
        click.echo("Скілів не знайдено.")
    else:
        click.echo(f"\n{click.style('✓', fg='green')} Всього встановлено: {len(total)} скіл(ів)")


@skills_group.command("uninstall")
@click.argument("skill_name")
def skills_uninstall(skill_name: str):
    """Видалити встановлений скіл (видаляє симлінк)."""
    from grunt.site.manager import site_manager  # noqa: PLC0415

    target = _claude_skills_dir() / skill_name
    if not target.exists() and not target.is_symlink():
        click.echo(f"Помилка: скіл '{skill_name}' не встановлено.", err=True)
        raise SystemExit(1)

    target.unlink()

    apps_dir = site_manager.bench_dir / "apps"
    for app_dir in apps_dir.iterdir():
        lock_file = app_dir / "skills-lock.json"
        if not lock_file.exists():
            continue
        lock = json.loads(lock_file.read_text(encoding="utf-8"))
        if skill_name in lock.get("skills", {}):
            del lock["skills"][skill_name]
            lock_file.write_text(json.dumps(lock, indent=2, ensure_ascii=False), encoding="utf-8")

    click.echo(f"{click.style('✓', fg='green')} Скіл '{skill_name}' видалено.")


@skills_group.command("list")
def skills_list():
    """Показати локальні скіли з усіх додатків."""
    from grunt.site.manager import site_manager  # noqa: PLC0415

    apps_dir = site_manager.bench_dir / "apps"
    found = False
    for app_dir in sorted(apps_dir.iterdir()):
        lock_file = app_dir / "skills-lock.json"
        if not lock_file.exists():
            continue
        lock = json.loads(lock_file.read_text(encoding="utf-8"))
        local_skills = {
            k: v for k, v in lock.get("skills", {}).items() if v.get("sourceType") == "local"
        }
        if not local_skills:
            continue
        found = True
        click.echo(f"\n[{app_dir.name}]")
        for name, meta in local_skills.items():
            linked = Path(meta.get("linkedTo", ""))
            status = (
                click.style("✓", fg="green")
                if linked.is_symlink()
                else click.style("✗ не встановлено", fg="red")
            )
            click.echo(f"  {status}  {name}  ({meta.get('path', '')})")

    if not found:
        click.echo("Немає локальних скілів.")
