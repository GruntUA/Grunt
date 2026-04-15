import client from './client'

export interface MfaSetupInfo {
    secret: string
    qr_svg: string
}

export const authApi = {
    async setupMfa(): Promise<MfaSetupInfo> {
        const { data } = await client.post('/api/v1/auth/mfa/setup')
        return data.data
    },

    async confirmMfa(code: string): Promise<string[]> {
        const { data } = await client.post('/api/v1/auth/mfa/confirm', { code })
        return data.data.backup_codes
    },

    async disableMfa(): Promise<void> {
        await client.delete('/api/v1/auth/mfa/disable')
    },

    async verifyMfaLogin(mfaToken: string, code: string) {
        const { data } = await client.post('/api/v1/auth/mfa-login', {
            mfa_token: mfaToken,
            code
        })
        return data
    }
}
