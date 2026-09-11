import json
from typing import Any

from grunt.hooks import on_doc
from grunt.log import log
from grunt.site.manager import site_manager


@on_doc("PrintFormat", "after_save")
async def save_print_format_to_app(doc: dict[str, Any], **kwargs: Any) -> None:
    """Save PrintFormat template to disk if is_app_format is enabled."""
    if not doc.get("is_app_format"):
        return

    app_name = doc.get("app")
    if not app_name:
        log.warning("print.save_to_app_failed", error="App is not specified", name=doc.get("name"))
        return

    # Find app directory
    bench_dir = site_manager.bench_dir
    app_dir = bench_dir / "apps" / app_name

    if not app_dir.exists():
        log.error("print.save_to_app_failed", error="App directory not found", path=str(app_dir))
        return

    # We assume the module name matches the app name (common pattern in Grunt)
    module_dir = app_dir / app_name
    if not module_dir.exists():
        # Look for the first subdirectory that is a module
        subdirs = [d for d in app_dir.iterdir() if d.is_dir() and (d / "__init__.py").exists()]
        if subdirs:
            module_dir = subdirs[0]
        else:
            log.error(
                "print.save_to_app_failed",
                error="No module found in app directory",
                path=str(app_dir),
            )
            return

    # Create print_formats directory
    pf_dir = module_dir / "print_formats"
    pf_dir.mkdir(parents=True, exist_ok=True)

    # Filename based on document name (slugified)
    safe_name = str(doc.get("name")).replace("/", "_").replace(" ", "_").lower()
    ext = "html" if doc.get("template_type") == "html" else "docx"

    file_path = pf_dir / f"{safe_name}.{ext}"

    try:
        content = doc.get("template", "")
        if ext == "docx":
            # No PrintFormat editor produces docx templates yet (only html is
            # wired up in PrintFormatBuilder.vue), so there's no real docx
            # content/path convention to copy from here. Skip the template
            # file rather than silently claim success below.
            log.warning(
                "print.save_to_app_skipped_docx",
                name=doc.get("name"),
                reason="docx app-export not implemented",
            )
        else:
            file_path.write_text(content, encoding="utf-8")

        # Also save a .json metadata file so it can be re-imported
        meta_path = pf_dir / f"{safe_name}.json"
        meta_data = {
            "name": doc.get("name"),
            "doctype": doc.get("doctype"),
            "template_type": doc.get("template_type"),
            "is_default": doc.get("is_default"),
            "is_app_format": True,
            "app": app_name,
            # We don't store the template in JSON if it's external,
            # but here it's easier to keep together
            "template": content,
        }
        meta_path.write_text(json.dumps(meta_data, indent=2, ensure_ascii=False), encoding="utf-8")

        log.info("print.saved_to_app", app=app_name, path=str(file_path))
    except Exception as e:
        log.exception("print.save_to_app_error", name=doc.get("name"), error=str(e))
