/**
 * Резервні копії — «Створити зараз» у списку, завантаження файлів копії у формі.
 * Посилання на файли підписані й дійсні 15 хвилин (grunt/backups/api.py).
 */

const DOWNLOADS = [
    ['database_url', 'База даних'],
    ['files_url', 'Файли'],
    ['config_url', 'Конфігурація'],
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
            label: `Завантажити: ${label}`,
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
        label: 'Створити зараз',
        icon: 'archive',
        placement: 'primary',
        action: async (lv) => {
            await grunt.call({ method: 'grunt.backups.api.backup_now' })
            grunt.show_alert('Резервну копію поставлено в чергу — з\'явиться в списку за хвилину', 'success')
            setTimeout(() => lv.refresh(), 5000)
        },
    })
}
