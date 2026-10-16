#!/bin/bash
# Disaster recovery setup for the Kronos trading system on a fresh Ubuntu box
# (WSL2 or native Linux server). Idempotent: safe to rerun after a partial failure.
#
# Usage (as your normal user, not root; sudo is used where needed):
#   bash scripts/setup.sh
# On a box with no checkout yet, copy this file over (or fetch it from GitHub)
# and run it from anywhere; it clones the repo to ~/kronos-trading-system.
#
# The repo must live at ~/kronos-trading-system: every script loads
# ~/kronos-trading-system/.env, and run_pipeline.sh hardcodes
# /home/pburstyn/kronos-trading-system.

set -uo pipefail

REPO_URL="${KRONOS_REPO_URL:-https://github.com/pburstyn/kronos-trading-system.git}"
REPO="$HOME/kronos-trading-system"
PY=python3.14
PANDAS_TA="pandas-ta==0.4.71b0"
ENV_KEYS=(ALPACA_API_KEY ALPACA_SECRET_KEY TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
          OPENROUTER_API_KEY ANTHROPIC_API_KEY FRED_API_KEY)
EXPECTED_TZ="America/Los_Angeles"   # cron times below are Pacific

# Cron line that runs a Python script from the repo with the venv: cron_py SCHEDULE SCRIPT LOG
cron_py() { echo "$1 cd $REPO && $REPO/venv/bin/python3 scripts/$2 >> $REPO/logs/$3 2>&1"; }

# Schedules are Pacific time (see EXPECTED_TZ) and match CLAUDE.md.
CRON_PIPELINE="0 18 * * 1-5 /bin/bash $REPO/scripts/run_pipeline.sh >> $REPO/logs/pipeline_cron.log 2>&1"
CRON_MORNING=$(cron_py "0 7 * * 1-5" morning_check.py morning_cron.log)
CRON_INTRADAY=$(cron_py "*/15 6-13 * * 1-5" intraday_logger.py intraday_price.log)  # script checks ET market hours itself
CRON_OUTCOME=$(cron_py "5 13 * * 1-5" outcome_tracker.py outcome_tracker.log)       # 4:05pm ET, right after close
CRON_TECH_WATCH=$(cron_py "5 7 * * 1" tech_watch.py tech_watch.log)
CRON_WEEKLY_HEALTH=$(cron_py "10 7 * * 1" weekly_health.py weekly_health.log)
CRON_ANDY_HEALTH=$(cron_py "*/30 * * * *" andy_health.py andy_health_cron.log)     # WSL2 only: calls powershell.exe
CRON_BACKUP="30 23 * * * /bin/bash $REPO/scripts/backup_logs.sh >> $REPO/logs/backup.log 2>&1"
BACKUP_REMOTE="gdrive"   # rclone remote name backup_logs.sh expects; see docs/backup_setup.md

DONE=(); SKIPPED=(); MANUAL=(); FAILED=()
done_()   { DONE+=("$1");    echo "  [done] $1"; }
skip()    { SKIPPED+=("$1"); echo "  [skip] $1"; }
manual()  { MANUAL+=("$1");  echo "  [todo] $1"; }
fail()    { FAILED+=("$1");  echo "  [FAIL] $1" >&2; }
section() { echo; echo "== $1"; }

# Prompts read from /dev/tty so they still work when the script is piped in.
have_tty() { [ -r /dev/tty ] && [ -w /dev/tty ] && { : </dev/tty; } 2>/dev/null; }
ask_yn() {  # ask_yn "question" -> 0 for yes
    have_tty || return 1
    local ans
    read -r -p "$1 [y/N] " ans </dev/tty || return 1
    [[ "$ans" =~ ^[Yy] ]]
}

