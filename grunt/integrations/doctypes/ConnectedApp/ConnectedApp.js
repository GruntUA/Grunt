/**
 * Підключений застосунок — підказує redirect URI, який треба вписати в
 * налаштуваннях OAuth-застосунку в Google Cloud / Microsoft Entra.
 */

const CALLBACK = '/api/v1/method/grunt.integrations.oauth.callback'

const CONSOLES = {
    Google: 'https://console.cloud.google.com/apis/credentials',
    Microsoft: 'https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade',
}

/** @param {FormProxy} frm */
function _describe(frm) {
    const uri = window.location.origin + CALLBACK
    const registry = CONSOLES[frm.doc.provider]
    const lines = [`${__('Redirect URI to register in the app')}: ${uri}`]
    if (registry) lines.push(`${__('Apps are registered at')}: ${registry}`)
    frm.set_df_property('client_id', 'description', lines.join('\n'))
}

/** @param {FormProxy} frm */
export function on_load(frm) {
    _describe(frm)
}

/**
 * @param {FormProxy} frm
 * @param {string} fieldname
 */
export function on_change(frm, fieldname) {
    if (fieldname === 'provider') _describe(frm)
}
