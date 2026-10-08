import { describe, expect, it } from 'vitest'
import { extractFileId, isExternalUrl, linkFilename } from '@/core/fileUtils'

describe('file links', () => {
  const link = 'https://backend.hromada.gov.ua/storage/uploads/files/%D0%90%20b.pdf?time=1743588653'

  it('names a link by the decoded last part of its path', () => {
    expect(linkFilename(link)).toBe('А b.pdf')
    expect(linkFilename('https://x.test/docs/')).toBe('docs')
  })

  it('tells links to files elsewhere from stored files', () => {
    const stored = '/api/v1/method/grunt.storage.doctypes.File.file.get_content?file_id=abc'
    expect(isExternalUrl(link)).toBe(true)
    expect(isExternalUrl(stored)).toBe(false)
    expect(extractFileId(stored)).toBe('abc')
    expect(extractFileId(link)).toBeNull()
  })
})
