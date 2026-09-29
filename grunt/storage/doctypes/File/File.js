/**
 * File list — the file library. Folders come from the tree panel beside the
 * list (DocType.list_tree_field = "folder"); uploads land in the folder that
 * is open there.
 */

/** @param {ListViewProxy} listview */
function setup_list(listview) {
  listview.actions.update('add', {
    label: __('Upload'),
    icon: 'upload',
    action: async (lv) => {
      const open = lv.filters.find((f) => f.fieldname === 'folder' && f.op === '=')
      const files = await grunt.upload_files({ folder: open ? open.value : null, multiple: true })
      if (!files.length) return
      grunt.show_alert(
        files.length === 1 ? __('File uploaded') : __('Files uploaded: {n}', { n: files.length }),
        'success',
      )
      lv.refresh()
    },
  })
}
