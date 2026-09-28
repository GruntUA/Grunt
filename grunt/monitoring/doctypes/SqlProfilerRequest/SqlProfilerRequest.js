function on_load(frm) {
  frm.actions.add({
    id: 'copy_json',
    label: __('Copy JSON'),
    icon: 'clipboard-copy',
    action: async (f) => {
      try {
        await navigator.clipboard.writeText(JSON.stringify(f.doc, null, 2))
        grunt.show_alert(__('Copied to the clipboard'), 'success')
      } catch (e) {
        grunt.show_alert(__('Clipboard unavailable:') + ' ' + e.message, 'error')
      }
    },
  })
}

async function setup_list(listview) {
  listview.actions.remove('add') // read-only ring buffer view — records aren't created by hand

  let isRecording = true
  try {
    const settings = await grunt.call({ method: 'grunt.api.v1.dev.get_profiler_settings' })
    isRecording = settings.enabled
  } catch (_) {}

  const toggleLook = () => ({
    label: isRecording ? __('Stop recording') : __('Start recording'),
    icon: isRecording ? 'square' : 'play',
    variant: isRecording ? 'destructive' : 'default',
  })

  listview.actions.add({
    id: 'profiler_toggle',
    ...toggleLook(),
    action: async (lv) => {
      try {
        const settings = await grunt.call({
          method: 'grunt.api.v1.dev.update_profiler_settings',
          args: { enabled: !isRecording },
        })
        isRecording = settings.enabled
        lv.actions.update('profiler_toggle', toggleLook())
        grunt.show_alert(isRecording ? __('Recording started') : __('Recording stopped'), isRecording ? 'success' : 'info')
        lv.refresh()
      } catch (e) {
        grunt.show_alert(__('Error') + ': ' + e.message, 'error')
      }
    },
  })

  listview.actions.add({
    id: 'profiler_clear',
    label: 'Clear',
    icon: 'eraser',
    confirm: __('Clear the profiler buffer?'),
    action: async (lv) => {
      try {
        await grunt.call({ method: 'grunt.api.v1.dev.clear_profiler' })
        grunt.show_alert(__('Buffer cleared'), 'success')
        lv.refresh()
      } catch (e) {
        grunt.show_alert(__('Error') + ': ' + e.message, 'error')
      }
    },
  })
}
