import i18n from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

/**
 * Thin browser-side glue for the WebAuthn provider (`/api/v1/auth/webauthn/*`).
 *
 * The backend (py_webauthn) speaks the "…OptionsJSON" dialect - every binary
 * field is base64url. This module converts those to the `ArrayBuffer`s that
 * `navigator.credentials` wants, runs the ceremony, and serialises the
 * resulting `PublicKeyCredential` back to the same base64url JSON shape the
 * backend verifies.
 */

// base64url ↔ bytes

function b64urlToBuffer(value: string): ArrayBuffer {
  const pad = value.length % 4 === 0 ? '' : '='.repeat(4 - (value.length % 4))
  const b64 = value.replace(/-/g, '+').replace(/_/g, '/') + pad
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out.buffer
}

function bytesToB64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let bin = ''
  for (const b of bytes) bin += String.fromCharCode(b)
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

// option decoders

interface DescriptorJSON {
  id: string
  type: 'public-key'
  transports?: string[]
}

function decodeDescriptors(list: DescriptorJSON[] | undefined) {
  return (list ?? []).map((d) => ({
    id: b64urlToBuffer(d.id),
    type: d.type,
    ...(d.transports ? { transports: d.transports } : {}),
  }))
}

function decodeCreationOptions(o: Record<string, any>): PublicKeyCredentialCreationOptions {
  return {
    ...o,
    challenge: b64urlToBuffer(o.challenge),
    user: { ...o.user, id: b64urlToBuffer(o.user.id) },
    excludeCredentials: decodeDescriptors(o.excludeCredentials),
  } as unknown as PublicKeyCredentialCreationOptions
}

function decodeRequestOptions(o: Record<string, any>): PublicKeyCredentialRequestOptions {
  return {
    ...o,
    challenge: b64urlToBuffer(o.challenge),
    allowCredentials: decodeDescriptors(o.allowCredentials),
  } as unknown as PublicKeyCredentialRequestOptions
}

// credential encoders

function encodeCredential(cred: PublicKeyCredential): Record<string, any> {
  const response = cred.response as AuthenticatorResponse & Record<string, any>
  const out: Record<string, any> = {
    id: cred.id,
    rawId: bytesToB64url(cred.rawId),
    type: cred.type,
    clientExtensionResults: cred.getClientExtensionResults(),
    authenticatorAttachment: cred.authenticatorAttachment ?? undefined,
    response: {
      clientDataJSON: bytesToB64url(response.clientDataJSON),
    },
  }
  if ('attestationObject' in response && response.attestationObject) {
    out.response.attestationObject = bytesToB64url(response.attestationObject)
    if (typeof response.getTransports === 'function') {
      out.response.transports = response.getTransports()
    }
  }
  if ('authenticatorData' in response && response.authenticatorData) {
    out.response.authenticatorData = bytesToB64url(response.authenticatorData)
    out.response.signature = bytesToB64url(response.signature)
    if (response.userHandle) out.response.userHandle = bytesToB64url(response.userHandle)
  }
  return out
}

// public API

export function isWebAuthnSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    !!window.PublicKeyCredential &&
    typeof navigator.credentials?.create === 'function'
  )
}

/** Run a registration ceremony for the given backend options; returns the
 *  serialised credential to POST to `.../enroll/complete`. */
export async function createPasskey(
  optionsJSON: Record<string, any>,
): Promise<Record<string, any>> {
  const cred = (await navigator.credentials.create({
    publicKey: decodeCreationOptions(optionsJSON),
  })) as PublicKeyCredential | null
  if (!cred) throw new Error(t('Key registration cancelled'))
  return encodeCredential(cred)
}

/** Run an authentication ceremony; returns the serialised assertion to POST to
 *  `.../complete`. */
export async function getPasskeyAssertion(
  optionsJSON: Record<string, any>,
): Promise<Record<string, any>> {
  const cred = (await navigator.credentials.get({
    publicKey: decodeRequestOptions(optionsJSON),
  })) as PublicKeyCredential | null
  if (!cred) throw new Error(t('Authentication cancelled'))
  return encodeCredential(cred)
}
