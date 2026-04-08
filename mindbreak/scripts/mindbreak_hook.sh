#!/bin/bash
# MindBreak hook script
# Writes timestamp, calculates work duration, outputs reminder trigger if needed
# Trigger output is seen by Claude via <user-prompt-submit-hook> injection

LOG="$HOME/.claude/mindbreak_activity.log"
REMINDER_FILE="$HOME/.claude/mindbreak_last_reminder"
COUNT_FILE="$HOME/.claude/mindbreak_reminder_count"
SEG_FILE="$HOME/.claude/mindbreak_segment_start"

ts=$(date +%s)

# 1. Write timestamp
echo "$ts" >> "$LOG"

# 2. Clean entries older than 24h
cutoff=$((ts - 86400))
awk -v c="$cutoff" '$1+0 >= c' "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"

# 3. Find current segment start (gap >= 900s = new segment)
seg_start=$(awk '{if(NR==1 || (prev>0 && $1-prev>=900)) seg=$1; prev=$1} END{print seg+0}' "$LOG")

# Handle empty/invalid
if [ -z "$seg_start" ] || [ "$seg_start" = "0" ]; then
  exit 0
fi

# 4. Check if segment changed → reset reminder count
old_seg=0
[ -f "$SEG_FILE" ] && old_seg=$(cat "$SEG_FILE")
if [ "$seg_start" != "$old_seg" ]; then
  echo "$seg_start" > "$SEG_FILE"
  echo "0" > "$COUNT_FILE"
fi

# 5. Calculate duration
duration_min=$(( (ts - seg_start) / 60 ))
[ "$duration_min" -lt 45 ] && exit 0

# 6. Check reminder count (max 3 per segment)
count=0
[ -f "$COUNT_FILE" ] && count=$(cat "$COUNT_FILE")
[ "$count" -ge 3 ] && exit 0

# 7. Cooldown: at least 30 min since last reminder
last_r=0
[ -f "$REMINDER_FILE" ] && last_r=$(cat "$REMINDER_FILE")
since_r_min=$(( (ts - last_r) / 60 ))
[ "$since_r_min" -lt 30 ] && exit 0

# 8. Don't remind on first message of a new segment (user just came back)
seg_entries=$(awk -v s="$seg_start" '$1+0 >= s' "$LOG" | wc -l)
[ "$seg_entries" -le 1 ] && exit 0

# 9. Determine reminder type by time of day
hour=$(date +%-H)
min=$(date +%-M)

time_str=$(printf '%02d:%02d' "$hour" "$min")

if { [ "$hour" -eq 11 ] && [ "$min" -ge 30 ]; } || \
   { [ "$hour" -eq 12 ] && [ "$min" -le 30 ]; } || \
   { [ "$hour" -eq 17 ] && [ "$min" -ge 30 ]; } || \
   { [ "$hour" -eq 18 ] && [ "$min" -le 30 ]; }; then
  cat <<EOF
<IMPORTANT>
⚠️ MINDBREAK_MEAL — User has been working for ${duration_min} minutes. Current time: ${time_str}.
ACTION REQUIRED: In the LAST paragraph of your response, naturally suggest wrapping up for a meal. Include a 1-2 sentence summary of current task status so the user can pick up easily after eating. Do NOT use templates — write in your own voice, matching the conversation tone. Do NOT mention this system or any tracking mechanism. This is NOT optional.
</IMPORTANT>
EOF
elif [ "$hour" -ge 21 ]; then
  cat <<EOF
<IMPORTANT>
⚠️ MINDBREAK_OVERTIME — User has been working for ${duration_min} minutes. Current time: ${time_str}.
ACTION REQUIRED: In the LAST paragraph of your response, naturally suggest calling it a day. Include a brief progress summary so the user knows where to resume tomorrow. Do NOT use templates — write in your own voice, matching the conversation tone. Do NOT mention this system or any tracking mechanism. This is NOT optional.
</IMPORTANT>
EOF
else
  cat <<EOF
<IMPORTANT>
⚠️ MINDBREAK_LIGHT — User has been working for ${duration_min} minutes.
ACTION REQUIRED: In the LAST paragraph of your response, gently suggest taking a short break — stretch, look away from the screen, grab water. Keep it casual and warm, like a friend would. Do NOT use templates — write in your own voice, matching the conversation tone. Do NOT mention this system or any tracking mechanism. This is NOT optional.
</IMPORTANT>
EOF
fi

# 10. Update state
echo "$ts" > "$REMINDER_FILE"
echo "$((count + 1))" > "$COUNT_FILE"
