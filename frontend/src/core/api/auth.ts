import client from './client'

export interface MfaSetupInfo {
    secret: string
    qr_svg: string
}

export const authApi = {
    async setupMfa(): Promise<MfaSetupInfo> {
        const { data } = await client.post('/api/v1/method/grunt.auth.doctypes.User.user.setup_mfa')
        return data.data
    },

    async confirmMfa(code: string): Promise<string[]> {
        const { data } = await client.post('/api/v1/method/grunt.auth.doctypes.User.user.confirm_mfa', { code })
        return data.data.backup_codes
    },

    async disableMfa(): Promise<void> {
        await client.post('/api/v1/method/grunt.auth.doctypes.User.user.disable_mfa')
    },

    async verifyMfaLogin(mfaToken: string, code: string) {
        const { data } = await client.post('/api/v1/method/grunt.auth.doctypes.User.user.mfa_login_api', {
            mfa_token: mfaToken,
            code
        })
        return data.data
    }
}
