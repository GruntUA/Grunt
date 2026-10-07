import { Details, DetailsContent, DetailsSummary } from '@tiptap/extension-details'

// Collapsible block: <details><summary>…</summary><div>…</div></details> -
// works on the public page without any script. The sanitizer strips the
// content div's `data-type`, so saved HTML is matched by structure instead.
const DetailsBody = DetailsContent.extend({
  parseHTML() {
    return [{ tag: 'div[data-type="detailsContent"]' }, { tag: 'details > div' }]
  },
})

export const DetailsKit = [Details.configure({ HTMLAttributes: { class: 'details' } }), DetailsSummary, DetailsBody]
