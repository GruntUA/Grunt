/**
 * EmailAccount — helper client script.
 *
 * Робить створення облікового запису максимально простим для Gmail і Microsoft 365:
 *  - автозаповнення SMTP/IMAP серверів і портів;
 *  - вхід через OAuth (ConnectedApp): «Підключити обліковий запис» / «Відключити»;
 *  - логін SMTP = email-адреса;
 *  - очищення пароля додатка від пробілів;
 *  - кнопки «Відкрити паролі додатків Google» та «Перевірити з'єднання».
 *
 * @param {FormProxy} frm
 */

// Те саме сервер підставляє в EmailAccount.validate (PRESETS) — тут лише для форми.
const PRESETS = {
    Gmail: {
        smtp_server: 'smtp.gmail.com',
        smtp_port: 587,
        use_tls: 1,
        imap_server: 'imap.gmail.com',
        imap_port: 993,
        use_ssl: 1,
    },
    'Microsoft 365': {
        smtp_server: 'smtp.office365.com',
        smtp_port: 587,
        use_tls: 1,
        imap_server: 'outlook.office365.com',
        imap_port: 993,
        use_ssl: 1,
    },
}

const OAUTH = 'grunt.integrations.oauth'

const APP_PASSWORDS_URL = 'https://myaccount.google.com/apppasswords'

/** @param {FormProxy} frm */
function _isGmail(frm) {
    return (frm.doc.provider || 'Gmail') === 'Gmail'
}

/** @param {FormProxy} frm */
function _isOAuth(frm) {
    return frm.doc.auth_method === 'OAuth'
}

/** @param {FormProxy} frm */
function _applyPreset(frm) {
    const preset = PRESETS[frm.doc.provider || 'Gmail']
    if (!preset) return
    for (const [field, value] of Object.entries(preset)) {
        frm.set_value(field, value)
    }
    frm.set_value('enable_outgoing', 1)
    if (frm.doc.email_address) frm.set_value('smtp_user', frm.doc.email_address)
    // Microsoft 365 вимкнув вхід за паролем — лише OAuth.
    if (frm.doc.provider === 'Microsoft 365') frm.set_value('auth_method', 'OAuth')
}

/** @param {FormProxy} frm */
export function on_load(frm) {
    // Повернення з OAuth-входу (grunt.integrations.oauth.callback).
    const params = new URLSearchParams(window.location.search)
    const outcome = params.get('oauth')
    if (outcome) {
        if (outcome === 'ok') grunt.show_alert(__('The account is connected'), 'success')
        else grunt.show_alert(`${__('Sign-in failed')}: ${params.get('message') || ''}`, 'error')
        params.delete('oauth')
        params.delete('message')
        const query = params.toString()
        window.history.replaceState(null, '', window.location.pathname + (query ? `?${query}` : ''))
    }
    if (!frm.is_new) {
        if (_isOAuth(frm)) _showOAuthProblem(frm)
        return
    }
    if (!frm.doc.provider) frm.set_value('provider', 'Gmail')
    _applyPreset(frm)
}

/** Попередження, якщо токен відкликано або вхід зроблено не тим обліковим записом. */
async function _showOAuthProblem(frm) {
    try {
        const res = await grunt.call(`${OAUTH}.status`, { doctype: 'EmailAccount', name: frm.doc.name })
        if (!res.connected) {
            grunt.show_alert(__('The account is not connected: click “Connect account”'), 'warning')
        } else if (res.error) {
            grunt.show_alert(`${__('The connection stopped working, connect the account again')}: ${res.error}`, 'error')
        } else if (res.account && frm.doc.email_address
            && res.account.toLowerCase() !== String(frm.doc.email_address).toLowerCase()) {
            grunt.show_alert(
                __('Access was allowed by {account}, not by {email}: mail is sent as {account}.')
                    .replaceAll('{account}', res.account)
                    .replaceAll('{email}', frm.doc.email_address),
                'warning',
            )
        }
    } catch {
        // Лише підказка — без неї форма працює.
    }
}

/** @param {FormProxy} frm */
async function _connect(frm) {
    if (frm.is_new || frm.is_dirty) {
        grunt.show_alert(__('Save the account first'), 'warning')
        return
    }
    if (!frm.doc.connected_app) {
        grunt.show_alert(__('Choose the connected app first'), 'warning')
        return
    }
    try {
        const res = await grunt.call(`${OAUTH}.authorize`, {
            connected_app: frm.doc.connected_app,
            doctype: 'EmailAccount',
            name: frm.doc.name,
        })
        window.location.href = res.url
    } catch (e) {
        grunt.show_alert(e?.message || String(e), 'error')
    }
}

