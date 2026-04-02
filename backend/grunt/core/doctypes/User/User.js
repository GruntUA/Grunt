// User DocType — Client Script
// Handles form behaviour for the User document.

grunt.ui.form.on("User", {
  onload(frm) {
    // hashed_password is always hidden — sensitive field
    frm.set_df_property("hashed_password", "hidden", true);
    frm.set_df_property("mfa_secret", "hidden", true);
    frm.set_df_property("mfa_backup_codes", "hidden", true);
    frm.set_df_property("login_attempts", "read_only", true);
    frm.set_df_property("locked_until", "read_only", true);
  },

  refresh(frm) {
    if (!frm.is_new()) {
      // "Змінити пароль" button (superadmin or own profile)
      frm.add_custom_button(grunt.ui.t("Змінити пароль"), () => {
        grunt.ui.prompt({
          title: grunt.ui.t("Новий пароль"),
          fields: [
            {
              fieldname: "password",
              fieldtype: "Password",
              label: grunt.ui.t("Новий пароль"),
              reqd: true,
            },
          ],
          primary_action_label: grunt.ui.t("Зберегти"),
          primary_action({ password }) {
            grunt.call({
              method: "grunt.api.v1.auth.set_user_password",
              args: { email: frm.doc.email, password },
              callback() {
                grunt.ui.msgprint(grunt.ui.t("Пароль успішно змінено"));
              },
            });
          },
        });
      });

      // Show/hide MFA status
      if (frm.doc.mfa_enabled) {
        frm.set_intro(grunt.ui.t("MFA увімкнено для цього користувача"), "green");
      }
    }
  },
});
