/**
 * Хмарне сховище — кнопки форми: перевірка з'єднання, підключення облікового
 * запису (вставити токен rclone або вхід через власний OAuth-додаток),
 * rclone-конфіг для аварійного відновлення, бекапи в сховищі, перенесення файлів.
 * Усе виконує сервер (grunt/storage/doctypes/StorageRemote/storage_remote.py);
 * довгі дії йдуть у воркер, прогрес — у панелі задач.
 */

const API = 'grunt.storage.doctypes.StorageRemote.storage_remote'

/** @param {FormProxy} frm */
function on_load(frm) {
    // Повернення з OAuth-входу (grunt.storage.cloud.oauth.callback).
    const params = new URLSearchParams(window.location.search)
    const outcome = params.get('cloud_auth')
    if (outcome) {
        if (outcome === 'ok') grunt.show_alert(__('The account is connected'), 'success')
        else grunt.show_alert(`${__('Sign-in failed')}: ${params.get('message') || ''}`, 'error')
        params.delete('cloud_auth')
        params.delete('message')
        const query = params.toString()
        window.history.replaceState(null, '', window.location.pathname + (query ? `?${query}` : ''))
    }
}

/** Дії над збереженим сховищем: нове чи змінене спершу треба зберегти. */
function _saved(frm) {
    if (frm.is_new || frm.is_dirty) {
        grunt.show_alert(__('Save the storage first'), 'warning')
        return false
    }
    return true
}

async function _call(method, args) {
    return grunt.call({ method: `${API}.${method}`, args })
}

/**
 * @param {FormProxy} frm
 * @param {string} fieldname
 */
async function on_change(frm, fieldname) {
    const handler = BUTTONS[fieldname]
    if (!handler) return
    if (!_saved(frm)) return
    try {
        await handler(frm)
    } catch (e) {
        grunt.show_alert(e?.message || String(e), 'error')
    }
}

const BUTTONS = {
    async test_connection(frm) {
        grunt.show_alert(__('Checking the connection…'), 'info')
        const res = await _call('test_connection', { name: frm.doc.name })
        if (res.ok) grunt.show_alert(`${__('Connection works')}${res.quota ? ` — ${res.quota}` : ''}`, 'success')
        else grunt.show_alert(res.error, 'error')
        await frm.reload()
    },

    async paste_token(frm) {
        const { command } = await _call('oauth_help', { name: frm.doc.name })
        const values = await grunt.form({
            title: __('Paste a token from rclone'),
            primaryLabel: __('Connect'),
            fields: [
                {
                    fieldname: 'help',
                    label: '',
                    fieldtype: 'HTML',
                    plain: true,
                    default: `<ol class="list-decimal pl-5 space-y-1 text-sm">
                        <li>${__('On any computer with a browser install rclone')}: <a class="underline" href="https://rclone.org/downloads/" target="_blank" rel="noopener">rclone.org/downloads</a></li>
                        <li>${__('Run in a terminal')}: <code class="rounded bg-muted px-1">${command}</code></li>
                        <li>${__('Sign in in the browser window that opens and allow access')}</li>
                        <li>${__('Copy the whole line rclone prints (it starts with access_token) and paste it below')}</li>
                    </ol>`,
                },
                { fieldname: 'token', label: __('Token'), fieldtype: 'LongText', required: true },
            ],
        })
        if (!values) return
        const res = await grunt.call({ method: 'grunt.storage.cloud.oauth.set_token', args: { name: frm.doc.name, token: values.token } })
        grunt.show_alert(`${__('The account is connected')}${res.account ? `: ${res.account}` : ''}`, 'success')
        await frm.reload()
    },

    async authorize(frm) {
        const res = await grunt.call({ method: 'grunt.storage.cloud.oauth.authorize', args: { name: frm.doc.name } })
        const go = await grunt.confirm(
            `${__('The redirect URI registered in your app must be exactly')}:\n${res.redirect_uri}`,
            __('Sign in through the browser'),
        )
        if (go) window.location.href = res.url
    },

    async show_config(frm) {
        const { config } = await _call('show_config', { name: frm.doc.name })
        await grunt.form({
            title: __('rclone config'),
            primaryLabel: __('Close'),
            size: 'large',
            fields: [
                {
                    fieldname: 'config',
                    label: '',
                    fieldtype: 'Code',
                    default: config,
                    read_only: true,
                    description: __('Save it as rclone.conf somewhere outside this system. Passwords are only obscured, not encrypted — keep the file private. To get a backup back: rclone copy secret:backups/<site>/ ./ (or remote: without encryption).'),
                },
            ],
        })
    },

    async upload_latest(frm) {
        await _call('upload_latest', { name: frm.doc.name })
        grunt.show_alert(__('Upload started'), 'success')
    },

    async browse_backups(frm) {
        await pickCloudBackup(frm.doc.name)
    },

    async offload_now(frm) {
        if (!(await grunt.confirm(__('Move the files that fit the rules to the storage now?')))) return
        await _call('offload_now', { name: frm.doc.name })
        grunt.show_alert(__('Moving started'), 'success')
    },

    async recall_files(frm) {
        if (!(await grunt.confirm(__('Download every file kept in this storage back to the server disk?')))) return
        await _call('recall_files', { name: frm.doc.name })
        grunt.show_alert(__('Returning started'), 'success')
    },
}

/** Список копій у сховищі → вибрана завантажується на сервер (у «Резервні копії»). */
async function pickCloudBackup(name) {
    const rows = await _call('list_backups', { name })
    if (!rows.length) {
        grunt.show_alert(__('No backups in this storage yet'), 'info')
        return
    }
    const picked = await grunt.select({
        title: __('Backups in the storage'),
        multiple: false,
        primaryLabel: __('Download to the server'),
        description: __('The chosen set appears in Backups; restore it with «grunt db restore <id>» on the server.'),
        columns: [
            { key: 'id', label: __('Backup') },
            { key: 'kinds', label: __('Parts') },
            { key: 'size', label: __('Size'), width: '110px' },
            { key: 'on_server', label: __('On the server'), width: '120px' },
        ],
        rows,
    })
    if (!picked) return
    if (picked.on_server) {
        grunt.show_alert(__('This backup is already on the server'), 'info')
        return
    }
    await _call('fetch_backup', { name, backup_id: picked.id })
    grunt.show_alert(__('Download started'), 'success')
}