/** @param {FormProxy} frm */
async function _disconnect(frm) {
    const ok = await grunt.confirm(
        __('The mailbox will stop sending and receiving mail until it is connected again. Access granted at the provider stays — revoke it in the account security settings if needed.'),
        __('Disconnect the account?'),
    )
    if (!ok) return
    try {
        await grunt.call(`${OAUTH}.disconnect`, { doctype: 'EmailAccount', name: frm.doc.name })
        grunt.show_alert(__('The account is disconnected'), 'success')
        await frm.reload()
    } catch (e) {
        grunt.show_alert(e?.message || String(e), 'error')
    }
}

/**
 * @param {FormProxy} frm
 * @param {string} fieldname
 */
export function on_change(frm, fieldname) {
    if (fieldname === 'provider') {
        _applyPreset(frm)
        return
    }

    if (fieldname === 'connect_oauth') {
        _connect(frm)
        return
    }

    if (fieldname === 'disconnect_oauth') {
        _disconnect(frm)
        return
    }

    if (fieldname === 'email_address' && PRESETS[frm.doc.provider || 'Gmail'] && frm.doc.email_address) {
        frm.set_value('smtp_user', frm.doc.email_address)
        return
    }

    // Пароль додатка Google — 16 літер без пробілів; прибираємо косметичні пробіли.
    if (fieldname === 'smtp_password' && _isGmail(frm) && frm.doc.smtp_password) {
        const cleaned = String(frm.doc.smtp_password).replace(/\s+/g, '')
        if (cleaned !== frm.doc.smtp_password) frm.set_value('smtp_password', cleaned)
        return
    }

    if (fieldname === 'open_app_passwords') {
        window.open(APP_PASSWORDS_URL, '_blank', 'noopener')
        return
    }

    if (fieldname === 'test_connection') {
        _testConnection(frm)
        return
    }

    if (fieldname === 'test_send') {
        _sendTest(frm)
    }
}

/** Перекладає технічну помилку SMTP у зрозумілу підказку. */
function _friendlySmtpError(raw) {
    const s = String(raw || '')
    if (/535|5\.7\.8|Username and Password not accepted|BadCredentials|Application-specific password/i.test(s)) {
        return __('Google rejected the sign-in. Use a 16-character «app password» (App Password), not the regular account password, and make sure 2-Step Verification is enabled.')
    }
    if (/WRONG_VERSION_NUMBER|wrong version number|SSL:|SSLV3|record layer/i.test(s)) {
        return __('Encryption and port mismatch. Gmail needs port 587 (STARTTLS) or 465 (SSL).')
    }
    if (/timed out|timeout|Connection refused|Name or service not known|getaddrinfo|nodename/i.test(s)) {
        return __('The server does not respond. Check the server address, port and network access.')
    }
    return s || __('Unknown error')
}

/** @param {FormProxy} frm */
async function _testConnection(frm) {
    if (!frm.doc.smtp_server) {
        grunt.show_alert(__('First choose a mail service or enter an SMTP server.'), 'warning')
        return
    }
    if (_isOAuth(frm) && (frm.is_new || frm.is_dirty)) {
        grunt.show_alert(__('Save the account first'), 'warning')
        return
    }
    if (!_isOAuth(frm) && !frm.doc.smtp_password && frm.is_new) {
        grunt.show_alert(__('Enter the SMTP password (for Gmail — an app password).'), 'warning')
        return
    }

    grunt.show_alert(__('Checking the connection…'), 'info')
    try {
        const res = await grunt.call('grunt.api.v1.email.test_smtp_connection', {
            smtp_server: frm.doc.smtp_server,
            smtp_port: frm.doc.smtp_port || 587,
            use_tls: frm.doc.use_tls ? 1 : 0,
            smtp_user: frm.doc.smtp_user || frm.doc.email_address || undefined,
            smtp_password: frm.doc.smtp_password || undefined,
            account_id: frm.is_new ? undefined : frm.doc.name,
        })
        if (res && res.success) {
            grunt.show_alert(__('Connection successful — signed in to the SMTP server.'), 'success')
        } else {
            grunt.show_alert(_friendlySmtpError(res && res.error), 'error')
        }
    } catch (e) {
        grunt.show_alert(_friendlySmtpError(e && e.message ? e.message : e), 'error')
    }
}

/** @param {FormProxy} frm */
async function _sendTest(frm) {
    if (frm.is_new) {
        grunt.show_alert(__('Save the account first, then send a test email.'), 'warning')
        return
    }
    const to = await grunt.prompt({ label: __('Recipient address'), title: __('Test email') })
    if (!to || !to.trim()) return

    grunt.show_alert(__('Sending a test email…'), 'info')
    try {
        const res = await grunt.call('grunt.api.v1.email.send_test_email', {
            account_id: frm.doc.name,
            recipient: to,
        })
        if (res && res.success) {
            grunt.show_alert(__('Test email sent to {to}.').replace('{to}', to), 'success')
        } else {
            grunt.show_alert(_friendlySmtpError(res && res.error), 'error')
        }
    } catch (e) {
        grunt.show_alert(_friendlySmtpError(e && e.message ? e.message : e), 'error')
    }
}
