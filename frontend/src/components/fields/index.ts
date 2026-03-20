import type { Component } from 'vue'

export const fieldComponents: Record<string, () => Promise<Component>> = {
  Text:        () => import('./FieldText.vue').then((m) => m.default),
  LongText:    () => import('./FieldLongText.vue').then((m) => m.default),
  Int:         () => import('./FieldInt.vue').then((m) => m.default),
  Float:       () => import('./FieldFloat.vue').then((m) => m.default),
  Check:       () => import('./FieldCheck.vue').then((m) => m.default),
  Date:        () => import('./FieldDate.vue').then((m) => m.default),
  Datetime:    () => import('./FieldDatetime.vue').then((m) => m.default),
  Time:        () => import('./FieldText.vue').then((m) => m.default),
  Select:      () => import('./FieldSelect.vue').then((m) => m.default),
  Link:        () => import('./FieldLink.vue').then((m) => m.default),
  MultiLink:   () => import('./FieldText.vue').then((m) => m.default),
  Attach:      () => import('./FieldAttach.vue').then((m) => m.default),
  Image:       () => import('./FieldImage.vue').then((m) => m.default),
  RichText:    () => import('./FieldRichText.vue').then((m) => m.default),
  Table:       () => import('./FieldTable.vue').then((m) => m.default),
  Color:       () => import('./FieldColor.vue').then((m) => m.default),
  JSON:        () => import('./FieldJson.vue').then((m) => m.default),
  Code:        () => import('./FieldCode.vue').then((m) => m.default),
  Geolocation: () => import('./FieldGeolocation.vue').then((m) => m.default),
  Signature:   () => import('./FieldText.vue').then((m) => m.default),
}

export const FallbackField = () => import('./FieldText.vue').then((m) => m.default)
