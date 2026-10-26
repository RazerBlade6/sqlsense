#!/usr/bin/env bash
# Build the backend Lambda image and call GET /health through the Lambda Runtime Interface
# Emulator that ships in the AWS base image, using a Function URL (payload v2) event.
set -euo pipefail

docker build --platform linux/amd64 -f backend/Dockerfile -t sqlsense-backend .
docker run -d --rm --name sqlsense-lambda -p 9000:8080 -e AWS_REGION=ap-southeast-2 sqlsense-backend
trap 'docker logs sqlsense-lambda; docker stop sqlsense-lambda >/dev/null' EXIT

event='{"version":"2.0","routeKey":"$default","rawPath":"/health","rawQueryString":"",
"headers":{"host":"example.lambda-url.ap-southeast-2.on.aws"},
"requestContext":{"http":{"method":"GET","path":"/health","protocol":"HTTP/1.1","sourceIp":"127.0.0.1","userAgent":"ci"},
"domainName":"example.lambda-url.ap-southeast-2.on.aws","stage":"$default","requestId":"ci","accountId":"anonymous","apiId":"example","time":"","timeEpoch":0},
"isBase64Encoded":false}'

for _ in $(seq 1 30); do
  if response=$(curl -sf -XPOST localhost:9000/2015-03-31/functions/function/invocations -d "$event"); then
    echo "$response"
    echo "$response" | grep -q '"statusCode": *200' && exit 0
    echo "unexpected response" >&2
    exit 1
  fi
  sleep 1
done
echo "Lambda emulator did not respond" >&2
exit 1
