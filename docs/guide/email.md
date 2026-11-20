# Email on documents

A mailbox (`EmailAccount`) can turn incoming letters into documents, and any
document can send letters and keep the correspondence on its timeline. Nothing
here needs code.

## Incoming letters → documents

1. On the DocType (*Behaviour → Incoming mail*) turn on **Create from incoming
   mail** and pick the **Sender field** (gets the sender's address) and the
   **Subject field** (gets the subject).
2. On the mailbox (*Processing* tab) set **Create documents** to that DocType.
   Only DocTypes with *Create from incoming mail* on are accepted.

Every 10 minutes `grunt.email.tasks.pull_from_accounts` reads new letters and
files each one (`grunt.email.routing.file_inbound`):

| The letter | What happens |
|------------|--------------|
| A reply: its `In-Reply-To` / `References` name a letter already on a document | Goes to that document, whatever the mailbox's settings |
| A new letter, the mailbox has *Create documents* | A new document; the letter is on its timeline |
| A new letter, no *Create documents* | Stays in the mailbox (`EmailMessage`) only |

The letter's files become the document's attachments. A document that cannot
be created (say a required field the letter does not fill) leaves the letter in
the mailbox and logs `email.append_to_failed`.

After filing, the `inbound_email` event fires with `account`, `email_data` and
`filed` (`{"message", "ref_doctype", "ref_name", "created"}`) for apps that want
more.

### Reading the mailbox

Letters are read by IMAP UID with `BODY.PEEK[]`: the *read* flags people see in
their mail client stay untouched. **IMAP folders** (default `INBOX`) is a
comma-separated list. The mailbox remembers the last UID per folder
(`imap_state`); a new mailbox, or a folder the server renumbered
(`UIDVALIDITY` changed), starts with its unread letters. At most 200 letters
per folder are read per run. A letter read twice is filed once (by
Message-ID).

### Auto-reply

**Auto-reply** answers each letter that created a document, with the
**Auto-reply text** (placeholders `{name}`, `{subject}`, `{sender}`) and the
signature. It is not sent to robots and lists (`Auto-Submitted`,
`Precedence: bulk/list`, `List-Id`, no-reply and mailer-daemon addresses) or to
the mailbox itself, so two auto-replies cannot ping-pong.

### Unanswered letters

**Notify if not answered** + **Minutes without a reply**: when the last letter
on a document has had no reply sent from the document for that long, the
document's assignees are notified (bell, push and email), or the **Notify
group** members when nobody is assigned. An auto-reply is not an answer. Each
letter is checked once; `grunt.email.tasks.check_unreplied` runs every 5
minutes and looks back one day beyond the set minutes.

## Letters from a document

The timeline has **Email** (a new letter) and **Reply** on each letter. The
dialog fills in the mailbox the correspondence came through, the addressee (the
sender field, or the answered letter's sender), `Re:` subject and the mailbox's
signature; it can apply an `EmailTemplate` (`{field}` placeholders take the
document's values), attach the document as PDF (needs *print*) and the
document's own files (10 MB in all).

Sending needs **write** access to the document. The letter is on the timeline
at once as *Queued*, then *Sent* or *Not sent* when the queue has tried it. It
threads to the answered letter (or the document's latest one), so the reply
comes back to the same document. Everyone who can read the document sees its
letters.

RPC: `grunt.api.v1.email.compose_context`, `render_email_template`,
`send_email`.

## Mailbox extras

| Field | Meaning |
|-------|---------|
| Signature | Added to letters written from documents and to auto-replies |
| Reply-To | Where replies should go, when not to this mailbox (every letter from it) |
| Always BCC | Every letter from the mailbox also goes, hidden, to this address |

`EmailService.queue_email` takes `cc`, `bcc`, `reply_to`, `message_id`,
`in_reply_to`, `message_references`, `ref_doctype` / `ref_name` and
`footer=False` for code that sends threaded or document-bound mail itself.
Bcc never appears in the headers.
