# Home server operations

- The home server runs on the family's Windows computer (`Start Homeschooling.cmd`). It stays running between lessons; ending a lesson closes only that lesson's reader session. Do not stop the server from the tutor.
- The MCP bridge (`tutor_mcp/bridge.py`) talks to the server over the home network with a tutor credential created on the host by `python launcher/homeschooling.py pair-agent`. It never writes to Google Sheets directly and never sees Google credentials.
- Sync states on every save: `saved` = verified in the Google Sheets database; `pending` = durable on the home server and queued for Google (for example while the internet is down); `needs_reconciliation` = Google Sheets disagreed (usually a direct edit); a parent resolves it in Settings → Sync. Never report `pending` work as saved to Google.
- If Google authorization expires, saves stay pending and a parent reconnects Google on the host computer (Settings → Google). Nothing is lost.
- While a parent has maintenance mode on (editing the spreadsheet by hand), saves are refused with "changes are paused". Wait and retry with the same `operation_id`.
- Reader links: `/lesson?learner=…&topic=…&session=…`. They show the original PDF pages (layout, maps and illustrations) with the assigned start/stop boundaries, handwriting tools and a read-along panel.
- Narration: default voice Google Neural2-J at 0.9 until a preference is confirmed; one narrator only, after the passage is reviewed; timings come from Google's timepoints or validated cached manifests, never estimates. The shared monthly guard (150,000 characters, `%LOCALAPPDATA%\HomeTutor\google\<project>\usage.json`) covers every subject. Uncertain requests stay counted and are not retried automatically. Preserved ElevenLabs Robin Hood audio is never regenerated.
- If the reader or audio fails, use the physical book or a short passage in chat and tell the parent what failed.
