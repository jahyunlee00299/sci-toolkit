#!/usr/bin/env bash
# statusline.sh - Claude Code statusLine command: model | context | 5h limit | 7d limit.
# Reads the statusLine JSON on stdin, prints exactly one line. Pure bash + `date`
# (no jq, no python: it runs on every render). Fail-open: always exits 0.
# Contract: see SKILL.md. Env: STATUSLINE_WARN_PCT (default 80),
# STATUSLINE_TZ_OFFSET_MIN (minutes east of UTC, overrides the system timezone).

json=""
IFS= read -r -d '' json || true
json=${json//$'\n'/}
json=${json//$'\r'/}

WARN=${STATUSLINE_WARN_PCT:-80}
[[ $WARN =~ ^[0-9]+$ ]] || WARN=80
OFFSET=${STATUSLINE_TZ_OFFSET_MIN:-}
[[ $OFFSET =~ ^[+-]?[0-9]+$ ]] || OFFSET=""

OBJ=""
NUM=""

# get_obj <key> <text>: first object value of "key" (at most one nested level) -> OBJ.
get_obj() {
  local re="\"$1\"[[:space:]]*:[[:space:]]*(\{([^{}]|\{[^{}]*\})*\})"
  OBJ=""
  [[ $2 =~ $re ]] && OBJ=${BASH_REMATCH[1]}
}

# get_num <key> <text>: first numeric value of "key" -> NUM (integer part), else empty.
get_num() {
  local re="\"$1\"[[:space:]]*:[[:space:]]*(-?[0-9]+)"
  NUM=""
  [[ $2 =~ $re ]] && NUM=${BASH_REMATCH[1]}
}

fmt_tokens() {
  local n=$1 t
  if ((n < 1000)); then
    printf '%s' "$n"
  elif ((n < 1000000)); then
    printf '%sk' "$((n / 1000))"
  elif ((n % 1000000 == 0)); then
    printf '%sM' "$((n / 1000000))"
  else
    t=$((n / 100000))
    printf '%s.%sM' "$((t / 10))" "$((t % 10))"
  fi
}

# fmt_time <epoch> <with_day 0|1>: local reset time -> TIME ("HH:MM" or "Ddd HH:MM").
fmt_time() {
  local e=$1 out dow hm
  TIME=""
  if [[ -n $OFFSET ]]; then
    out=$(date -u -d "@$((e + OFFSET * 60))" '+%u %H:%M' 2>/dev/null) ||
      out=$(date -u -r "$((e + OFFSET * 60))" '+%u %H:%M' 2>/dev/null) || return 0
  else
    out=$(date -d "@$e" '+%u %H:%M' 2>/dev/null) ||
      out=$(date -r "$e" '+%u %H:%M' 2>/dev/null) || return 0
  fi
  dow=${out%% *}
  hm=${out#* }
  local days=(x Mon Tue Wed Thu Fri Sat Sun)
  if [[ $2 == 1 ]]; then TIME="${days[dow]} $hm"; else TIME=$hm; fi
}

# limit_segment <label> <key> <with_day>: appends to SEGS when the window is present.
limit_segment() {
  local pct reset seg
  get_obj "$2" "$json"
  [[ -n $OBJ ]] || return 0
  get_num used_percentage "$OBJ"
  pct=$NUM
  get_num resets_at "$OBJ"
  reset=$NUM
  [[ -n $pct ]] || return 0
  seg="$1 ${pct}%"
  if [[ -n $reset ]]; then
    fmt_time "$reset" "$3"
    [[ -n $TIME ]] && seg+=" ~$TIME"
  fi
  ((pct >= WARN)) && seg="!$seg"
  SEGS+=("$seg")
}

SEGS=()
BS='\'
DQ='"'

# 1. model
get_obj model "$json"
if [[ -n $OBJ ]]; then
  re='"display_name"[[:space:]]*:[[:space:]]*"([^"\]*(\\.[^"\]*)*)"'
  if [[ $OBJ =~ $re && -n ${BASH_REMATCH[1]} ]]; then
    name=${BASH_REMATCH[1]}
    name=${name//"$BS$DQ"/$DQ}
    SEGS+=("${name//"$BS$BS"/$BS}")
  fi
fi

# 2. context
get_obj context_window "$json"
if [[ -n $OBJ ]]; then
  ctx=$OBJ
  get_obj current_usage "$ctx"
  usage=$OBJ
  flat=${ctx/"$usage"/}
  get_num context_window_size "$flat"
  size=$NUM
  get_num used_percentage "$flat"
  pct=$NUM
  used=0
  for k in input_tokens cache_creation_input_tokens cache_read_input_tokens; do
    get_num "$k" "$usage"
    used=$((used + ${NUM:-0}))
  done
  [[ -n $size && $size -gt 0 ]] || size=""
  [[ -n $pct || -z $size ]] || pct=$((used * 100 / size))
  if ((used > 0)) || [[ -n $pct ]] || [[ -n $size ]]; then
    seg="ctx $(fmt_tokens "$used")"
    [[ -n $size ]] && seg+="/$(fmt_tokens "$size")"
    [[ -n $pct ]] && seg+=" ${pct}%"
    [[ -n $pct ]] && ((pct >= WARN)) && seg="!$seg"
    SEGS+=("$seg")
  fi
fi

# 3-4. rate limits
limit_segment 5h five_hour 0
limit_segment 7d seven_day 1

if ((${#SEGS[@]} == 0)); then
  printf 'claude\n'
else
  out=${SEGS[0]}
  for ((i = 1; i < ${#SEGS[@]}; i++)); do out+=" | ${SEGS[i]}"; done
  printf '%s\n' "$out"
fi
exit 0
