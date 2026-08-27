/**
 * EmailAccount — helper client script.
 *
 * Робить створення облікового запису максимально простим для Gmail:
 *  - автозаповнення SMTP/IMAP серверів і портів;
 *  - логін SMTP = email-адреса;
 *  - очищення пароля додатка від пробілів;
 *  - кнопки «Відкрити паролі додатків Google» та «Перевірити з'єднання».
 *
 * @param {FormProxy} frm
 */

const GMAIL_DEFAULTS = {
    smtp_server: 'smtp.gmail.com',
    smtp_port: 587,
    use_tls: 1,
    imap_server: 'imap.gmail.com',
    imap_port: 993,
    use_ssl: 1,
}

const APP_PASSWORDS_URL = 'https://myaccount.google.com/apppasswords'

/** @param {FormProxy} frm */
function _isGmail(frm) {
    return (frm.doc.provider || 'Gmail') === 'Gmail'
}

/** @param {FormProxy} frm */
function _applyGmailDefaults(frm) {
    for (const [field, value] of Object.entries(GMAIL_DEFAULTS)) {
        frm.set_value(field, value)
    }
    frm.set_value('enable_outgoing', 1)
    if (frm.doc.email_address) frm.set_value('smtp_user', frm.doc.email_address)
}

/** @param {FormProxy} frm */
function on_load(frm) {
    if (!frm.is_new) return
    if (!frm.doc.provider) frm.set_value('provider', 'Gmail')
    if (_isGmail(frm)) _applyGmailDefaults(frm)
}

/**
 * @param {FormProxy} frm
 * @param {string} fieldname
 */
function on_change(frm, fieldname) {
    if (fieldname === 'provider' && _isGmail(frm)) {
        _applyGmailDefaults(frm)
        return
    }

    if (fieldname === 'email_address' && _isGmail(frm) && frm.doc.email_address) {
        frm.set_value('smtp_user', frm.doc.email_address)
        return
    }

    if (fieldname === 'smtp_password' && frm.doc.smtp_password) {
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
    }
}

/** Перекладає технічну помилку SMTP у зрозумілу підказку. */
function _friendlySmtpError(raw) {
    const s = String(raw || '')
    if (/535|5\.7\.8|Username and Password not accepted|BadCredentials|Application-specific password/i.test(s)) {
        return 'Google відхилив вхід. Використайте 16-значний «пароль додатка» (App Password), а не звичайний пароль акаунта, і переконайтесь, що увімкнена двоетапна перевірка.'
    }
    if (/WRONG_VERSION_NUMBER|wrong version number|SSL:|SSLV3|record layer/i.test(s)) {
        return 'Невідповідність шифрування та порту. Для Gmail потрібен порт 587 (STARTTLS) або 465 (SSL).'
    }
    if (/timed out|timeout|Connection refused|Name or service not known|getaddrinfo|nodename/i.test(s)) {
        return 'Сервер не відповідає. Перевірте адресу сервера, порт і доступ до мережі.'
    }
    return s || 'Невідома помилка'
}

/** @param {FormProxy} frm */
async function _testConnection(frm) {
    if (!frm.doc.smtp_server) {
        grunt.show_alert('Спочатку оберіть поштову службу або вкажіть SMTP-сервер.', 'warning')
        return
    }
    if (!frm.doc.smtp_password) {
        grunt.show_alert('Вкажіть пароль SMTP (для Gmail — пароль додатка).', 'warning')
        return
    }

    grunt.show_alert('Перевіряємо з\'єднання…', 'info')
    try {
        const res = await grunt.call('grunt.api.v1.email.test_smtp_connection', {
            smtp_server: frm.doc.smtp_server,
            smtp_port: frm.doc.smtp_port || 587,
            use_tls: frm.doc.use_tls ? 1 : 0,
            smtp_user: frm.doc.smtp_user || frm.doc.email_address || undefined,
            smtp_password: frm.doc.smtp_password || undefined,
        })
        if (res && res.success) {
            grunt.show_alert('З\'єднання успішне — вхід на SMTP-сервер пройшов.', 'success')
        } else {
            grunt.show_alert(_friendlySmtpError(res && res.error), 'error')
        }
    } catch (e) {
        grunt.show_alert(_friendlySmtpError(e && e.message ? e.message : e), 'error')
    }
}
