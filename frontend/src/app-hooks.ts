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

// ── List Cell Renderers ────────────────────────────────────────────────────
import { registerListCell } from '@/core/listCellRegistry'
import CheckListCell from '@/components/fields/Check/ListCell.vue'
import SelectListCell from '@/components/fields/Select/ListCell.vue'
import DateListCell from '@/components/fields/Date/ListCell.vue'
import DatetimeListCell from '@/components/fields/Datetime/ListCell.vue'
import GeolocationListCell from '@/components/fields/Geolocation/ListCell.vue'
import RatingListCell from '@/components/fields/Rating/ListCell.vue'
import IconListCell from '@/components/fields/Icon/ListCell.vue'
import LinkListCell from '@/components/fields/Link/ListCell.vue'

registerListCell('Check', CheckListCell)
registerListCell('Select', SelectListCell)
registerListCell('Date', DateListCell)
registerListCell('Datetime', DatetimeListCell)
registerListCell('Geolocation', GeolocationListCell)
registerListCell('Rating', RatingListCell)
registerListCell('Icon', IconListCell)
registerListCell('Link', LinkListCell)

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
