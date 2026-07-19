#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob

# Usage:
#   PORT=/dev/ttyACM0 ./scripts/update_firmware.sh main_board [config.py]
#   ./scripts/update_firmware.sh lights_board
#   ./scripts/update_firmware.sh automatic_power_control
#   ./scripts/update_firmware.sh display

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-/dev/ttyACM0}"
BOARD="${1:-}"

# Configuração usada por defeito. Pode ser substituída pelo segundo argumento.
DEFAULT_CONFIG="config_escooter_dual_motor_iscooter_i12.py"

CFG="${2:-$DEFAULT_CONFIG}"
[[ "$CFG" == config_*.py ]] || CFG="config_${CFG}.py"

case "$BOARD" in
  main_board)
    FILES=(01_diy_main_board/boot.py 01_diy_main_board/main.py
      01_diy_main_board/bms_jbd.py 01_diy_main_board/mode.py
      01_diy_main_board/motor.py 01_diy_main_board/vars.py
      01_diy_main_board/throttle.py 01_diy_main_board/brake.py)
    for f in 01_diy_main_board/escooter/*.py; do FILES+=("$f"); done
    MANIFEST="/.main_board_update_manifest"
    ;;
  lights_board)
    FILES=(03_diy_lights_board/main.py)
    MANIFEST="/.lights_board_update_manifest"
    ;;
  automatic_power_control)
    FILES=(04_diy_automatic_power_control/main.py
      04_diy_automatic_power_control/adxl345.py)
    MANIFEST="/.automatic_power_control_update_manifest"
    ;;
  display)
    FILES=(02_diy_display/main.py 02_diy_display/screen_manager.py
      02_diy_display/wifi_time_sync.py
      02_diy_display/rtc_datetime.py)
    for f in 02_diy_display/escooter/*.py 02_diy_display/lcd/*.py \
      02_diy_display/screens/*.py 02_diy_display/widgets/*.py \
      02_diy_display/fonts/*.py; do FILES+=("$f"); done
    MANIFEST="/.display_update_manifest"
    ;;
  *)
    echo "Uso: $0 {main_board|lights_board|automatic_power_control|display} [config_file.py]" >&2
    exit 2
    ;;
esac

command -v mpremote >/dev/null || { echo "Erro: instale mpremote." >&2; exit 1; }
[[ -f "$ROOT/$CFG" ]] || { echo "Configuração não encontrada: $CFG" >&2; exit 1; }
FILES+=("$CFG")
for f in common/*.py; do FILES+=("$f"); done

MP=(mpremote)
[[ -n "$PORT" ]] && MP+=(connect "$PORT")
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
declare -A OLD
while IFS=$'\t' read -r hash path; do
  [[ "$hash" =~ ^[0-9a-f]{64}$ && -n "$path" ]] && OLD["$path"]="$hash"
done < <("${MP[@]}" fs cat ":$MANIFEST" 2>/dev/null || true)

changed=0
for source in "${FILES[@]}"; do
  destination="${source#01_diy_main_board/}"
  destination="${destination#03_diy_lights_board/}"
  destination="${destination#04_diy_automatic_power_control/}"
  destination="${destination#02_diy_display/}"
  hash="$(sha256sum "$ROOT/$source" | awk '{print $1}')"
  printf '%s\t/%s\n' "$hash" "$destination" >> "$TMP"
  if [[ "${OLD["/$destination"]:-}" != "$hash" ]]; then
    remote_dir="$(dirname "/$destination")"
    if [[ "$remote_dir" != "/" ]]; then
      "${MP[@]}" fs mkdir ":$remote_dir" 2>/dev/null || true
    fi
    "${MP[@]}" fs cp "$ROOT/$source" ":/$destination"
    changed=$((changed + 1))
  fi
done

if [[ "$changed" -eq 0 ]]; then
  echo "$BOARD já está atualizado; nenhum ficheiro foi enviado."
  exit 0
fi

"${MP[@]}" fs cp "$TMP" ":$MANIFEST"
echo "$changed ficheiro(s) atualizado(s) no $BOARD; a reiniciar..."
"${MP[@]}" reset
