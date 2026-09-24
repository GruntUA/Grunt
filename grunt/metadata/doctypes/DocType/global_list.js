/**
 * Standard list actions — registered for every DocType before its own script.
 *
 * A DocType's `<Name>.js` (or a ClientScript) changes or removes them by id
 * in `setup_list(listview)`:
 *
 *   listview.actions.remove('add')
 *   listview.actions.update('add', { label: 'Новий запис' })
 *
 * Ids: add · refresh · export:<exporter> · edit_doctype, customize_quick_filters ·
 * create_report · bulk_edit, bulk_delete, fast_delete. Labels are translation
 * keys (English source strings).
 *
 * @param {ListViewProxy} listview
 */

const _isSystemManager = () => (grunt.session.roles || []).includes('System Manager')

function setup_list(listview) {
    const actions = listview.actions

    actions.add({
        id: 'add',
        label: __('Add'),
        icon: 'plus',
        placement: 'primary',
        order: 100,
        visible: (lv) => lv.perm.create,
        action: (lv) => lv.new_doc(),
    })

    actions.add({
        id: 'refresh',
        label: __('Refresh'),
        icon: 'refresh-cw',
        icon_only: true,
        order: 900,
        busy: (lv) => lv.is_fetching,
        // The rows and the DocType definition, fresh from the server.
        action: (lv) => lv.refresh({ meta: true }),
    })

    // ── Menu ───────────────────────────────────────────────────────────────
    listview.exporters.forEach((exporter, i) =>
        actions.add({
            id: `export:${exporter.id}`,
            label: exporter.label,
            icon: 'download',
            placement: 'menu',
            group: 'export',
            order: 100 + i,
            visible: (lv) => lv.can_export,
            action: (lv) => lv.export(exporter.id),
        }),
    )
    actions.add({
        id: 'edit_doctype',
        label: __('Edit DocType'),
        icon: 'pencil',
        placement: 'menu',
        group: 'doctype',
        order: 200,
        visible: _isSystemManager,
        action: (lv) => grunt.set_route('Form', 'DocType', lv.doctype),
    })
    actions.add({
        id: 'customize_quick_filters',
        label: __('Customize Quick Filters'),
        icon: 'filter',
        placement: 'menu',
        group: 'doctype',
        order: 210,
        visible: _isSystemManager,
        action: (lv) => lv.customize_quick_filters(),
    })
    actions.add({
        id: 'create_report',
        label: __('Create report'),
        icon: 'bar-chart-2',
        placement: 'menu',
        group: 'report',
        order: 300,
        action: (lv) => lv.create_report(),
    })

    // ── Selection bar ──────────────────────────────────────────────────────
    actions.add({
        id: 'bulk_edit',
        label: __('Edit'),
        icon: 'pencil',
        placement: 'bulk',
        order: 100,
        visible: (lv) => lv.perm.write,
        action: (lv) => lv.bulk_edit(),
    })
    actions.add({
        id: 'bulk_delete',
        label: __('Delete'),
        icon: 'trash-2',
        placement: 'bulk',
        order: 200,
        variant: 'destructive',
        visible: (lv) => lv.perm.delete,
        action: (lv) => lv.bulk_delete(),
    })
    actions.add({
        id: 'fast_delete',
        label: __('Fast delete'),
        icon: 'zap',
        placement: 'bulk',
        order: 210,
        variant: 'destructive',
        // Every matching row, without per-document hooks — System Manager only.
        visible: (lv) => lv.all_selected && lv.perm.delete && _isSystemManager(),
        action: (lv) => lv.fast_delete(),
    })
}
