#!/bin/bash
# Fix volume ownership (volumes may have been created as root)
chown -R botuser:botuser /data /home/botuser/.claude 2>/dev/null

# Copy fresh credentials into the claude volume (bind mount is at a separate path
# because the named volume shadows individual file mounts inside it)
cp /run/secrets/claude-credentials.json /home/botuser/.claude/.credentials.json 2>/dev/null
chown botuser:botuser /home/botuser/.claude/.credentials.json 2>/dev/null

exec gosu botuser "$@"
