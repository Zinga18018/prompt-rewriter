# Security policy

## Reporting a vulnerability

Please use GitHub's **Security** tab to submit a private vulnerability report. Include the affected
version or commit, Windows version, reproduction steps, expected behavior, actual behavior, and any
safe proof of impact.

If private vulnerability reporting is unavailable, open a public issue that asks the maintainer for
a private contact channel. Do not post API keys, selected text, clipboard contents, exploit details,
or other sensitive information in a public issue.

Please allow the maintainer time to reproduce and address a report before sharing it publicly. This
project does not currently promise a fixed response or remediation deadline.

## Security and privacy boundaries

Prompt Rewriter is a small desktop-automation MVP, not a security boundary. Its safeguards reduce
common mistakes, but they cannot eliminate operating-system, clipboard, focus, or third-party
provider risks.

- The keyboard hook is global while the program is running. Stop the process when the hotkey is not
  needed.
- Pressing the hotkey intentionally copies the current selection through the Windows global
  clipboard. Other software with clipboard access, including clipboard history and clipboard
  managers, may observe that text.
- With Gemini or Groq enabled, selected text is sent to that provider over the network. Use
  Ollama-only mode for text that must stay on the machine, while recognizing that local software
  and the operating system can still access the clipboard.
- Clipboard recovery is plain-text, best effort. Rich formats are not preserved, and another
  program can race with the transaction. The code checks Windows clipboard sequence numbers and
  avoids overwriting a newer detectable clipboard value.
- Focus and input-activity checks reduce accidental pastes into another control. They are not a
  guarantee against every accessibility tool, remote-desktop behavior, privileged process, or
  malicious program.
- The application does not intentionally persist selected or generated prompt text. The operating
  system, inference provider, terminal capture, or diagnostic tooling may have separate retention
  behavior.

Do not select passwords, API keys, protected health information, client secrets, or other sensitive
data unless the entire configured path is appropriate for that data.

## API keys

Keep `.env` out of source control. If a key is exposed, revoke it with the provider immediately,
replace it locally, and remove it from published Git history before continuing to use the repository.
Provider keys are sent in request headers and must never be placed in URLs or logged.
Gemini interactions set `store: false`; this does not override any separate provider-side logging,
abuse-monitoring, billing, or account policies.
