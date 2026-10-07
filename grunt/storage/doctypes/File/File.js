/**
 * File list - personal file spaces. Folders come from the tree panel beside
 * the list (DocType.list_tree_field = "folder"); the list opens on «My files»,
 * uploads ask where to go (the open folder preselected), and files dragged
 * in from the desktop land in the folder they are dropped on.
 */

/** @param {ListViewProxy} listview */
function setup_list(listview) {
  const openFolder = (lv) => {
    const open = lv.filters.find((f) => f.fieldname === 'folder' && f.op === '=')
    return open ? open.value : null
  }

  const showFolder = async (lv, folder) => {
    const doc = await grunt.api.get(`/api/v1/docs/FileFolder/${folder}`)
    const row = doc.data ?? doc
    lv.set_filters([{
      fieldname: 'folder',
      op: '=',
      value: folder,
      label: __('Folder'),
      fieldtype: 'Link',
      displayValue: row.is_home && row.space_user === grunt.session.user ? __('My files') : row.folder_name,
    }])
  }

  const upload = async (lv, opts) => {
    const files = await grunt.upload_files({ multiple: true, ...opts })
    if (!files.length) return
    grunt.show_alert(
      files.length === 1 ? __('File uploaded') : __('Files uploaded: {n}', { n: files.length }),
      'success',
    )
    // Like Explorer: end up in the folder the files went to.
    const target = files[0].folder
    if (target && target !== openFolder(lv)) await showFolder(lv, target)
    lv.refresh()
  }

  listview.actions.update('add', {
    label: __('Upload'),
    icon: 'upload',
    action: (lv) => upload(lv, { folder: openFolder(lv), choose_folder: true }),
  })

  // Dropped on a folder - straight in; dropped on the list - ask where.
  listview.drop_files = (lv, files, target) =>
    upload(lv, target ? { files, folder: target } : { files, folder: openFolder(lv), choose_folder: true })

  // Nothing filtered (the menu link, a fresh visit) - open «My files».
  if (!listview.filters.length) {
    grunt.call('grunt.storage.doctypes.FileFolder.file_folder.get_home_folder')
      .then((home) => showFolder(listview, home.name))
  }
}
