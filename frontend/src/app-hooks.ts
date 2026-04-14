/**
 * App hooks — the single place where exporters, importers, and other
 * extensible registries get populated at startup.
 *
 * Pattern mirrors the backend hooks.py convention:
 *   each app/module registers its own capabilities here.
 *
 * Built-in (grunt core) registrations come first.
 * App-specific registrations follow in clearly marked sections.
 *
 * Usage from an app module:
 *   import { registerExporter } from '@/core/io'
 *   import { myCustomExporter } from './exporters/myCustomExporter'
 *   registerExporter(myCustomExporter)
 */

// ── Exporters ──────────────────────────────────────────────────────────────
import { registerExporter } from '@/core/io'
import { excelExporter } from '@/core/io/exporters/excelExporter'
import { htmlExporter } from '@/core/io/exporters/htmlExporter'

registerExporter(excelExporter)
registerExporter(htmlExporter)

// ── Importers ──────────────────────────────────────────────────────────────
// import { registerImporter } from '@/core/io'
// registerImporter(csvImporter)

// ── infra_map ──────────────────────────────────────────────────────────────
// import { infraMapExporter } from '@/modules/infra_map/exporters'
// registerExporter(infraMapExporter)
