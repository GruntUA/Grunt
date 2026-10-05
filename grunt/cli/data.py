"""grunt data export / import - move documents of chosen DocTypes (with their files)
between sites, e.g. from a dev site to a new production one.

A bundle is a plain tar (uploads are mostly images/PDF - compression buys little):

* ``data.json`` - rows of every exported DocType, as stored (same ``name`` s, so
  links between documents and ``file_id`` references in texts keep working), and
  the ``File`` records they use;
* ``blobs/<sha256>`` (+ ``thumbs/<sha256>.webp``) - the stored files of those
  records only, not the whole ``uploads/`` of the source site.

Rows are copied table-to-table, without controllers/hooks: this is a transfer of
existing data, not new input. DocTypes with child tables are refused.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import tarfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import click
from sqlalchemy import text

from grunt.cli.utils import _site_session

FORMAT_VERSION = 1

# /api/v1/method/grunt.storage.doctypes.File.file.get_content?file_id=<name>
_FILE_ID_RE = re.compile(r"file_id=([0-9A-Za-z_-]+)")


@click.group("data")
def data_group():
    """Data: move documents with their files between sites."""


# export


@data_group.command("export")
@click.argument("output", type=click.Path(dir_okay=False, path_type=Path))
@click.option(
    "--doctype",
    "specs",
    multiple=True,
    required=True,
    help='DocType or "DocType:field=value[,field=value]"; repeat for several.',
)
@click.option("--site", default=None, help="Site name")
def data_export(output: Path, specs: tuple[str, ...], site: str | None):
    """Export documents (and the files they use) into a bundle.

    \b
    Example:
      grunt data export portal.tar --doctype MltPage --doctype MltBanner \\
          --doctype "WebsiteMenuItem:menu=mlt_portal"
    """

    from grunt.db.write_intent import set_process_default

    # Only reads here - don't take the write lock at BEGIN like other commands.
    set_process_default(False)

    async def _collect():
        import grunt
        from grunt.storage.backends import get_storage_backend

        async with _site_session(site) as (session, eng), grunt.system_context(session, eng):
            doctypes = []
            file_ids: set[str] = set()
            for spec in specs:
                doctype, filters = _parse_spec(spec)
                table = await _table(doctype)
                rows = await _select(session, table, filters)
                doctypes.append({"doctype": doctype, "filters": filters, "rows": rows})
                click.echo(f"{doctype}: {len(rows)}")
                names = [r["name"] for r in rows]
                for chunk in _chunks(names):
                    attached = await _select(
                        session,
                        await _table("File"),
                        {"attached_to_doctype": doctype},
                        extra=("attached_to_id", chunk),
                    )
                    file_ids.update(f["name"] for f in attached)
                for row in rows:
                    for value in row.values():
                        if isinstance(value, str):
                            file_ids.update(_FILE_ID_RE.findall(value))

            files = []
            file_table = await _table("File")
            for chunk in _chunks(sorted(file_ids)):
                files += await _select(session, file_table, {}, extra=("name", chunk))
            # Reads are done - end the transaction before the long file copy.
            await session.rollback()

            backend = get_storage_backend()
            blobs = {}
            for f in files:
                key = f.get("content_hash")
                if key and key not in blobs:
                    blobs[key] = (backend.path(key), backend.thumbnail_path(key))
        return doctypes, files, blobs

    doctypes, files, blobs = asyncio.run(_collect())
    missing = [key for key, (blob, _thumb) in blobs.items() if not blob.is_file()]
    if missing:
        click.echo(f"Warning: {len(missing)} stored file(s) missing on disk — skipped.", err=True)

    payload = {"version": FORMAT_VERSION, "doctypes": doctypes, "files": files}
    raw = json.dumps(payload, default=_encode, ensure_ascii=False).encode()
    total = sum(p.stat().st_size for p, _t in blobs.values() if p.is_file())
    click.echo(f"File: {len(files)} record(s), {len(blobs)} stored file(s), {total / 2**20:.0f} MB")

    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_name(output.name + ".part")
    with tarfile.open(part, "w") as tar:
        info = tarfile.TarInfo("data.json")
        info.size = len(raw)
        tar.addfile(info, io.BytesIO(raw))
        with click.progressbar(blobs.items(), label="Files") as items:
            for key, (blob, thumb) in items:
                if blob.is_file():
                    tar.add(blob, arcname=f"blobs/{key}")
                if thumb.is_file():
                    tar.add(thumb, arcname=f"thumbs/{key}.webp")
    part.replace(output)
    click.echo(f"Bundle: {output} ({output.stat().st_size / 2**20:.0f} MB)")


# import


@data_group.command("import")
@click.argument("bundle", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--site", default=None, help="Site name")
@click.option("--yes", "-y", is_flag=True, help="Do not ask for confirmation")
def data_import(bundle: Path, site: str | None, yes: bool):
    """Import a bundle made by `grunt data export`.

    For every DocType in the bundle, the target site's documents matching the
    same filter are REPLACED by the bundle's (e.g. all MltPage, only the
    `mlt_portal` menu items). File records with the same name are replaced too.
    """
    with tarfile.open(bundle) as tar:
        member = tar.extractfile("data.json")
        if member is None:
            raise click.ClickException("data.json not found in the bundle")
        payload = json.loads(member.read(), object_hook=_decode)
    if payload.get("version") != FORMAT_VERSION:
        raise click.ClickException(f"Unsupported bundle version: {payload.get('version')}")

    click.echo("The bundle replaces on the target site:")
    for block in payload["doctypes"]:
        where = _describe(block["filters"])
        click.echo(f"  {block['doctype']}{where}: → {len(block['rows'])}")
    click.echo(f"  File (same names): {len(payload['files'])}")
    if not yes and not click.confirm("Continue?", default=False):
        raise SystemExit(1)

    async def _run():
        import grunt
        from grunt.storage.backends import get_storage_backend

        async with _site_session(site) as (session, eng), grunt.system_context(session, eng):
            # Files first, outside any write transaction (they are content-addressed:
            # an existing blob is the same file).
            await session.rollback()
            backend = get_storage_backend()
            placed = await asyncio.to_thread(_place_files, bundle, backend)
            click.echo(f"Stored files: {placed} new")

            touched = []
            for block in payload["doctypes"]:
                table = await _table(block["doctype"])
                deleted = await _delete(session, table, block["filters"])
                inserted = await _insert(session, table, block["rows"])
                touched.append(block["doctype"])
                click.echo(f"{block['doctype']}: removed {deleted}, added {inserted}")
            file_table = await _table("File")
            names = [f["name"] for f in payload["files"]]
            for chunk in _chunks(names):
                await session.execute(
                    text(f'DELETE FROM "{file_table}" WHERE name IN :names').bindparams(
                        _expanding("names")
                    ),
                    {"names": chunk},
                )
            await _insert(session, file_table, payload["files"])
            await session.commit()

            for doctype in [*touched, "File"]:
                await grunt.doc_cache.invalidate_doctype(doctype)
                await grunt.query_cache.invalidate_doctype(doctype)
        click.echo("Done. Restart the services so their in-process caches refresh: grunt restart")

    asyncio.run(_run())


# helpers


def _parse_spec(spec: str) -> tuple[str, dict[str, str]]:
    doctype, _, cond = spec.partition(":")
    filters = {}
    for part in filter(None, cond.split(",")):
        field, sep, value = part.partition("=")
        if not sep:
            raise click.BadParameter(f"expected field=value, got {part!r}", param_hint="--doctype")
        filters[field.strip()] = value.strip()
    return doctype.strip(), filters


def _describe(filters: dict[str, str]) -> str:
    return f" ({', '.join(f'{k}={v}' for k, v in filters.items())})" if filters else " (all)"


async def _table(doctype: str) -> str:
    import grunt

    meta = await grunt.get_meta(doctype)
    if meta is None:
        raise click.ClickException(f"DocType not found: {doctype}")
    if meta.get_table_fields():
        raise click.ClickException(f"{doctype}: DocTypes with child tables are not supported")
    return meta.table_name


def _check_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise click.ClickException(f"Bad field name: {name!r}")
    return name


def _expanding(name: str):
    from sqlalchemy import bindparam

    return bindparam(name, expanding=True)


def _where(filters: dict[str, Any], extra: tuple[str, list] | None) -> tuple[str, list]:
    clauses = [f'"{_check_ident(k)}" = :f_{k}' for k in filters]
    binds = []
    if extra:
        clauses.append(f'"{_check_ident(extra[0])}" IN :extra')
        binds.append(_expanding("extra"))
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), binds


async def _select(session, table: str, filters: dict, extra: tuple[str, list] | None = None):
    where, binds = _where(filters, extra)
    params: dict[str, Any] = {f"f_{k}": v for k, v in filters.items()}
    if extra:
        params["extra"] = extra[1]
    stmt = text(f'SELECT * FROM "{table}"{where}')
    if binds:
        stmt = stmt.bindparams(*binds)
    result = await session.execute(stmt, params)
    return [dict(r) for r in result.mappings()]


async def _delete(session, table: str, filters: dict) -> int:
    where, _ = _where(filters, None)
    result = await session.execute(
        text(f'DELETE FROM "{table}"{where}'), {f"f_{k}": v for k, v in filters.items()}
    )
    return result.rowcount or 0


async def _columns(session, table: str) -> set[str]:
    def _inspect(conn):
        from sqlalchemy import inspect

        return {c["name"] for c in inspect(conn).get_columns(table)}

    conn = await session.connection()
    return await conn.run_sync(_inspect)


async def _insert(session, table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    columns = await _columns(session, table)
    dropped = sorted({k for r in rows for k in r} - columns)
    if dropped:
        click.echo(f"  {table}: no such column(s) here, values skipped: {', '.join(dropped)}")
    keys = sorted({k for r in rows for k in r} & columns)
    stmt = text(
        f'INSERT INTO "{table}" ({", ".join(f"{chr(34)}{k}{chr(34)}" for k in keys)}) '
        f"VALUES ({', '.join(f':{k}' for k in keys)})"
    )
    for chunk in _chunks(rows, 500):
        await session.execute(stmt, [{k: r.get(k) for k in keys} for r in chunk])
    return len(rows)


def _place_files(bundle: Path, backend) -> int:
    """Put blobs/thumbnails from the bundle where the storage expects them."""
    placed = 0
    with tarfile.open(bundle) as tar:
        for member in tar:
            if not member.isfile():
                continue
            folder, _, fname = member.name.partition("/")
            if folder == "blobs":
                dest = backend.path(fname)
            elif folder == "thumbs" and fname.endswith(".webp"):
                dest = backend.thumbnail_path(fname.removesuffix(".webp"))
            else:
                continue
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".part")
            source = tar.extractfile(member)
            if source is None:
                continue
            with source, open(tmp, "wb") as out:
                while chunk := source.read(1 << 20):
                    out.write(chunk)
            tmp.replace(dest)
            placed += folder == "blobs"
    return placed


def _chunks(items: list, size: int = 400):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"$dt": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, Decimal):
        return {"$dec": str(value)}
    if isinstance(value, bytes):
        return {"$b64": base64.b64encode(value).decode()}
    raise TypeError(f"Cannot serialise {type(value).__name__}")


def _decode(obj: dict) -> Any:
    if len(obj) == 1:
        ((key, value),) = obj.items()
        if key == "$dt":
            return datetime.fromisoformat(value)
        if key == "$date":
            return date.fromisoformat(value)
        if key == "$dec":
            return Decimal(value)
        if key == "$b64":
            return base64.b64decode(value)
    return obj
