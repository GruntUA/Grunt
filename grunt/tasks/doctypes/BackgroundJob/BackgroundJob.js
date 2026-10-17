/**
 * Активні фонові задачі — «Скасувати» для задачі, що звітує прогрес
 * (напр. резервна копія за розкладом; grunt/progress.py → cancel_job).
 */

/** @param {FormProxy} frm */
function on_load(frm) {
    frm.actions.add({
        id: 'cancel_job',
        label: __('Cancel'),
        icon: 'circle-stop',
        placement: 'primary',
        visible: (f) => !!f.doc.cancellable && !!f.doc.task_id,
        action: async (f) => {
            const ok = await grunt.call({ method: 'grunt.progress.cancel_job', args: { job_id: f.doc.task_id } })
            grunt.show_alert(ok ? __('Cancelling…') : __('The task has already finished'), ok ? 'success' : 'info')
        },
    })
}
