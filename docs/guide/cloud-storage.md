# Cloud storage

A **Cloud Storage** (`StorageRemote`) is a connection to storage outside the
server: Google Drive, Dropbox, OneDrive, MEGA, any S3-compatible service,
WebDAV (Nextcloud, ownCloud), SFTP, an SMB share, a mounted disk, or any
other [rclone backend](https://rclone.org/overview/). It has two uses:

1. **Backups**: each new backup set is uploaded there as well, and the
   storage keeps its own number of copies.
2. **Old files**: file contents that are rarely read are moved off the
   server disk and fetched back when someone opens them.

Every transfer goes through [rclone](https://rclone.org), so it has to be
installed on the server (`rclone version`). If the binary is not on `PATH`,
set `RCLONE_BINARY` to its full path. **System Health** reports a missing
rclone.

## Setting up

Desk → **Cloud Storage** → new. Choose the **Storage type** and fill in the
fields shown for it:

| Type | What it needs |
|------|---------------|
| Google Drive, Dropbox, OneDrive | an account token (see below) |
| MEGA | account email and password |
| S3 | S3 provider, endpoint (empty for AWS), region, access key and secret |
| WebDAV | server URL, server kind, user, password (Nextcloud: an app password) |
| SFTP | host, port, user, password or private key |
| SMB | host, share in **Root folder** (`share/path`), user, password, domain |
| Server folder | an absolute **Root folder**, such as a mounted NAS (`/mnt/nas/grunt`) |
| Other | the rclone backend name plus its options in **rclone options** |

Everything is kept under **Root folder**, in `backups/<site>/` and
`files/<site>/`. Several sites can share one storage.

**Advanced → rclone options** takes extra `key = value` lines for any
storage type. They override the generated values.

Save, then click **Test connection**. It creates the root folder, writes a
small file, reads it back, deletes it, and shows the free space where the
provider reports it. The result is stored in **Status**.

### Google Drive, Dropbox, OneDrive

These need an OAuth token. There are two ways to get one:

- **Paste a token from rclone.** No app registration needed. On any computer
  with a browser, install rclone and run the command shown in the dialog (for
  example `rclone authorize "drive"`). Sign in, allow access, and paste the
  printed `{…}` line. Leave **Client ID** empty: the token belongs to rclone's
  own app.
- **Sign in through the browser.** Register your own app with the provider
  (Google Cloud console, Dropbox App Console, Microsoft Entra), enter its
  Client ID and secret, and set its redirect URI to
  `https://<your site>/api/v1/method/grunt.storage.cloud.oauth.callback`.

Google Drive is accessed with the `drive.file` scope, so the app sees only
the files it created and nothing else in the Drive. Tokens are refreshed
automatically, and every refreshed token is written back to the record.

### Encryption

**Encrypt before sending** wraps the storage in rclone `crypt`
(XSalsa20-Poly1305). The provider stores only ciphertext. File names stay
readable, so listing and rotation still work.

Keep the encryption password somewhere outside this system. Without it no
backup can be restored, and the password itself is stored in the database you
would be restoring. Changing it later makes everything already uploaded
unreadable, so it can't be changed while files are kept in the storage.

### Secrets

Passwords, keys and tokens are never sent to the browser. Every read returns
a mask, and saving the mask back keeps the stored value. To replace a secret,
type a new one.

## Backups

On the **Backups** tab, turn on **Upload backups here** and set **Copies to
keep here**. After every backup (scheduled, or **Create now**) the worker
uploads the set to each such storage, then deletes the older sets there. A
failing storage does not fail the backup. Instead the failure is recorded on
the storage (status, Error Log), and System Managers get a notification when
the storage goes from OK to Error.

- The **Backups** list has an **In cloud storage** column that shows which
  storages hold each set.
- **Upload the latest backup now** uploads the newest set to this storage.
- **Backups in this storage**, or **From cloud storage** in the Backups list,
  lists the sets kept there. The chosen set is downloaded to the server and
  appears in Backups. Then restore it with `grunt db restore <id>`.
- **System Health → Cloud storage** shows the age of the latest upload per
  storage: one missed interval is a warning, two are an error.

CLI:

```bash
grunt db cloud-backups <storage>            # sets kept in the storage
grunt db fetch-backup <storage> <id>        # download a set into backups/
grunt db upload-backup <storage> [<id>]     # upload a set (the newest by default)
```

### If the server is lost

The storage settings live in the database you are about to restore. Before
that happens, click **Show rclone config** and keep the text somewhere safe,
saved as `rclone.conf`. Passwords in it are only obscured, so keep the file
private. With it, plain rclone gets a set back:

```bash
rclone --config rclone.conf copy secret:backups/<site>/ ./restore/   # encrypted
rclone --config rclone.conf copy remote:<root>/backups/<site>/ ./restore/
```

Put the files into `sites/<site>/backups/` and run `grunt db restore <id>`.

## Old files

On the **Files** tab, turn on **Move old files here**. Only one storage can
hold files. The rules:

- **Older than, days**: upload age.
- **Larger than, KB**: minimum size.
- **Public files too**: off by default, because website images are read all
  the time.
- **Only files of**: DocType names, one per line. Empty means any file.

Every night at 04:00, a job moves the contents (blobs) that match. A blob is
moved only when every `File` record pointing at it matches the rules. The
`File` record stays and gets **In cloud storage**. Previews stay on the
server, so lists and galleries never wait for the cloud. **Move files now**
runs the job straight away.

Reading is transparent. When someone opens a moved file, the server
downloads it into `uploads/cache/`, checks its SHA-256, and serves it.
Afterwards it is served from the cache. **Local cache, MB** caps the cache,
and the least recently used copies are dropped at night.

- The nightly garbage collection also deletes blobs in the storage that no
  record needs any more (records in the trash still count).
- `grunt files verify` checks moved files against the storage listing.
- Backup sets don't include moved files, which are kept in the storage, nor
  the cache.
- **Return all files to the server** downloads everything back (after
  checking free space), points the records at the server disk again, and
  deletes the copies in the storage. Do this before changing where or how
  the storage keeps things (type, root folder, encryption) or deleting it.
  These changes are blocked while files are kept there.

## For developers

`grunt.storage.cloud.rclone.Rclone` works with single files, so apps can use a
configured storage for their own purposes:

```python
from grunt.storage.cloud import Rclone, load_remote

async with Rclone(await load_remote("Archive")) as rc:
    await rc.put_file(path, "reports/2026/q3.pdf")
    data = await rc.cat("reports/2026/q3.pdf")       # offset= / count= for a slice
    entries = await rc.list("reports", recursive=True)
    await rc.delete_file("reports/2026/q3.pdf")
```

Each call starts one rclone process. For many files, use
`copy_files` / `get_files` / `delete_files`, which take a list and run a
single process. Paths are relative to the root folder, and encryption is
applied automatically.
