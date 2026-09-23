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
    for (const [field, label] of DOWNLOADS) {
        if (frm.doc[field]) {
            frm.add_button(`Завантажити: ${label}`, () => window.open(frm.doc[field], '_blank'), { variant: 'outline' })
        }
    }
}

async function setup_list(listview) {
    listview.can_create = false
    listview.add_button('Створити зараз', async () => {
        await grunt.call({ method: 'grunt.backups.api.backup_now' })
        grunt.show_alert('Резервну копію поставлено в чергу — з\'явиться в списку за хвилину', 'success')
        setTimeout(() => listview.refresh(), 5000)
    })
}
