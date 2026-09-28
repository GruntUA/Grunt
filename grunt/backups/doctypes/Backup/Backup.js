/**
 * Резервні копії — «Створити зараз» у списку (вибір частин, прогрес у панелі задач),
 * завантаження файлів копії у формі.
 * Посилання на файли підписані й дійсні 15 хвилин (grunt/backups/api.py).
 */

const DOWNLOADS = [
    ['database_url', 'Database'],
    ['files_url', 'Files'],
    ['config_url', 'Configuration'],
]

/** @param {FormProxy} frm */
function on_load(frm) {
    frm.hide_sidebar()
    for (const id of ['print', 'print_xlsx', 'print_pdf', 'print_html', 'share', 'links', 'activity', 'duplicate', 'rename']) {
        frm.actions.remove(id)
    }
    DOWNLOADS.forEach(([field, label], i) =>
        frm.actions.add({
            id: `download_${field}`,
            label: `${__('Download')}: ${__(label)}`,
            icon: 'download',
            group: 'download',
            order: 100 + i,
            visible: (f) => !!f.doc[field],
            action: (f) => window.open(f.doc[field], '_blank'),
        }),
    )
}

async function setup_list(listview) {
    listview.actions.remove('add')
    listview.actions.remove('bulk_edit')
    listview.actions.add({
        id: 'backup_now',
        label: __('Create now'),
        icon: 'archive',
        placement: 'primary',
        action: async () => {
            const parts = await grunt.form({
                title: __('Create backup'),
                primaryLabel: __('Create now'),
                fields: [
                    { fieldname: 'with_database', label: __('Database'), fieldtype: 'Check', default: true },
                    { fieldname: 'with_files', label: __('Uploaded files'), fieldtype: 'Check', default: true },
                    { fieldname: 'with_config', label: __('Configuration (.env)'), fieldtype: 'Check', default: true },
                ],
            })
            if (!parts) return
            if (!parts.with_database && !parts.with_files && !parts.with_config) {
                grunt.show_alert(__('Choose at least one part to back up'), 'warning')
                return
            }
            await grunt.call({
                method: 'grunt.backups.api.backup_now',
                args: {
                    with_database: !!parts.with_database,
                    with_files: !!parts.with_files,
                    with_config: !!parts.with_config,
                },
            })
            // Progress shows in the task panel; the list refreshes when it's done.
            grunt.show_alert(__('Backup started'), 'success')
        },
    })
}
