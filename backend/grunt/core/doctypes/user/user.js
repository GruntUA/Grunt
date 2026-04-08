// User DocType — Client Script

function on_load(frm) {
  // Sensitive fields: always hidden / read-only
  frm.set_df_property("hashed_password", "hidden", true);
  frm.set_df_property("mfa_secret", "hidden", true);
  frm.set_df_property("mfa_backup_codes", "hidden", true);
  frm.set_df_property("login_attempts", "read_only", true);
  frm.set_df_property("locked_until", "read_only", true);

  if (!frm.is_new) {
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

    if (frm.doc.mfa_enabled) {
      grunt.show_alert("MFA увімкнено для цього користувача", "success");
    }
  }
}
