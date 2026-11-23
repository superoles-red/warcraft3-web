#!/bin/sh
cd "$(dirname "$0")" || exit 1
device=$(networksetup -listallhardwareports | awk '/Hardware Port: (Wi-Fi|AirPort)/ {getline; print $2; exit}')
address=$(ipconfig getifaddr "${device:-en0}")
if [ -z "$address" ]; then
  echo 'Подключите Mac к той же Wi-Fi-сети, что и телефон.'
  exit 1
fi
if [ ! -f local/distribution/manifest.json ]; then
  echo 'Для запуска на телефоне сначала соберите компактную версию по инструкции в README.md.'
  exit 1
fi
echo "Откройте игру на телефоне: http://$address:8884/"
echo "ZIP для автономной установки: http://$address:8884/download/Warcraft-III-1.31.1-ruRU-compact.zip"
exec python3 server.py --host "$address" --port 8884 --pack-only "$@"
