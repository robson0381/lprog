#!/usr/bin/env bash
# Prepara uma sessão do Claude Code na nuvem para rodar a automação:
# instala dependências e faz o Chromium confiar nos certificados do proxy do ambiente.
set -euo pipefail
cd "$(dirname "$0")"
pip install -q -r requirements.txt
if [ -f /root/.ccr/ca-bundle.crt ]; then
  command -v certutil >/dev/null || apt-get install -y -q libnss3-tools >/dev/null
  mkdir -p "$HOME/.pki/nssdb"
  [ -f "$HOME/.pki/nssdb/cert9.db" ] || certutil -N -d "sql:$HOME/.pki/nssdb" --empty-password
  tmp=$(mktemp -d)
  awk -v d="$tmp" '/BEGIN CERT/{n++} {print > (d "/c" n ".pem")}' /root/.ccr/ca-bundle.crt
  for f in "$tmp"/c*.pem; do certutil -A -d "sql:$HOME/.pki/nssdb" -t "C,," -n "ccr-$(basename "$f")" -i "$f" 2>/dev/null || true; done
  rm -rf "$tmp"
fi
echo "Pronto. Defina SAP_USUARIO e SAP_SENHA nas variáveis do ambiente e rode:"
echo "  python preencher_interacao.py --headless --gravar"
