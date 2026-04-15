// User DocType — Client Script

function on_load(frm) {
  // Sensitive fields: always hidden / read-only
  frm.set_df_property("hashed_password", "hidden", true);
  frm.set_df_property("mfa_secret", "hidden", true);
  frm.set_df_property("mfa_backup_codes", "hidden", true);
  frm.set_df_property("login_attempts", "read_only", true);
  frm.set_df_property("locked_until", "read_only", true);

  frm.set_df_property("mfa_backup_display", "hidden", !frm.doc.mfa_enabled);

  if (!frm.is_new) {
    // Top bar override for change password
    frm.add_button("Змінити пароль", async () => {
      const email = frm.get_value("email");
      const password = window.prompt("Новий пароль:");
      if (!password) return;
      await grunt.call({
        method: "grunt.api.v1.auth.set_user_password",
        args: { email, password },
      });
      grunt.msgprint("Пароль успішно змінено");
    });

    frm.set_df_property("mfa_setup_button", "label", frm.doc.mfa_enabled ? "Вимкнути MFA" : "Увімкнути MFA");
  }
}

async function on_change(frm, fieldname) {
  if (fieldname === "mfa_setup_button") {
    if (frm.doc.mfa_enabled) {
      if (!confirm("Ви впевнені, що хочете вимкнути двофакторну автентифікацію?")) return;
      await grunt.call({ method: "grunt.api.v1.user.disable_mfa" });
      await frm.reload();
      grunt.msgprint("MFA вимкнено");
    } else {
      const info = await grunt.call({ method: "grunt.api.v1.user.setup_mfa" });
      if (info.qr_svg) {
        const values = await grunt.form({
          title: "Налаштування MFA",
          primaryLabel: "Активувати",
          fields: [
            {
              fieldname: "qr_code",
              label: "1. Відскануйте QR-код у додатку",
              fieldtype: "HTML",
              default: info.qr_svg
            },
            {
              fieldname: "code",
              label: "2. Введіть 6-значний код підтвердження",
              fieldtype: "Text",
              placeholder: "123456",
              required: true
            }
          ]
        });

        if (!values || !values.code) return;

        try {
          const res = await grunt.call({
            method: "grunt.api.v1.user.confirm_mfa",
            args: { code: values.code }
          });
          await frm.reload();

          // Show backup codes
          frm.set_value("mfa_backup_display", res.backup_codes.join("\n"));
          frm.set_df_property("mfa_backup_display", "hidden", false);

          grunt.msgprint({
            title: "MFA активовано",
            message: "Збережіть ваші резервні коди! Вони відображені у формі.",
            indicator: "green"
          });
        } catch (e) {
          grunt.msgprint({ message: "Невірний код або помилка", indicator: "red" });
        }
      }
    }
  }

}
