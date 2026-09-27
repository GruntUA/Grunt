/**
 * Standard form actions — registered for every DocType before its own script.
 *
 * A DocType's `<Name>.js` (or a ClientScript) changes or removes them by id:
 *
 *   frm.actions.update('save', { label: 'Провести' })
 *   frm.actions.remove('duplicate')
 *
 * Ids: save · refresh · print, print_xlsx, print_pdf, print_html · open_new_tab, web_view ·
 * edit_doctype, configure_print · duplicate, discard, activity, links, share ·
 * rename, delete. Labels are translation keys (English source strings).
 *
 * Orders: primary 100; toolbar — yours by default (500), refresh 900;
 * menu — print 100…, navigation 200…, DocType 250…, document 300…, danger 900….
 *
 * @param {FormProxy} frm
 */

const _isSystemManager = () => (grunt.session.roles || []).includes('System Manager')
const _saved = (frm) => !frm.is_new

function on_load(frm) {
    const actions = frm.actions

    // ── Primary ────────────────────────────────────────────────────────────
    actions.add({
        id: 'save',
        label: __('Save'),
        placement: 'primary',
        order: 100,
        shortcut: 'Ctrl+S',
        visible: (f) => f.perm.write && f.has_editable_fields,
        enabled: (f) => !f.is_saving,
        busy: (f) => f.is_saving,
        action: (f) => f.save(),
    })

    // ── Toolbar ────────────────────────────────────────────────────────────
    actions.add({
        id: 'refresh',
        label: __('Refresh'),
        icon: 'refresh-cw',
        icon_only: true,
        order: 900,
        visible: _saved,
        enabled: (f) => !f.is_dirty && !f.is_loading,
        busy: (f) => f.is_loading,
        // The document and the DocType definition, fresh from the server.
        action: (f) => f.reload({ meta: true }),
    })

    // ── Menu: print ────────────────────────────────────────────────────────
    const print = [
        ['print', __('Print'), 'printer', () => frm.print('html', { autoprint: true })],
        ['print_xlsx', __('Excel (.xlsx)'), 'file-spreadsheet', () => frm.print('xlsx')],
        ['print_pdf', __('PDF'), 'file-text', () => frm.print('pdf')],
        ['print_html', __('HTML'), 'globe', () => frm.print('html')],
    ]
    print.forEach(([id, label, icon, action], i) =>
        actions.add({ id, label, icon, placement: 'menu', group: 'print', order: 100 + i, visible: _saved, action }),
    )

    // ── Menu: navigation / DocType ─────────────────────────────────────────
    actions.add({
        id: 'open_new_tab',
        label: __('Open in new tab'),
        icon: 'external-link',
        placement: 'menu',
        group: 'print',
        order: 200,
        visible: _saved,
        action: (f) => grunt.open_route('Form', f.doctype, f.name),
    })
    // `__web_url` — set by the server while the document is a public page
    // (DocType web view, grunt.website.generator).
    actions.add({
        id: 'web_view',
        label: __('View on website'),
        icon: 'globe',
        placement: 'menu',
        group: 'print',
        order: 210,
        visible: (f) => _saved(f) && !!f.doc.__web_url,
        action: (f) => window.open(f.doc.__web_url, '_blank', 'noopener'),
    })
    actions.add({
        id: 'edit_doctype',
        label: __('Edit DocType'),
        icon: 'settings',
        placement: 'menu',
        group: 'doctype',
        order: 250,
        visible: _isSystemManager,
        action: (f) => grunt.open_route('Form', 'DocType', f.doctype),
    })
    actions.add({
        id: 'configure_print',
        label: __('Configure print'),
        icon: 'sliders-horizontal',
        placement: 'menu',
        group: 'doctype',
        order: 260,
        visible: _isSystemManager,
        action: (f) => grunt.open_route('List', 'PrintFormat', { doctype: f.doctype }),
    })

    // ── Menu: the document ─────────────────────────────────────────────────
    actions.add({
        id: 'duplicate',
        label: __('Duplicate'),
        icon: 'copy',
        placement: 'menu',
        group: 'document',
        order: 300,
        visible: (f) => _saved(f) && f.perm.create,
        action: (f) => f.duplicate(),
    })
    actions.add({
        id: 'discard',
        label: __('Discard changes'),
        icon: 'undo',
        placement: 'menu',
        group: 'document',
        order: 310,
        visible: (f) => _saved(f) && f.is_dirty,
        action: (f) => f.discard(),
    })
    actions.add({
        id: 'activity',
        label: __('Activity log'),
        icon: 'history',
        placement: 'menu',
        group: 'document',
        order: 320,
        visible: _saved,
        action: (f) => f.toggle_activity(),
    })
    actions.add({
        id: 'links',
        label: __('Links'),
        icon: 'link-2',
        placement: 'menu',
        group: 'document',
        order: 330,
        visible: _saved,
        action: (f) => f.show_links(),
    })
    actions.add({
        id: 'share',
        label: __('Share link'),
        icon: 'share-2',
        placement: 'menu',
        group: 'document',
        order: 340,
        visible: _saved,
        action: (f) => f.share(),
    })

    // ── Menu: rename / delete ──────────────────────────────────────────────
    actions.add({
        id: 'rename',
        label: __('Rename'),
        icon: 'pencil',
        placement: 'menu',
        group: 'danger',
        order: 900,
        visible: (f) => _saved(f) && f.perm.write,
        action: (f) => f.rename(),
    })
    actions.add({
        id: 'delete',
        label: __('Delete'),
        icon: 'trash-2',
        placement: 'menu',
        group: 'danger',
        order: 910,
        variant: 'destructive',
        visible: (f) => _saved(f) && f.perm.delete,
        action: (f) => f.delete(),
    })
}

/**
 * Workflow transitions allowed now → `workflow:<action>` actions in the workflow
 * bar. Runs again whenever they reload (a transition changes the state), so the
 * previous state's transitions are dropped first. A DocType's own
 * `on_transitions` runs after this one and may change or hide them:
 *
 *   function on_transitions(frm) {
 *       frm.actions.update('workflow:Відхилити', { variant: 'destructive', confirm: 'Відхилити документ?' })
 *   }
 *
 * @param {FormProxy} frm
 */
function on_transitions(frm) {
    frm.actions
        .list()
        .filter((a) => a.id.startsWith('workflow:'))
        .forEach((a) => frm.actions.remove(a.id))

    frm.transitions.forEach((t, i) =>
        frm.actions.add({
            id: `workflow:${t.action}`,
            label: t.action,
            placement: 'workflow',
            order: 100 + i,
            variant: 'secondary',
            enabled: (f) => !f.is_saving && !f.is_dirty,
            action: (f) => f.apply_transition(t.action),
        }),
    )
}
