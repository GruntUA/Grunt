/**
 * Validation-error channel for the form renderer tree.
 *
 * `FormRenderer` provides the whole form's error map (fieldname → message).
 * `FieldRenderer` reads its own entry as a fallback when no explicit `error`
 * prop was passed. Container fields that render a sub-form (EmbeddedForm, and
 * later Table rows) re-provide the context with an extended `prefix`, so a
 * nested field named `voltage` inside the `spec` field looks up
 * `errors["spec.voltage"]`.
 *
 * The error map is expected to be flat with dot-separated paths for nesting.
 */
import type { ComputedRef, InjectionKey } from 'vue'

export interface FormErrorContext {
  /** Whole-form map: dot-path fieldname → message. */
  errors: ComputedRef<Record<string, string>>
  /** Path prefix for the current nesting level, e.g. "" or "spec.". */
  prefix: string
}

export const FORM_ERRORS: InjectionKey<FormErrorContext> = Symbol('form-errors')
