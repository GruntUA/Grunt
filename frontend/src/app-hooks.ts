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

const EMPTY_OPS = ['is not set', 'is set']
const LIST_OPS = ['in', 'not in']
const TEXT_OPS = ['like', 'not like', '=', '!=', ...LIST_OPS, ...EMPTY_OPS]
const NUM_OPS = ['=', '!=', '>', '<', '>=', '<=', ...EMPTY_OPS]
const DATE_OPS = ['=', '!=', '>', '<', '>=', '<=', ...EMPTY_OPS]

registerFilterConfig('_default', { operators: TEXT_OPS, filterInput: DefaultFilterInput })
registerFilterConfig('Data', { operators: TEXT_OPS, filterInput: DefaultFilterInput })
registerFilterConfig('Text', { operators: TEXT_OPS, filterInput: DefaultFilterInput })
registerFilterConfig('LongText', { operators: TEXT_OPS, filterInput: DefaultFilterInput })
registerFilterConfig('Int', { operators: NUM_OPS, filterInput: DefaultFilterInput })
registerFilterConfig('Float', { operators: NUM_OPS, filterInput: DefaultFilterInput })
registerFilterConfig('Currency', { operators: NUM_OPS, filterInput: DefaultFilterInput })
registerFilterConfig('Rating', { operators: NUM_OPS, filterInput: DefaultFilterInput })
registerFilterConfig('Date', { operators: DATE_OPS, filterInput: DateFilterInput })
registerFilterConfig('Datetime', { operators: DATE_OPS, filterInput: DatetimeFilterInput })
registerFilterConfig('Time', { operators: DATE_OPS, filterInput: DefaultFilterInput })
registerFilterConfig('Check', { operators: ['='], filterInput: CheckFilterInput })
registerFilterConfig('Select', { operators: ['=', '!=', ...LIST_OPS, ...EMPTY_OPS], filterInput: SelectFilterInput })
registerFilterConfig('Link', { operators: ['=', '!=', ...LIST_OPS, 'child_of', ...EMPTY_OPS], filterInput: LinkFilterInput })

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
import ImageListCell from '@/components/fields/Image/ListCell.vue'
import CurrencyListCell from '@/components/fields/Currency/ListCell.vue'

registerListCell('Check', CheckListCell)
registerListCell('Select', SelectListCell)
registerListCell('Date', DateListCell)
registerListCell('Datetime', DatetimeListCell)
registerListCell('Geolocation', GeolocationListCell)
registerListCell('Rating', RatingListCell)
registerListCell('Icon', IconListCell)
registerListCell('Link', LinkListCell)
registerListCell('Image', ImageListCell)
registerListCell('Currency', CurrencyListCell)

// ── Exporters ──────────────────────────────────────────────────────────────
import { registerExporter } from '@/core/io'
import { excelExporter } from '@/core/io/exporters/excelExporter'
import { htmlExporter } from '@/core/io/exporters/htmlExporter'

registerExporter(excelExporter)
registerExporter(htmlExporter)

// ── Importers ──────────────────────────────────────────────────────────────
// import { registerImporter } from '@/core/io'
// registerImporter(csvImporter)

// ── Attachment Channels ────────────────────────────────────────────────────
import { registerAttachChannel } from '@/core/attachmentChannels/registry'
import { localFileChannel } from '@/core/attachmentChannels/channels/LocalFileChannel'
import { libraryChannel } from '@/core/attachmentChannels/channels/LibraryChannel'
import { urlChannel } from '@/core/attachmentChannels/channels/UrlChannel'
import { cameraChannel } from '@/core/attachmentChannels/channels/CameraChannel'

registerAttachChannel(localFileChannel)
registerAttachChannel(libraryChannel)
registerAttachChannel(urlChannel)
registerAttachChannel(cameraChannel)

// ── infra_map ──────────────────────────────────────────────────────────────
// import { infraMapExporter } from '@/modules/infra_map/exporters'
// registerExporter(infraMapExporter)