is_wsl() {
    [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null
}

APT_UPDATED=0
apt_install() {
    if [ "$APT_UPDATED" -eq 0 ]; then
        sudo apt-get update -qq || return 1
        APT_UPDATED=1
    fi
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@"
}

# ---------------------------------------------------------------- steps

step_packages() {
    section "System packages"
    local need=()
    command -v git >/dev/null || need+=(git)
    command -v "$PY" >/dev/null || need+=("$PY")
    dpkg -s "$PY-venv" >/dev/null 2>&1 || need+=("$PY-venv")
    command -v crontab >/dev/null || need+=(cron)
    command -v rclone >/dev/null || need+=(rclone)
    command -v curl >/dev/null || need+=(curl)
    if [ ${#need[@]} -eq 0 ]; then
        skip "git, $PY, $PY-venv, cron, rclone, curl already installed"
    elif apt_install "${need[@]}"; then
        done_ "Installed: ${need[*]}"
    elif command -v git >/dev/null && command -v "$PY" >/dev/null && command -v crontab >/dev/null; then
        # Only the venv package failed; step_venv has a fallback for that.
        skip "Couldn't install $PY-venv; will try creating the venv with --without-pip"
    else
        fail "apt install ${need[*]} (if $PY isn't in this Ubuntu release's repos, add the deadsnakes PPA)"
        return 1
    fi
}

# The ledgers in logs/ are gitignored, so after a fresh clone the Drive backup
# is the only copy. Restore never overwrites a file that already exists locally.
step_backup() {
    section "Log backup (rclone -> Google Drive)"
    if ! command -v rclone >/dev/null; then
        manual "Install rclone, then follow docs/backup_setup.md"
        return 0
    fi
    if ! rclone listremotes 2>/dev/null | grep -qxF "$BACKUP_REMOTE:"; then
        manual "Connect Google Drive for nightly log backups: run 'rclone config' and name the remote '$BACKUP_REMOTE' (full steps in $REPO/docs/backup_setup.md), then rerun this script to restore logs if this is a rebuild"
        return 0
    fi
    skip "rclone remote '$BACKUP_REMOTE:' is configured"

    local remote="${KRONOS_BACKUP_REMOTE:-$BACKUP_REMOTE:kronos-backup}/latest"
    if [ -f "$REPO/logs/trade_ledger.csv" ]; then
        skip "logs/ already has data (trade_ledger.csv present); not restoring"
    elif ! rclone lsf "$remote" --max-depth 1 2>/dev/null | grep -q .; then
        skip "No backup found at $remote to restore from"
    elif ask_yn "  logs/ looks empty and a backup exists at $remote. Restore missing files from it?"; then
        if rclone copy --ignore-existing "$remote" "$REPO/logs"; then
            done_ "Restored logs/ from $remote (existing files left untouched)"
        else
            fail "Restoring logs/ from $remote"
        fi
    else
        manual "Restore logs if needed: rclone copy --ignore-existing $remote $REPO/logs"
    fi
}

# update_claude_md.sh commits and pushes after every pipeline run.
step_git_auth() {
    section "Git identity and GitHub auth"
    if [ -n "$(git -C "$REPO" config user.email)" ]; then
        skip "git user.email is set"
    else
        manual "Set a git identity so update_claude_md.sh can commit: git config --global user.name '...' && git config --global user.email '...'"
    fi
    local gh
    gh=$(command -v gh || { [ -x "$HOME/.local/bin/gh" ] && echo "$HOME/.local/bin/gh"; })
    if [ -n "$gh" ] && "$gh" auth status >/dev/null 2>&1; then
        skip "gh is logged in to GitHub"
    else
        manual "Log in to GitHub so update_claude_md.sh can push: install gh and run 'gh auth login'"
    fi
}

step_clone() {
    section "Repository"
    if [ -d "$REPO/.git" ]; then
        skip "Repo already present at $REPO (not pulled; run 'git pull' yourself if needed)"
    elif [ -e "$REPO" ]; then
        fail "$REPO exists but is not a git checkout; move it aside and rerun"
        return 1
    elif git clone "$REPO_URL" "$REPO"; then
        done_ "Cloned $REPO_URL to $REPO"
    else
        fail "git clone $REPO_URL (if the repo is private, run 'gh auth login' or set up an SSH key first)"
        return 1
    fi
    mkdir -p "$REPO/logs"
}

step_venv() {
    section "Python venv"
    local vpy="$REPO/venv/bin/python"
    if [ -x "$vpy" ]; then
        local ver
        ver=$("$vpy" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null)
        if [ "python$ver" = "$PY" ]; then
            skip "venv already exists ($PY)"
            return 0
        fi
        echo "  Existing venv is broken or not $PY (got '${ver:-none}'); recreating"
        rm -rf "$REPO/venv"
    fi
    if "$PY" -m venv "$REPO/venv"; then
        done_ "Created venv at $REPO/venv"
    elif rm -rf "$REPO/venv" && "$PY" -m pip --version >/dev/null 2>&1 \
         && "$PY" -m venv --without-pip "$REPO/venv" \
         && "$PY" -m pip --python "$REPO/venv/bin/python" install -q pip; then
        # No ensurepip (python3.14-venv missing): bootstrap pip with the system pip.
        done_ "Created venv at $REPO/venv (--without-pip, pip bootstrapped from system pip)"
    else
        rm -rf "$REPO/venv"   # don't leave a half-built venv for the next run to trust
        fail "$PY -m venv"
        return 1
    fi
}

step_deps() {
    section "Python dependencies"
    local vpy="$REPO/venv/bin/python"
    "$vpy" -m pip install -q --upgrade pip || { fail "pip upgrade"; return 1; }
    "$vpy" -m pip install -q -r "$REPO/requirements.txt" || { fail "pip install -r requirements.txt"; return 1; }
    # pandas-ta pins numba==0.61.2, which doesn't support Python 3.14, so install
    # it without deps; it runs on the numba pinned in requirements.txt.
    "$vpy" -m pip install -q --no-deps "$PANDAS_TA" || { fail "pip install --no-deps $PANDAS_TA"; return 1; }
    if "$vpy" -W ignore -c 'import pandas_ta, alpaca, anthropic, yfinance, dotenv' 2>/dev/null; then
        done_ "Installed requirements.txt + $PANDAS_TA (--no-deps); imports verified"
    else
        fail "Dependencies installed but imports failed; run: $vpy -c 'import pandas_ta'"
        return 1
    fi
}

env_value() {  # prints the value of $1 in .env, quotes stripped; empty if unset
    local line
    line=$(grep -E "^(export[[:space:]]+)?$1=" "$REPO/.env" 2>/dev/null | tail -n1) || true
    line=${line#*=}
    line=${line%$'\r'}
    line=${line#[\"\']}; line=${line%[\"\']}
    printf '%s' "$line"
}

env_set() {  # env_set KEY VALUE: replace an existing KEY= line, else append
    local f="$REPO/.env"
    if grep -qE "^(export[[:space:]]+)?$1=" "$f"; then
        local tmp
        tmp=$(mktemp)
        K="$1" V="$2" awk '
            BEGIN { k = ENVIRON["K"]; v = ENVIRON["V"] }
            $0 ~ "^(export[[:space:]]+)?" k "=" { print k "=" v; next }
            { print }' "$f" > "$tmp" && cat "$tmp" > "$f"   # cat keeps the 600 mode
        rm -f "$tmp"
    else
        [ -s "$f" ] && [ -n "$(tail -c1 "$f")" ] && echo >> "$f"
        printf '%s=%s\n' "$1" "$2" >> "$f"
    fi
}

step_env() {
    section ".env API keys"
    local f="$REPO/.env"
    if [ ! -e "$f" ]; then
        (umask 077; : > "$f")
        done_ "Created $f (mode 600)"
    fi
    chmod 600 "$f"

    local key val added=() missing=()
    for key in "${ENV_KEYS[@]}"; do
        if [ -n "$(env_value "$key")" ]; then
            continue
        fi
        val="${!key:-}"   # already exported in this shell?
        if [ -z "$val" ] && have_tty; then
            read -r -s -p "  $key (leave blank to skip): " val </dev/tty
            echo >/dev/tty
        fi
        if [ -n "$val" ]; then
            env_set "$key" "$val"
            added+=("$key")
        else
            missing+=("$key")
        fi
    done

    local already=$(( ${#ENV_KEYS[@]} - ${#added[@]} - ${#missing[@]} ))
    [ "$already" -gt 0 ] && skip "$already of ${#ENV_KEYS[@]} keys already set in .env"
    [ ${#added[@]} -gt 0 ] && done_ "Wrote to .env: ${added[*]}"
    [ ${#missing[@]} -gt 0 ] && manual "Add to $f: ${missing[*]}"
    return 0
}

# Curly quotes (UTF-8 bytes, so this works whatever the locale) usually come
# from pasting a cron line out of a chat or doc.
has_curly_quotes() {
    LC_ALL=C grep -qF -e $'\xe2\x80\x98' -e $'\xe2\x80\x99' -e $'\xe2\x80\x9c' -e $'\xe2\x80\x9d'
}

# Ensures one cron job. $1 = label, $2 = string identifying the job, $3 = canonical line.
# Exact match: leave it. Existing line with curly quotes (cron can't parse those):
# replace it. Any other existing variant: keep it, since it was set up deliberately.
ensure_cron() {
    local label=$1 pattern=$2 want=$3 current matches
    current=$(crontab -l 2>/dev/null) || current=""
    matches=$(printf '%s\n' "$current" | grep -F -- "$pattern" | grep -v '^[[:space:]]*#')

    if printf '%s\n' "$current" | grep -qxF -- "$want"; then
        skip "$label cron job already present"
        return 0
    fi
    if [ -n "$matches" ] && ! printf '%s' "$matches" | has_curly_quotes; then
        skip "$label cron job present with a custom line (kept as is): $matches"
        return 0
    fi

    local new action="Added"
    if [ -n "$matches" ]; then
        action="Replaced broken (curly-quoted)"
        new=$(printf '%s\n' "$current" | grep -vF -- "$pattern")
    else
        new=$current
    fi
    if { [ -n "$new" ] && printf '%s\n' "$new"; printf '%s\n' "$want"; } | crontab -; then
        done_ "$action $label cron job"
    else
        fail "Installing $label cron job"
        return 1
    fi
}

step_cron() {
    section "Cron jobs"
    mkdir -p "$REPO/logs"
    local cur
    cur=$(crontab -l 2>/dev/null) || cur=""
    if [ -n "$cur" ] && ! [ -f "$REPO/logs/crontab.bak" ]; then
        printf '%s\n' "$cur" > "$REPO/logs/crontab.bak"
        echo "  Backed up current crontab to $REPO/logs/crontab.bak"
    fi
    ensure_cron "Morning check (7am weekdays)" "scripts/morning_check.py" "$CRON_MORNING"
    ensure_cron "Pipeline (6pm weekdays)" "scripts/run_pipeline.sh" "$CRON_PIPELINE"
    ensure_cron "Intraday logger (every 15 min, market hours)" "scripts/intraday_logger.py" "$CRON_INTRADAY"
    ensure_cron "Outcome tracker (1:05pm weekdays)" "scripts/outcome_tracker.py" "$CRON_OUTCOME"
    ensure_cron "Tech watch (Mon 7:05am)" "scripts/tech_watch.py" "$CRON_TECH_WATCH"
    ensure_cron "Weekly health (Mon 7:10am)" "scripts/weekly_health.py" "$CRON_WEEKLY_HEALTH"
    if [ "$ENV_KIND" = "WSL2" ]; then
        ensure_cron "Andy health (every 30 min)" "scripts/andy_health.py" "$CRON_ANDY_HEALTH"
    else
        skip "Andy health cron not installed: it checks OpenClaw via Windows powershell.exe, which only exists under WSL2"
    fi
    ensure_cron "Log backup to Google Drive (11:30pm nightly)" "scripts/backup_logs.sh" "$CRON_BACKUP"

    # Cron times assume Pacific time.
    local tz
    tz=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null)
    if [ "$tz" = "$EXPECTED_TZ" ]; then
        skip "Timezone is already $EXPECTED_TZ"
    elif ask_yn "  System timezone is '${tz:-unknown}', but the cron times assume $EXPECTED_TZ. Change it?"; then
        if sudo timedatectl set-timezone "$EXPECTED_TZ" 2>/dev/null \
           || { sudo ln -sf "/usr/share/zoneinfo/$EXPECTED_TZ" /etc/localtime && echo "$EXPECTED_TZ" | sudo tee /etc/timezone >/dev/null; }; then
            done_ "Set timezone to $EXPECTED_TZ"
            sudo systemctl restart cron 2>/dev/null || sudo service cron restart 2>/dev/null
        else
            fail "Setting timezone to $EXPECTED_TZ"
        fi
    else
        manual "Timezone is '${tz:-unknown}', not $EXPECTED_TZ: set it (sudo timedatectl set-timezone $EXPECTED_TZ) or the 7am/6pm jobs fire at the wrong time"
    fi
}

step_cron_service() {
    section "Cron service"
    if [ -d /run/systemd/system ]; then
        if systemctl is-enabled --quiet cron && systemctl is-active --quiet cron; then
            skip "cron service already enabled and running"
        elif sudo systemctl enable --now cron; then
            done_ "Enabled and started cron service"
        else
            fail "systemctl enable --now cron"
        fi
    elif sudo service cron start >/dev/null 2>&1; then
        done_ "Started cron (systemd not running yet)"
    else
        fail "service cron start"
    fi
}

# Prints /etc/wsl.conf with [boot] systemd=true and a command that starts cron.
# An existing different boot command is kept and cron start is appended to it.
render_wsl_conf() {
    awk '
        function finish_boot() {
            if (!sd)  print "systemd=true"
            if (!cmd) print "command = service cron start"
        }
        /^[[:space:]]*\[/ {
            if (inboot) finish_boot()
            inboot = ($0 ~ /^[[:space:]]*\[boot\][[:space:]]*$/)
            if (inboot) seen = 1
            print; next
        }
        inboot && /^[[:space:]]*systemd[[:space:]]*=/ { print "systemd=true"; sd = 1; next }
        inboot && /^[[:space:]]*command[[:space:]]*=/ {
            cmd = 1
            if ($0 ~ /service cron start/) print
            else { sub(/[[:space:]]+$/, ""); print $0 "; service cron start" }
            next
        }
        { print }
        END {
            if (inboot) finish_boot()
            if (!seen) {
                if (NR > 0) print ""
                print "[boot]"; print "systemd=true"; print "command = service cron start"
            }
        }' "${1:-/dev/null}"
}

step_wsl_conf() {
    section "/etc/wsl.conf"
    local f=/etc/wsl.conf src=/dev/null new
    [ -f "$f" ] && src=$f
    new=$(render_wsl_conf "$src")
    if [ -f "$f" ] && [ "$new" = "$(cat "$f")" ]; then
        skip "/etc/wsl.conf already has systemd=true and command = service cron start"
        return 0
    fi
    [ -f "$f" ] && sudo cp -p "$f" "$f.bak.$(date +%Y%m%d%H%M%S)"
    if printf '%s\n' "$new" | sudo tee "$f" >/dev/null; then
        done_ "Updated /etc/wsl.conf ([boot] systemd=true, command = service cron start)"
        manual "Restart WSL so wsl.conf takes effect: run 'wsl --shutdown' in PowerShell, reopen Ubuntu, then check 'systemctl is-active cron'"
    else
        fail "Writing /etc/wsl.conf"
    fi
}

# ---------------------------------------------------------------- main

summary() {
    echo
    echo "================================================================"
    echo " Kronos setup summary ($ENV_KIND)"
    echo "================================================================"
    local i
    echo "Done:";          for i in "${DONE[@]}";    do echo "  + $i"; done; [ ${#DONE[@]} -eq 0 ] && echo "  (nothing)"
    echo "Already in place:"; for i in "${SKIPPED[@]}"; do echo "  = $i"; done; [ ${#SKIPPED[@]} -eq 0 ] && echo "  (nothing)"
    if [ ${#FAILED[@]} -gt 0 ]; then
        echo "FAILED (fix, then rerun this script):"; for i in "${FAILED[@]}"; do echo "  ! $i"; done
    fi
    echo "Manual steps remaining:"
    for i in "${MANUAL[@]}"; do echo "  - $i"; done
    [ ${#MANUAL[@]} -eq 0 ] && echo "  (none)"
}

main() {
    if [ "$(id -u)" -eq 0 ]; then
        echo "Run this as your normal user, not root (the crontab and ~/kronos-trading-system are per-user)." >&2
        exit 1
    fi
    if is_wsl; then ENV_KIND="WSL2"; else ENV_KIND="native Linux"; fi
    echo "Kronos disaster recovery setup: $ENV_KIND, user $USER, target $REPO"
    sudo -v || { echo "sudo is required" >&2; exit 1; }

    if [ "$REPO" != "/home/pburstyn/kronos-trading-system" ]; then
        manual "run_pipeline.sh hardcodes /home/pburstyn/kronos-trading-system but this repo is at $REPO; update the paths in scripts/run_pipeline.sh"
    fi

    # Later steps depend on earlier ones; a failure skips its dependents.
    local ok_pkgs=0 ok_repo=0 ok_venv=0
    step_packages && ok_pkgs=1
    [ $ok_pkgs -eq 1 ] && step_clone && ok_repo=1
    [ $ok_repo -eq 1 ] && step_venv && ok_venv=1
    [ $ok_venv -eq 1 ] && step_deps
    [ $ok_repo -eq 1 ] && step_env
    [ $ok_repo -eq 1 ] && step_git_auth
    [ $ok_repo -eq 1 ] && step_backup   # before cron, so restored logs are in place before any job runs
    [ $ok_repo -eq 1 ] && step_cron
    [ $ok_pkgs -eq 1 ] && step_cron_service
    if [ "$ENV_KIND" = "WSL2" ]; then
        step_wsl_conf
        manual "WSL2: the Andy health cron needs OpenClaw running on Windows (Kronos-Andy-Autostart task, see CLAUDE.md), or it will send DOWN alerts. Optional: run scripts/setup_cron_sudoers.sh so startup_check.py can restart cron without a password"
    else
        manual "Optional: run scripts/setup_cron_sudoers.sh if you want startup_check.py to restart cron without a password"
    fi
    [ $ok_repo -eq 1 ] && manual "Smoke test: cd $REPO && venv/bin/python scripts/morning_check.py"

    summary
    [ ${#FAILED[@]} -eq 0 ]
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
