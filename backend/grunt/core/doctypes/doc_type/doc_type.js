/**
 * Client Script for DocType
 */

function setup_list(listview) {
    // Add a button to the list view to open the designer for the selected doctype
    listview.add_button('Designer (Studio)', () => {
        // In Grunt, listview doesn't easily expose selected rows to these buttons yet,
        // so we'll just open the general Studio home or prompt for a doctype.
        // However, if we are in the DocType list, we want to edit the doctypes.
        window.open('/grunt/studio/DocType', '_blank')
    }, { variant: 'secondary' })
}

function on_load(frm) {
    // Add a prominent button to the form header to open this DocType in Studio
    if (frm.doc && frm.doc.name && !frm.is_new) {
        frm.add_button('Designer (Studio)', () => {
            const workspace = frm.doc.module === 'core' ? 'grunt' : 'hrm' // Simplistic workspace detection
            // Use the new route for the builder
            window.open(`/${workspace}/studio/DocType/${frm.doc.name}`, '_blank')
        }, { variant: 'primary' })
    }
}

// Export for the executor
window.doc_type_on_load = on_load
window.doc_type_setup_list = setup_list

// And also define them globally as expected by the executor's "new Function" scope
if (typeof on_load === 'function') { window.on_load = on_load }
if (typeof setup_list === 'function') { window.setup_list = setup_list }
