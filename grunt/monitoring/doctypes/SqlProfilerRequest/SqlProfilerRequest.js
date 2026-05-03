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
  let isRecording = true
  try {
    const res = await grunt.api.get('/api/v1/dev/profiler/settings')
    isRecording = res.data.enabled
  } catch (_) {}

  const toggleBtn = listview.add_button(
    isRecording ? '⏹ Зупинити' : '▶ Старт',
    async function () {
      try {
        const res = await grunt.api.put('/api/v1/dev/profiler/settings', { enabled: !isRecording })
        isRecording = res.data.enabled
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
      await grunt.api.delete('/api/v1/dev/profiler/clear')
      grunt.show_alert('Буфер очищено', 'success')
      listview.refresh()
    } catch (e) {
      grunt.show_alert('Помилка: ' + e.message, 'error')
    }
  }, { variant: 'outline' })
}
