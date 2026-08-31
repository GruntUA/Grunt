import client from './client'

export interface MfaSetupInfo {
    secret: string
    qr_svg: string
}

export interface AuthMethod {
    name: string
    label: string
    kind: 'redirect' | 'challenge'
    icon: string | null
    requires_identifier: boolean
    supports_enrollment: boolean
}

export interface Passkey {
    name: string
    label: string
    last_used_at: string | null
    backed_up: boolean
    transports: string[]
    created_at: string | null
}

const METHOD = '/api/v1/method/grunt.auth.doctypes.User.user'
const PASSKEY = '/api/v1/method/grunt.auth.doctypes.WebAuthnCredential.web_authn_credential'

export const authApi = {
    async setupMfa(): Promise<MfaSetupInfo> {
        const { data } = await client.post(`${METHOD}.setup_mfa`)
        return data.data
    },

    async confirmMfa(code: string): Promise<string[]> {
        const { data } = await client.post(`${METHOD}.confirm_mfa`, { code })
        return data.data.backup_codes
    },

    async disableMfa(): Promise<void> {
        await client.post(`${METHOD}.disable_mfa`)
    },

    async register(email: string, password: string, fullName: string): Promise<{ approval_pending: boolean }> {
        const { data } = await client.post(`${METHOD}.register_full_name_api`, {
            email,
            password,
            full_name: fullName,
        })
        return { approval_pending: !!data.data?.approval_pending }
    },

    async verifyMfaLogin(mfaToken: string, code: string) {
        const { data } = await client.post(`${METHOD}.mfa_login_api`, {
            mfa_token: mfaToken,
            code
        })
        return data.data
    },

    // ── Pluggable auth providers ──────────────────────────────────────────

    async listMethods(): Promise<AuthMethod[]> {
        const { data } = await client.get('/api/v1/auth/methods')
        return data.data
    },

    async begin(provider: string, payload: Record<string, unknown> = {}) {
        const { data } = await client.post(`/api/v1/auth/${provider}/begin`, payload)
        return data.data
    },

    async complete(provider: string, payload: Record<string, unknown>) {
        const { data } = await client.post(`/api/v1/auth/${provider}/complete`, payload)
        return data.data
    },

    async enrollBegin(provider: string, payload: Record<string, unknown> = {}) {
        const { data } = await client.post(`/api/v1/auth/${provider}/enroll/begin`, payload)
        return data.data
    },

    async enrollComplete(provider: string, payload: Record<string, unknown>) {
        const { data } = await client.post(`/api/v1/auth/${provider}/enroll/complete`, payload)
        return data.data
    },

    // ── Passkey management (signed-in user) ──────────────────────────────

    async listPasskeys(): Promise<Passkey[]> {
        const { data } = await client.get(`${PASSKEY}.list_my_passkeys`)
        return data.data
    },

    async renamePasskey(name: string, label: string): Promise<void> {
        await client.post(`${PASSKEY}.rename_passkey`, { name, label })
    },

    async deletePasskey(name: string): Promise<void> {
        await client.post(`${PASSKEY}.delete_passkey`, { name })
    }
}
