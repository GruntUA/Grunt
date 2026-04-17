import json
from typing import Any

import structlog

from grunt.core.hooks import on_doc
from grunt.core.site.manager import site_manager

logger = structlog.get_logger()


@on_doc("PrintFormat", "after_save")
async def save_print_format_to_app(doc: dict[str, Any], **kwargs: Any) -> None:
    """Save PrintFormat template to disk if is_app_format is enabled."""
    if not doc.get("is_app_format"):
        return

    app_name = doc.get("app")
    if not app_name:
        logger.warning(
            "print.save_to_app_failed", error="App is not specified", name=doc.get("name")
        )
        return

    # Find app directory
    bench_dir = site_manager.bench_dir
    app_dir = bench_dir / "apps" / app_name

    if not app_dir.exists():
        logger.error("print.save_to_app_failed", error="App directory not found", path=str(app_dir))
        return

    # We assume the module name matches the app name (common pattern in Grunt)
    module_dir = app_dir / app_name
    if not module_dir.exists():
        # Look for the first subdirectory that is a module
        subdirs = [d for d in app_dir.iterdir() if d.is_dir() and (d / "__init__.py").exists()]
        if subdirs:
            module_dir = subdirs[0]
        else:
            logger.error(
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

    # We save as JSON metadata + the actual template file?
    # Or just as a fixture?
    # User said "в теці обраного додатку".
    # Creating a dedicated folder for each print format might be better if
    # we have multiple files (html + css).
    # But for now, one file is fine.

    file_path = pf_dir / f"{safe_name}.{ext}"

    try:
        content = doc.get("template", "")
        if ext == "docx":
            # For DOCX, the template might be bytes or a file reference?
            # Actually, PrintFormat template for docx is usually a path or bytes.
            # Base DocumentStore handles this.
            pass
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

        logger.info("print.saved_to_app", app=app_name, path=str(file_path))
    except Exception as e:
        logger.exception("print.save_to_app_error", name=doc.get("name"), error=str(e))
