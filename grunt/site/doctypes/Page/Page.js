function on_load(frm) {
  if (!frm.is_new) {
    frm.add_button('Відкрити конструктор', () => {
      grunt.set_route('page', frm.doc.name)
    }, { icon: 'layout-dashboard', variant: 'primary' })
  }
}
