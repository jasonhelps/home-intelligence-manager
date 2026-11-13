#!/bin/sh
set -eu

SOURCE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/custom_components/ai_automation_suggester"
CONFIG="${1:-}"

if [ -z "$CONFIG" ] || [ ! -d "$CONFIG/custom_components" ]; then
    echo "Usage: sh install.sh /path/to/homeassistant/config"
    exit 1
fi

TARGET="$CONFIG/custom_components/ai_automation_suggester"

if [ ! -f "$SOURCE/manifest.json" ]; then
    echo "ERROR: Release integration missing"
    exit 1
fi

if [ -e "$TARGET" ]; then
    BACKUP="$CONFIG/custom_components/ai_automation_suggester.backup-$(date +%Y%m%d-%H%M%S)"
    cp -Rp "$TARGET" "$BACKUP"
    echo "Backup: $BACKUP"
fi

TEMP="$CONFIG/custom_components/.him-install-$$"
trap 'rm -rf "$TEMP"' EXIT HUP INT TERM
cp -Rp "$SOURCE" "$TEMP"

OLD="$CONFIG/custom_components/.him-previous-$$"

if [ -e "$TARGET" ]; then
    mv "$TARGET" "$OLD"
fi

if ! mv "$TEMP" "$TARGET"; then
    if [ -e "$OLD" ]; then
        mv "$OLD" "$TARGET"
    fi
    echo "ERROR: Installation failed; previous version restored"
    exit 1
fi

if [ -e "$OLD" ]; then
    rm -rf "$OLD"
fi
trap - EXIT HUP INT TERM

echo "PASS - Home Intelligence Manager integration installed"
echo "Home Assistant restart required to load changes"
echo "No automations modified"
