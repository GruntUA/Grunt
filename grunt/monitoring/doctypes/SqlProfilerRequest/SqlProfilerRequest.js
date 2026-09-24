function on_load(frm) {
  frm.actions.add({
    id: 'copy_json',
    label: 'Копіювати JSON',
    icon: 'clipboard-copy',
    action: async (f) => {
      try {
        await navigator.clipboard.writeText(JSON.stringify(f.doc, null, 2))
        grunt.show_alert('Скопійовано в буфер обміну', 'success')
      } catch (e) {
        grunt.show_alert('Clipboard недоступний: ' + e.message, 'error')
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
    label: isRecording ? 'Зупинити запис' : 'Почати запис',
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
        grunt.show_alert(isRecording ? 'Запис розпочато' : 'Запис зупинено', isRecording ? 'success' : 'info')
        lv.refresh()
      } catch (e) {
        grunt.show_alert('Помилка: ' + e.message, 'error')
      }
    },
  })

  listview.actions.add({
    id: 'profiler_clear',
    label: 'Очистити',
    icon: 'eraser',
    confirm: 'Очистити буфер профілера?',
    action: async (lv) => {
      try {
        await grunt.call({ method: 'grunt.api.v1.dev.clear_profiler' })
        grunt.show_alert('Буфер очищено', 'success')
        lv.refresh()
      } catch (e) {
        grunt.show_alert('Помилка: ' + e.message, 'error')
      }
    },
  })
}
