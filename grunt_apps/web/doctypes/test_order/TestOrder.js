/**
 * {name} Client Script
 *
 * Викликається на UI сторінці при редагуванні {name}.
 */

function on_load(frm) {
    // Код що виконується при завантаженні форми
    console.log('Loaded {name}', frm.doc)
}

function on_save(frm) {
    // Код що виконується при збереженні форми
    console.log('Saved {name}', frm.doc)
}
