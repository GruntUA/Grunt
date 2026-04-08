/**
 * TestPayment Client Script
 *
 * Викликається на UI сторінці при редагуванні TestPayment.
 */

function on_load(frm) {
    // Код що виконується при завантаженні форми
    console.log('Loaded TestPayment', frm.doc)
}

function on_save(frm) {
    // Код що виконується при збереженні форми
    console.log('Saved TestPayment', frm.doc)
}
