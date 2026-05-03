/**
 * Client Script for DocType
 */

function setup_list(listview) {
    listview.add_button('Designer (Studio)', () => {
        window.open('/grunt/studio/DocType', '_blank')
    }, { variant: 'secondary' })
}

async function on_load(frm) {
    // Add Studio button for existing DocTypes
    if (frm.doc && frm.doc.name && !frm.is_new) {
        frm.add_button('Designer (Studio)', () => {
            const workspace = frm.doc.module === 'core' ? 'grunt' : (frm.doc.module || 'grunt')
            window.open(`/${workspace}/studio/DocType/${frm.doc.name}`, '_blank')
        }, { variant: 'primary' })
    }

    // Load apps and populate selects
    try {
        const result = await grunt.api.get('/api/v1/docs/GruntInstalledApp')
        const apps = result?.data || []
        window._dtAppsCache = apps

        // Populate app options
        const appOptions = apps.map(a => a.name).join('\n')
        frm.set_df_property('app', 'options', appOptions)

        // For existing docs — reverse-lookup app from current module
        const currentModule = frm.get_value('module')
        if (currentModule) {
            const matchingApp = apps.find(a => (a.modules || []).includes(currentModule))
            if (matchingApp) {
                frm.set_value('app', matchingApp.name)
                frm.set_df_property('module', 'options', (matchingApp.modules || []).join('\n'))
                frm.set_df_property('module', 'description', '')
            }
        }

        // For new docs, make app and module required
        if (frm.is_new) {
            frm.toggle_reqd('app', true)
            frm.toggle_reqd('module', true)
        }
    } catch (e) {
        grunt.show_alert('Не вдалося завантажити список додатків', 'error')
    }
}

async function on_change(frm, fieldname) {
    if (fieldname !== 'app') return

    const selectedApp = frm.get_value('app')

    // Clear module when app is deselected
    if (!selectedApp) {
        frm.set_df_property('module', 'options', '')
        frm.set_value('module', '')
        return
    }

    let apps = window._dtAppsCache
    if (!apps || !apps.length) {
        try {
            const result = await grunt.api.get('/api/v1/docs/GruntInstalledApp')
            apps = result?.data || []
            window._dtAppsCache = apps
        } catch (e) {
            return
        }
    }

    const app = apps.find(a => a.name === selectedApp)
    if (app) {
        // Clear module selection, update options, remove hint
        frm.set_value('module', '')
        frm.set_df_property('module', 'options', (app.modules || []).join('\n'))
        frm.set_df_property('module', 'description', '')
    }
}

// Export for the executor
window.doc_type_on_load = on_load
window.doc_type_on_change = on_change
window.doc_type_setup_list = setup_list

if (typeof on_load === 'function') { window.on_load = on_load }
if (typeof on_change === 'function') { window.on_change = on_change }
if (typeof setup_list === 'function') { window.setup_list = setup_list }
