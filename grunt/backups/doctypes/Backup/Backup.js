/**
 * Резервні копії — «Створити зараз» у списку (вибір частин, прогрес у панелі задач),
 * завантаження файлів копії у формі.
 * Посилання на файли підписані й дійсні 15 хвилин (grunt/backups/api.py).
 * «З хмарного сховища» — завантажити на сервер копію, що лишилась лише в хмарі
 * (grunt/storage/cloud/backups.py).
 */

const CLOUD_API = 'grunt.storage.doctypes.StorageRemote.storage_remote'

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
    listview.actions.add({
        id: 'from_cloud',
        label: __('From cloud storage'),
        icon: 'cloud-download',
        placement: 'toolbar',
        action: () => _fromCloud().catch((e) => grunt.show_alert(e?.message || String(e), 'error')),
    })
}

async function _fromCloud() {
    const choice = await grunt.form({
        title: __('From cloud storage'),
        primaryLabel: __('Show backups'),
        fields: [{ fieldname: 'remote', label: __('Cloud storage'), fieldtype: 'Link', options: 'StorageRemote', required: true }],
    })
    if (!choice?.remote) return
    const rows = await grunt.call({ method: `${CLOUD_API}.list_backups`, args: { name: choice.remote } })
    if (!rows.length) {
        grunt.show_alert(__('No backups in this storage yet'), 'info')
        return
    }
    const picked = await grunt.select({
        title: __('Backups in the storage'),
        multiple: false,
        primaryLabel: __('Download to the server'),
        description: __('The chosen set appears in Backups; restore it with «grunt db restore <id>» on the server.'),
        columns: [
            { key: 'id', label: __('Backup') },
            { key: 'kinds', label: __('Parts') },
            { key: 'size', label: __('Size'), width: '110px' },
            { key: 'on_server', label: __('On the server'), width: '120px' },
        ],
        rows,
    })
    if (!picked) return
    if (picked.on_server) {
        grunt.show_alert(__('This backup is already on the server'), 'info')
        return
    }
    await grunt.call({ method: `${CLOUD_API}.fetch_backup`, args: { name: choice.remote, backup_id: picked.id } })
    grunt.show_alert(__('Download started'), 'success')
}
