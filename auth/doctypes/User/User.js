// Client script for User
//
// Available objects:
//   frm.doc                              — current document data (live, always up-to-date)
//   frm.doc.fieldname                    — read a field value
//   frm.is_new                           — true if document is not yet saved
//   frm.fields                           — list of field definitions
//
// Form helpers:
//   frm.get_value(fieldname)             — read a field value
//   frm.set_value(fieldname, value)      — set a field value
//   frm.toggle_display(fieldname, show)  — show/hide a field (true = visible)
//   frm.toggle_reqd(fieldname, reqd)     — make field required/optional
//   frm.set_df_property(field, prop, v)  — set any field property
//   frm.add_button(label, action, opts)  — add a custom button to the form
//   frm.save()                           — save the document
//
// Framework helpers:
//   grunt.call({ method, args })         — call a server script (POST /api/v1/method/...)
//   grunt.msgprint(msg)                  — show info dialog
//   grunt.msgprint({ message, title })   — show dialog with title
//   grunt.show_alert(msg, type)          — show toast (type: success/error/info/warning)
//   grunt.confirm(msg)                   — show confirm dialog (returns Promise<boolean>)
//   grunt.throw(msg)                     — throw an error and stop execution

function on_load(frm) {
  // Called once when the form loads — add buttons, set initial state
}

function on_change(frm, fieldname) {
  // Called when any field value changes
}

function validate(frm) {
  // Called before save — return false to cancel
  return true
}
