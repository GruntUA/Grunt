/**
 * ApiTest Client Script
 *
 * Викликається на UI сторінці при редагуванні ApiTest.
 */

function on_load(frm) {
    // Код що виконується при завантаженні форми
    console.log('Loaded ApiTest', frm.doc)
}

function on_save(frm) {
    // Код що виконується при збереженні форми
    console.log('Saved ApiTest', frm.doc)
}
