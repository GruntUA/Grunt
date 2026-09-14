function on_load(frm) {
  frm.add_button('Копіювати JSON', async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(frm.doc, null, 2))
      grunt.show_alert('Скопійовано в буфер обміну', 'success')
    } catch (e) {
      grunt.show_alert('Clipboard недоступний: ' + e.message, 'error')
    }
  }, { variant: 'outline' })
}

async function setup_list(listview) {
  listview.can_create = false // read-only ring buffer view — records aren't created by hand

  let isRecording = true
  try {
    const settings = await grunt.call({ method: 'grunt.api.v1.dev.get_profiler_settings' })
    isRecording = settings.enabled
  } catch (_) {}

  const toggleBtn = listview.add_button(
    isRecording ? '⏹ Зупинити' : '▶ Старт',
    async function () {
      try {
        const settings = await grunt.call({
          method: 'grunt.api.v1.dev.update_profiler_settings',
          args: { enabled: !isRecording },
        })
        isRecording = settings.enabled
        toggleBtn.update({
          label: isRecording ? '⏹ Зупинити' : '▶ Старт',
          variant: isRecording ? 'destructive' : 'default',
        })
        grunt.show_alert(isRecording ? 'Запис розпочато' : 'Запис зупинено', isRecording ? 'success' : 'info')
        listview.refresh()
      } catch (e) {
        grunt.show_alert('Помилка: ' + e.message, 'error')
      }
    },
    { variant: isRecording ? 'destructive' : 'default' },
  )

  listview.add_button('Очистити', async function () {
    const ok = await grunt.confirm('Очистити буфер профілера?', 'Підтвердження')
    if (!ok) return
    try {
      await grunt.call({ method: 'grunt.api.v1.dev.clear_profiler' })
      grunt.show_alert('Буфер очищено', 'success')
      listview.refresh()
    } catch (e) {
      grunt.show_alert('Помилка: ' + e.message, 'error')
    }
  }, { variant: 'outline' })
}
