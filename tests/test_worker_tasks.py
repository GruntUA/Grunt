"""The worker process must know every task the web app can enqueue."""

from __future__ import annotations

from pathlib import Path

from grunt.tasks.worker import _task_modules, broker, import_task_modules


def test_framework_task_modules_are_found():
    import grunt

    found = set(_task_modules(Path(grunt.__file__).parent))
    assert {"grunt.email.tasks", "grunt.tasks.retention", "grunt.reports.delivery"} <= found
    assert not any(".tests." in m for m in found)


def test_scheduled_framework_tasks_are_registered():
    import_task_modules()
    names = set(broker.get_all_tasks())
    assert {
        "grunt.email.tasks:process_email_queue",
        "grunt.email.tasks:send_notification_digest",
        "grunt.tasks.retention:purge_expired_documents",
        "grunt.tasks.todo_reminders:send_due_reminders",
    } <= names


def test_app_task_modules_are_imported(tmp_path):
    pkg = tmp_path / "demo_app" / "demo_app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "tasks.py").write_text(
        "from grunt.tasks.broker import task\n\n\n@task\nasync def ping():\n    return 1\n"
    )
    assert "demo_app.tasks" in import_task_modules(tmp_path)
    assert "demo_app.tasks:ping" in broker.get_all_tasks()
