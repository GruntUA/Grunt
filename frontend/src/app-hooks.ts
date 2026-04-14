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

// ── Filter Operators & Inputs ──────────────────────────────────────────────
import { registerFilterConfig } from '@/core/filterRegistry'
import DefaultFilterInput from '@/components/fields/Default/FilterInput.vue'
import CheckFilterInput from '@/components/fields/Check/FilterInput.vue'
import SelectFilterInput from '@/components/fields/Select/FilterInput.vue'
import DateFilterInput from '@/components/fields/Date/FilterInput.vue'
import DatetimeFilterInput from '@/components/fields/Datetime/FilterInput.vue'
import LinkFilterInput from '@/components/fields/Link/FilterInput.vue'

const TEXT_OPS = ['=', '!=', 'like']
const NUM_OPS  = ['=', '!=', '>', '<', '>=', '<=']
const DATE_OPS = ['=', '!=', '>', '<', '>=', '<=']

registerFilterConfig('_default',  { operators: TEXT_OPS,  filterInput: DefaultFilterInput })
registerFilterConfig('Data',      { operators: TEXT_OPS,  filterInput: DefaultFilterInput })
registerFilterConfig('Text',      { operators: TEXT_OPS,  filterInput: DefaultFilterInput })
registerFilterConfig('LongText',  { operators: TEXT_OPS,  filterInput: DefaultFilterInput })
registerFilterConfig('Int',       { operators: NUM_OPS,   filterInput: DefaultFilterInput })
registerFilterConfig('Float',     { operators: NUM_OPS,   filterInput: DefaultFilterInput })
registerFilterConfig('Currency',  { operators: NUM_OPS,   filterInput: DefaultFilterInput })
registerFilterConfig('Rating',    { operators: NUM_OPS,   filterInput: DefaultFilterInput })
registerFilterConfig('Date',      { operators: DATE_OPS,  filterInput: DateFilterInput })
registerFilterConfig('Datetime',  { operators: DATE_OPS,  filterInput: DatetimeFilterInput })
registerFilterConfig('Time',      { operators: DATE_OPS,  filterInput: DefaultFilterInput })
registerFilterConfig('Check',     { operators: ['='],     filterInput: CheckFilterInput })
registerFilterConfig('Select',    { operators: ['=', '!='], filterInput: SelectFilterInput })
registerFilterConfig('Link',      { operators: ['=', '!='], filterInput: LinkFilterInput })

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
