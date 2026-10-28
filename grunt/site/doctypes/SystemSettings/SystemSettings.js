/**
 * SystemSettings - «Compress existing images» queues the background task
 * (grunt.storage.images.start_compression); its progress shows in the task panel.
 * The task uses the saved settings.
 *
 * @param {FormProxy} frm
 * @param {string} fieldname
 */
async function on_change(frm, fieldname) {
    if (fieldname !== 'compress_existing_images') return
    const ok = await grunt.confirm(
        __('Images uploaded before compression was on will be re-encoded in the background with the saved settings. The originals are not kept. Continue?'),
    );
    if (!ok) return
    try {
        await grunt.call({ method: 'grunt.storage.images.start_compression' })
        grunt.show_alert(__('Image compression started - follow it in the task panel.'), 'success')
    } catch (e) {
        console.error('[SystemSettings] start_compression failed', e)
        grunt.msgprint({ message: e && e.message ? e.message : __('Could not start the task'), indicator: 'red' })
    }
}
