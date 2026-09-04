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

  if (!frm.is_new) {
    // Top bar override for change password
    frm.add_button("Змінити пароль", async () => {
      const user_id = frm.doc.name;
      if (!user_id) return;

      // Own password: prove knowledge of the current one — unless there is none
      // yet (signed up via email link / OIDC). Admins skip the check entirely.
      const isSelf = user_id === grunt.session.user;
      const isAdmin = grunt.session.is_superadmin || (grunt.session.roles || []).includes("System Manager");
      const needCurrent = isSelf && !isAdmin && grunt.session.has_password !== false;

      const values = await grunt.form({
        title: "Змінити пароль",
        primaryLabel: "Змінити",
        fields: [
          ...(needCurrent
            ? [{ fieldname: "current_password", label: "Поточний пароль", fieldtype: "Password", required: true }]
            : []),
          { fieldname: "new_password", label: "Новий пароль", fieldtype: "Password", required: true, show_strength: true },
          { fieldname: "confirm_password", label: "Підтвердіть пароль", fieldtype: "Password", required: true },
        ],
      });
      if (!values) return; // cancelled

      if (values.new_password !== values.confirm_password) {
        grunt.msgprint({ message: "Паролі не збігаються", indicator: "orange" });
        return;
      }

      try {
        await grunt.call({
          method: "grunt.auth.doctypes.User.user.set_user_password_api",
          args: { user_id, new_password: values.new_password, current_password: values.current_password },
        });
        grunt.msgprint({ message: "Пароль успішно змінено", indicator: "green" });
      } catch (error) {
        grunt.msgprint({ message: error?.message || "Помилка при встановленні пароля", indicator: "red" });
      }
    });

    frm.set_df_property("mfa_setup_button", "label", frm.doc.mfa_enabled ? "Вимкнути MFA" : "Увімкнути MFA");

    // Референтність — суперадмін відкриває сесію під цим користувачем, щоб
    // перевірити доступність документів. Повернення — через банер угорі.
    if (grunt.session.is_superadmin && frm.doc.name !== grunt.session.user && !frm.doc.is_superadmin) {
      frm.add_button("Увійти як цей користувач", async () => {
        if (!(await grunt.confirm(
          `Відкрити сесію під користувачем «${frm.doc.full_name || frm.doc.name}»? ` +
          `Ви зможете повернутися у свій обліковий запис у будь-який момент.`
        ))) return;
        try {
          await grunt.impersonate(frm.doc.name);
        } catch (e) {
          grunt.msgprint({ message: e?.message || "Не вдалося увійти під користувачем", indicator: "red" });
        }
      });
    }

    if (frm.doc.signup_state === "pending") {
      frm.add_button("✓ Підтвердити реєстрацію", async () => {
        await grunt.call({
          method: "grunt.auth.doctypes.User.user.approve_user_api",
          args: { user_id: frm.doc.name },
        });
        grunt.msgprint({ message: "Реєстрацію підтверджено — користувач може увійти", indicator: "green" });
        await frm.reload();
      });
      frm.add_button("Відхилити", async () => {
        if (!confirm("Відхилити реєстрацію цього користувача?")) return;
        await grunt.call({
          method: "grunt.auth.doctypes.User.user.reject_user_api",
          args: { user_id: frm.doc.name },
        });
        grunt.msgprint({ message: "Реєстрацію відхилено", indicator: "orange" });
        await frm.reload();
      });
    }
  }
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
        grunt.show_alert(`Ключ «${r.label}» додано`, "success");
      } catch (e) {
        if (e && e.name === "NotAllowedError") return; // user cancelled the browser prompt
        grunt.show_alert(e && e.message ? e.message : "Не вдалося додати ключ", "error");
        return;
      }
      setField("keys", { rows: await load() });
      setField("new_label", { default: "" });
    }

    await grunt.form({
      title: "Ключі доступу (Passkeys)",
      size: "large",
      fields: [
        {
          fieldname: "hint",
          fieldtype: "HTML",
          plain: true,
          default: "Дозволяють входити без пароля — за відбитком, Face ID або PIN. " +
            "Під час додавання браузер запропонує зберегти ключ на цьому пристрої, " +
            "на телефоні (QR-код) або на апаратному ключі.",
        },
        {
          fieldname: "keys",
          label: "Ваші ключі",
          fieldtype: "Table",
          selectable: false,
          searchable: false,
          rowKey: "name",
          maxHeight: "260px",
          emptyText: "Ще немає жодного ключа. Додайте нижче.",
          columns: [
            { key: "label", label: "Назва" },
            { key: "backed_up", label: "Синхр.", width: "90px", align: "center", format: (v) => (v ? "так" : "—") },
            { key: "last_used_at", label: "Востаннє", width: "130px", format: (v) => fmtDate(v) },
          ],
          rows: await load(),
          rowActions: [
            {
              label: "Видалити",
              danger: true,
              onClick: async (row, { confirm, setRows }) => {
                if (!(await confirm(`Видалити ключ «${row.label}»? Увійти за ним більше не вийде.`))) return;
                await grunt.call({ method: `${PK}.delete_passkey`, args: { name: row.name } });
                grunt.show_alert("Ключ видалено", "success");
                setRows(await load());
              },
            },
          ],
        },
        { fieldname: "new_label", label: "Назва нового ключа", fieldtype: "Text", placeholder: "напр. Робочий ноутбук" },
      ],
      buttons: [
        { label: "＋ Додати ключ", variant: "default", action: addKey },
      ],
    });
  }

  if (fieldname === "mfa_setup_button") {
    if (frm.doc.mfa_enabled) {
      if (!confirm("Ви впевнені, що хочете вимкнути двофакторну автентифікацію?")) return;
      await grunt.call({ method: "grunt.auth.doctypes.User.user.disable_mfa" });
      await frm.reload();
      grunt.msgprint("MFA вимкнено");
    } else {
      const info = await grunt.call({ method: "grunt.auth.doctypes.User.user.setup_mfa" });
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
            method: "grunt.auth.doctypes.User.user.confirm_mfa",
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
