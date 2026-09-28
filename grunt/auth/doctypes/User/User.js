// User DocType — Client Script

function on_load(frm) {
  // Sensitive fields: always hidden / read-only
  frm.set_df_property("hashed_password", "hidden", true);
  frm.set_df_property("mfa_secret", "hidden", true);
  frm.set_df_property("mfa_backup_codes", "hidden", true);
  frm.set_df_property("login_attempts", "read_only", true);
  frm.set_df_property("locked_until", "read_only", true);

  frm.set_df_property("mfa_backup_display", "hidden", !frm.doc.mfa_enabled);

  // Passkeys are enrolled against the *logged-in* session, so only expose the
  // manager on a saved record (your own profile).
  frm.set_df_property("passkeys_button", "hidden", frm.is_new);

  const saved = (f) => !f.is_new;

  frm.actions.add({
    id: "change_password",
    label: __('Change password'),
    icon: "key-round",
    visible: saved,
    action: async () => {
      const user_id = frm.doc.name;
      if (!user_id) return;

      // Own password: prove knowledge of the current one — unless there is none
      // yet (signed up via email link / OIDC). Admins skip the check entirely.
      const isSelf = user_id === grunt.session.user;
      const isAdmin = (grunt.session.roles || []).includes("System Manager");
      const needCurrent = isSelf && !isAdmin && grunt.session.has_password !== false;

      const values = await grunt.form({
        title: __('Change password'),
        primaryLabel: __('Change'),
        fields: [
          ...(needCurrent
            ? [{ fieldname: "current_password", label: __('Current password'), fieldtype: "Password", required: true }]
            : []),
          { fieldname: "new_password", label: __('New password'), fieldtype: "Password", required: true, show_strength: true },
          { fieldname: "confirm_password", label: __('Confirm password'), fieldtype: "Password", required: true },
        ],
      });
      if (!values) return; // cancelled

      if (values.new_password !== values.confirm_password) {
        grunt.msgprint({ message: __('Passwords do not match'), indicator: "orange" });
        return;
      }

      try {
        await grunt.call({
          method: "grunt.auth.doctypes.User.user.set_user_password_api",
          args: { user_id, new_password: values.new_password, current_password: values.current_password },
        });
        grunt.msgprint({ message: __('Password changed'), indicator: "green" });
      } catch (error) {
        grunt.msgprint({ message: error?.message || __('Could not set the password'), indicator: "red" });
      }
    },
  });

  if (!frm.is_new) {
    frm.set_df_property("mfa_setup_button", "label", frm.doc.mfa_enabled ? __('Disable MFA') : __('Enable MFA'));
  }

  // Референтність — System Manager відкриває сесію під цим користувачем, щоб
  // перевірити доступність документів. Повернення — через банер угорі.
  frm.actions.add({
    id: "impersonate",
    label: __('Sign in as this user'),
    icon: "log-in",
    visible: (f) =>
      saved(f) &&
      (grunt.session.roles || []).includes("System Manager") &&
      f.doc.name !== grunt.session.user &&
      !(f.doc.roles || []).some((r) => r.role_name === "System Manager"),
    action: async () => {
        if (!(await grunt.confirm(
          __("Open a session as «{name}»? You can return to your own account at any time.").replace("{name}", frm.doc.full_name || frm.doc.name)
        ))) return;
        try {
          await grunt.impersonate(frm.doc.name);
        } catch (e) {
          grunt.msgprint({ message: e?.message || __('Could not sign in as the user'), indicator: "red" });
        }
    },
  });

  const pending = (f) => saved(f) && f.doc.signup_state === "pending";
  frm.actions.add({
    id: "approve_signup",
    label: __('Approve registration'),
    icon: "check",
    variant: "success",
    visible: pending,
    action: async () => {
      await grunt.call({
        method: "grunt.auth.doctypes.User.user.approve_user_api",
        args: { user_id: frm.doc.name },
      });
      grunt.msgprint({ message: __('Registration approved — the user can sign in'), indicator: "green" });
      await frm.reload();
    },
  });
  frm.actions.add({
    id: "reject_signup",
    label: __('Reject'),
    variant: "destructive",
    confirm: __('Reject the registration of this user?'),
    visible: pending,
    action: async () => {
      await grunt.call({
        method: "grunt.auth.doctypes.User.user.reject_user_api",
        args: { user_id: frm.doc.name },
      });
      grunt.msgprint({ message: __('Registration rejected'), indicator: "orange" });
      await frm.reload();
    },
  });
}

