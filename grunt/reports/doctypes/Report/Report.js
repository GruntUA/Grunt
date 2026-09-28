// Report — кнопка переходу на рендер звіту (/<workspace>/report/<report_name>).

function on_load(frm) {
  frm.actions.add({
    id: 'view_report',
    label: 'View report',
    icon: 'file-bar-chart-2',
    visible: (f) => !f.is_new && !!f.doc.report_name,
    action: (f) => grunt.set_route('report', f.doc.report_name),
  })
}
