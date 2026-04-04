/// <reference types="vite/client" />

import type { grunt as GruntInstance } from '@/core/grunt'

declare global {
  interface Window {
    grunt: typeof GruntInstance
    frappe: typeof GruntInstance
  }
}
