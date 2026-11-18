/**
 * Role form: warn when the role does nothing yet - nobody holds it, or no
 * document type has a rule for it and it holds no permission
 * (grunt.permissions.warnings).
 */

function _escape(text) {
    return String(text).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
}

export async function on_load(frm) {
    if (frm.is_new || !grunt.has_perm('grunt.manage_permissions')) return
    try {
        const warnings = await grunt.call('grunt.api.v1.permission_warnings.for_role', {
            role: frm.doc.role_name || frm.doc.name,
        })
        for (const w of warnings || []) frm.dashboard.add_comment(_escape(w.message), 'orange')
    } catch (e) {
        // A hint, not a requirement - the form works without it.
    }
}