async function on_change(frm, fieldname) {
  if (["first_name", "last_name", "middle_name"].includes(fieldname)) {
    const last = frm.get_value("last_name") || "";
    const first = frm.get_value("first_name") || "";
    const middle = frm.get_value("middle_name") || "";
    const full = [last, first, middle].map(v => v.trim()).filter(Boolean).join(" ");
    frm.set_value("full_name", full);
  }

  if (fieldname === "passkeys_button") {
    await manage_passkeys();
    return;
  }

  async function manage_passkeys() {
    const PK = "grunt.auth.doctypes.WebAuthnCredential.web_authn_credential";
    const load = async () => (await grunt.call({ method: `${PK}.list_my_passkeys` })) || [];
    const fmtDate = (d) => (d
      ? new Date(d).toLocaleDateString("uk-UA", { day: "2-digit", month: "short", year: "numeric" })
      : "—");

    // One button — the browser's own picker offers "this device" / phone (QR) /
    // security key. No need to pre-choose the authenticator type.
    async function addKey({ values, setField }) {
      try {
        const r = await grunt.passkey.register((values.new_label || "").trim() || undefined);
        grunt.show_alert(__("Key «{name}» added").replace("{name}", r.label), "success");
      } catch (e) {
        if (e && e.name === "NotAllowedError") return; // user cancelled the browser prompt
        grunt.show_alert(e && e.message ? e.message : __('Could not add the key'), "error");
        return;
      }
      setField("keys", { rows: await load() });
      setField("new_label", { default: "" });
    }

    await grunt.form({
      title: __('Passkeys'),
      size: "large",
      fields: [
        {
          fieldname: "hint",
          fieldtype: "HTML",
          plain: true,
          default: __("Sign in without a password — with a fingerprint, Face ID or PIN. When adding, the browser offers to store the key on this device, on a phone (QR code) or on a hardware key."),
        },
        {
          fieldname: "keys",
          label: __('Your keys'),
          fieldtype: "Table",
          selectable: false,
          searchable: false,
          rowKey: "name",
          maxHeight: "260px",
          emptyText: __('No keys yet. Add one below.'),
          columns: [
            { key: "label", label: __('Name') },
            { key: "backed_up", label: __('Synced'), width: "90px", align: "center", format: (v) => (v ? __("yes") : "—") },
            { key: "last_used_at", label: __('Last used'), width: "130px", format: (v) => fmtDate(v) },
          ],
          rows: await load(),
          rowActions: [
            {
              label: __('Delete'),
              danger: true,
              onClick: async (row, { confirm, setRows }) => {
                if (!(await confirm(__("Delete key «{name}»? You will no longer be able to sign in with it.").replace("{name}", row.label)))) return;
                await grunt.call({ method: `${PK}.delete_passkey`, args: { name: row.name } });
                grunt.show_alert(__('Key deleted'), "success");
                setRows(await load());
              },
            },
          ],
        },
        { fieldname: "new_label", label: __('New key name'), fieldtype: "Text", placeholder: __('e.g. Work laptop') },
      ],
      buttons: [
        { label: __('＋ Add key'), variant: "default", action: addKey },
      ],
    });
  }

  if (fieldname === "mfa_setup_button") {
    if (frm.doc.mfa_enabled) {
      if (!confirm(__('Are you sure you want to disable two-factor authentication?'))) return;
      await grunt.call({ method: "grunt.auth.doctypes.User.user.disable_mfa" });
      await frm.reload();
      grunt.msgprint(__('MFA disabled'));
    } else {
      const info = await grunt.call({ method: "grunt.auth.doctypes.User.user.setup_mfa" });
      if (info.qr_svg) {
        const values = await grunt.form({
          title: __('MFA setup'),
          primaryLabel: __('Activate'),
          fields: [
            {
              fieldname: "qr_code",
              label: __('1. Scan the QR code in the app'),
              fieldtype: "HTML",
              default: info.qr_svg
            },
            {
              fieldname: "code",
              label: __('2. Enter the 6-digit confirmation code'),
              fieldtype: "Text",
              placeholder: "123456",
              required: true
            }
          ]
        });

        if (!values || !values.code) return;

        try {
          const res = await grunt.call({
            method: "grunt.auth.doctypes.User.user.confirm_mfa",
            args: { code: values.code }
          });
          await frm.reload();

          // Show backup codes
          frm.set_value("mfa_backup_display", res.backup_codes.join("\n"));
          frm.set_df_property("mfa_backup_display", "hidden", false);

          grunt.msgprint({
            title: __('MFA activated'),
            message: __('Save your backup codes! They are shown in the form.'),
            indicator: "green"
          });
        } catch (e) {
          grunt.msgprint({ message: __('Invalid code or error'), indicator: "red" });
        }
      }
    }
  }

}
