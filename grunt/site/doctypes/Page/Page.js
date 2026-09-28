function on_load(frm) {
  frm.actions.add({
    id: 'open_builder',
    label: __('Open builder'),
    icon: 'layout-dashboard',
    variant: 'primary',
    visible: (f) => !f.is_new,
    action: (f) => grunt.set_route('page', f.doc.name),
  })
}
