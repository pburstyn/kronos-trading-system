# Log Backups to Google Drive (rclone)

`scripts/backup_logs.sh` runs nightly at 11:30pm PT from cron and backs up `logs/` to Google Drive:

- `gdrive:kronos-backup/latest/`: mirror of `logs/`, updated nightly
- `gdrive:kronos-backup/snapshots/YYYY-MM-DD/`: full dated copy, deleted after 30 days

The ledgers in `logs/` (signal_log, decision_ledger, trade_ledger, regime_log and the rest) are gitignored, so this backup is the only copy off the machine. `.env` is **not** backed up. Re-enter the keys with `scripts/setup.sh` on a new machine.

If a backup fails, Telegram gets an alert and `logs/backup.log` has the details.

## One-time setup

`scripts/setup.sh` installs rclone and the cron job. The Google Drive login has to be done by hand, once per machine.

### 1. Create the remote

```bash
rclone config
```

Answer the prompts:

| Prompt | Answer |
|---|---|
| `n/s/q>` | `n` (new remote) |
| `name>` | `gdrive` (the script expects this name) |
| `Storage>` | `drive` (Google Drive) |
| `client_id>` / `client_secret>` | leave blank (see the note below) |
| `scope>` | `drive.file` (rclone can only see files it created, not the rest of your Drive) |
| `service_account_file>` | leave blank |
| `Edit advanced config?` | `n` |
| `Use web browser to automatically authenticate?` | see step 2 |
| `Configure this as a Shared Drive?` | `n` |
| `y/e/d>` | `y` to save |

Note: leaving `client_id` blank uses rclone's shared Google client, which is rate-limited across all rclone users. That's fine for a nightly run of a few MB. If you ever see `rateLimitExceeded` errors, create your own client ID ([rclone docs](https://rclone.org/drive/#making-your-own-client-id)) and run `rclone config` again.

### 2. Authenticate

**WSL2:** answer `y`. rclone prints a `http://127.0.0.1:53682/auth?...` link. Open it in your Windows browser (WSL2 forwards localhost) and approve access. If the browser can't reach it, answer `n` instead and use the headless steps below, running `rclone authorize` from Windows (`winget install Rclone.Rclone`).

**Native server with no browser (headless):** answer `n`. rclone prints a command like `rclone authorize "drive" "eyJ..."`. On any machine that has a browser, install rclone and run that exact command (copy it as printed, since the string encodes the `drive.file` scope). Approve in the browser, copy the token JSON it prints, and paste it into the server's `config_token>` prompt.

### 3. Test

```bash
rclone lsd gdrive:                                    # should list without errors
bash ~/kronos-trading-system/scripts/backup_logs.sh --dry-run
bash ~/kronos-trading-system/scripts/backup_logs.sh
rclone ls gdrive:kronos-backup/latest | head          # files should be there
rclone lsf gdrive:kronos-backup/snapshots             # today's date
```

The rclone config, including the Drive token, is stored in `~/.config/rclone/rclone.conf`. Treat it like `.env`.

## Restore

On a fresh machine, `scripts/setup.sh` offers to restore `logs/` from `latest` once the `gdrive` remote is configured. It only copies files that don't exist locally. To restore by hand:

```bash
# From the latest mirror
rclone copy gdrive:kronos-backup/latest ~/kronos-trading-system/logs

# From a specific day (for example, if a CSV got corrupted and the corruption was mirrored)
rclone lsf gdrive:kronos-backup/snapshots
rclone copy gdrive:kronos-backup/snapshots/2026-10-14 ~/kronos-trading-system/logs
```

`rclone copy` overwrites local files that differ. Add `--ignore-existing` to fill in only missing files, or `--dry-run` to preview.

## Changing the destination

Set `KRONOS_BACKUP_REMOTE` (default `gdrive:kronos-backup`) in the cron line, for example `KRONOS_BACKUP_REMOTE=b2:my-bucket/kronos bash .../backup_logs.sh`. Retention is `KEEP_DAYS` at the top of the script.
