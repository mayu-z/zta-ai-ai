#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Generate local CA + mTLS client/server certificates for ZTA-AI.

Usage:
  ./scripts/generate_mtls_artifacts.sh [options]

Options:
  --out-dir <path>           Output directory (default: ./certs/mtls/current)
  --ca-cn <name>             CA common name (default: zta-ai-local-ca)
  --client-cn <name>         Client cert common name (default: zta-ai-client)
  --server-cn <name>         Server cert common name (default: zta-ai-server)
  --server-san-dns <list>    Comma-separated DNS SANs (default: localhost,api,api.zta-ai.svc)
  --server-san-ip <list>     Comma-separated IP SANs (default: 127.0.0.1)
  --days <n>                 Certificate validity days (default: 365)
  --force                    Overwrite existing non-empty output directory
  -h, --help                 Show this help

Example:
  ./scripts/generate_mtls_artifacts.sh \
    --out-dir ./certs/mtls/current \
    --server-san-dns localhost,api,api.prod.internal \
    --server-san-ip 127.0.0.1,10.0.10.12
USAGE
}

trim() {
  local value="$1"
  # shellcheck disable=SC2001
  echo "$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
}

require_tool() {
  local tool_name="$1"
  if ! command -v "$tool_name" >/dev/null 2>&1; then
    echo "Error: required tool '$tool_name' is not installed or not in PATH." >&2
    exit 1
  fi
}

OUT_DIR="./certs/mtls/current"
CA_CN="zta-ai-local-ca"
CLIENT_CN="zta-ai-client"
SERVER_CN="zta-ai-server"
SERVER_SAN_DNS="localhost,api,api.zta-ai.svc"
SERVER_SAN_IP="127.0.0.1"
DAYS="365"
FORCE="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --ca-cn)
      CA_CN="$2"
      shift 2
      ;;
    --client-cn)
      CLIENT_CN="$2"
      shift 2
      ;;
    --server-cn)
      SERVER_CN="$2"
      shift 2
      ;;
    --server-san-dns)
      SERVER_SAN_DNS="$2"
      shift 2
      ;;
    --server-san-ip)
      SERVER_SAN_IP="$2"
      shift 2
      ;;
    --days)
      DAYS="$2"
      shift 2
      ;;
    --force)
      FORCE="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown option '$1'" >&2
      usage
      exit 1
      ;;
  esac
done

require_tool openssl

if ! [[ "$DAYS" =~ ^[0-9]+$ ]]; then
  echo "Error: --days must be a positive integer." >&2
  exit 1
fi

if [[ -d "$OUT_DIR" ]] && [[ -n "$(find "$OUT_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null || true)" ]] && [[ "$FORCE" != "true" ]]; then
  echo "Error: output directory '$OUT_DIR' is not empty. Use --force to overwrite." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"

# Clean any prior content when --force is enabled.
if [[ "$FORCE" == "true" ]]; then
  find "$OUT_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
fi

CA_KEY="$OUT_DIR/ca.key"
CA_CRT="$OUT_DIR/ca.crt"
CA_SRL="$OUT_DIR/ca.srl"
CLIENT_KEY="$OUT_DIR/client.key"
CLIENT_CSR="$OUT_DIR/client.csr"
CLIENT_CRT="$OUT_DIR/client.crt"
SERVER_KEY="$OUT_DIR/server.key"
SERVER_CSR="$OUT_DIR/server.csr"
SERVER_CRT="$OUT_DIR/server.crt"
CA_BUNDLE="$OUT_DIR/ca_bundle.crt"

client_ext_file="$OUT_DIR/client.ext"
server_ext_file="$OUT_DIR/server.ext"

openssl req -x509 -newkey rsa:4096 -sha256 \
  -nodes \
  -subj "/CN=${CA_CN}" \
  -days "$DAYS" \
  -keyout "$CA_KEY" \
  -out "$CA_CRT" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -addext "subjectKeyIdentifier=hash"

openssl req -new -newkey rsa:3072 -sha256 \
  -nodes \
  -subj "/CN=${CLIENT_CN}" \
  -keyout "$CLIENT_KEY" \
  -out "$CLIENT_CSR"

cat > "$client_ext_file" <<EOF
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=clientAuth
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF

openssl x509 -req \
  -in "$CLIENT_CSR" \
  -CA "$CA_CRT" \
  -CAkey "$CA_KEY" \
  -CAcreateserial \
  -CAserial "$CA_SRL" \
  -out "$CLIENT_CRT" \
  -days "$DAYS" \
  -sha256 \
  -extfile "$client_ext_file"

openssl req -new -newkey rsa:3072 -sha256 \
  -nodes \
  -subj "/CN=${SERVER_CN}" \
  -keyout "$SERVER_KEY" \
  -out "$SERVER_CSR"

san_entries=()
IFS=',' read -r -a dns_items <<< "$SERVER_SAN_DNS"
for item in "${dns_items[@]}"; do
  cleaned="$(trim "$item")"
  if [[ -n "$cleaned" ]]; then
    san_entries+=("DNS:${cleaned}")
  fi
done

IFS=',' read -r -a ip_items <<< "$SERVER_SAN_IP"
for item in "${ip_items[@]}"; do
  cleaned="$(trim "$item")"
  if [[ -n "$cleaned" ]]; then
    san_entries+=("IP:${cleaned}")
  fi
done

if [[ ${#san_entries[@]} -eq 0 ]]; then
  echo "Error: at least one SAN entry must be provided via --server-san-dns or --server-san-ip." >&2
  exit 1
fi

san_joined=""
for entry in "${san_entries[@]}"; do
  if [[ -z "$san_joined" ]]; then
    san_joined="$entry"
  else
    san_joined="$san_joined,$entry"
  fi
done

cat > "$server_ext_file" <<EOF
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
subjectAltName=${san_joined}
EOF

openssl x509 -req \
  -in "$SERVER_CSR" \
  -CA "$CA_CRT" \
  -CAkey "$CA_KEY" \
  -CAserial "$CA_SRL" \
  -out "$SERVER_CRT" \
  -days "$DAYS" \
  -sha256 \
  -extfile "$server_ext_file"

cp "$CA_CRT" "$CA_BUNDLE"

chmod 600 "$CA_KEY" "$CLIENT_KEY" "$SERVER_KEY"
chmod 644 "$CA_CRT" "$CLIENT_CRT" "$SERVER_CRT" "$CA_BUNDLE"

# CSRs and extension files are only needed for issuance; keep them for traceability.
chmod 600 "$CLIENT_CSR" "$SERVER_CSR" "$client_ext_file" "$server_ext_file"

echo

echo "mTLS artifacts generated successfully:"
echo "  CA certificate:      $CA_CRT"
echo "  Client certificate:  $CLIENT_CRT"
echo "  Client key:          $CLIENT_KEY"
echo "  Server certificate:  $SERVER_CRT"
echo "  Server key:          $SERVER_KEY"
echo "  CA bundle:           $CA_BUNDLE"
echo

echo "Set backend service mTLS environment variables:"
echo "  SERVICE_MTLS_ENABLED=true"
echo "  SERVICE_MTLS_CLIENT_CERT_PATH=$CLIENT_CRT"
echo "  SERVICE_MTLS_CLIENT_KEY_PATH=$CLIENT_KEY"
echo "  SERVICE_MTLS_CA_BUNDLE_PATH=$CA_BUNDLE"
