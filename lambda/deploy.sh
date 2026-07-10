#!/usr/bin/env bash
#
# Deploy the camel-up-tournament Lambda (engine + handler, python3.12).
#
# One-time + on engine/handler changes:
#   CAMEL_BUCKET=<cdn-asset-bucket> AWS_REGION=us-west-2 ./lambda/deploy.sh
#
# The function name is fixed (camel-up-tournament) so the website can invoke
# it by name. Its role can only read/write the camel-up S3 prefixes and
# re-invoke itself — no other AWS access, no secrets in env, because it
# executes untrusted submitted code. Reserved concurrency of 1 serializes
# tournaments so parallel submissions can't corrupt the leaderboard.
#
# After the FIRST site deploy (or if Architect ever recreates the site role),
# also run: ./lambda/attach-site-policy.sh <site-lambda-function-name>

set -euo pipefail

FUNCTION=camel-up-tournament
ROLE=camel-up-tournament-role
REGION=${AWS_REGION:-us-west-2}
BUCKET=${CAMEL_BUCKET:?set CAMEL_BUCKET to the CDN asset bucket name}
RUNTIME=python3.12
# 10240 MB is the Lambda max, ~6 vCPUs (2026-07-09, raised from 7076/4 to speed
# up 2000-game boards when a slow-but-legal upload is on the roster). Lambda
# bills GB-seconds and CPU scales with memory (~1 vCPU / 1769 MB), so with games
# parallelized across the vCPUs (handler.py) the cost per game is ~flat across
# memory sizes — more memory buys wall-clock speed, not lower cost. Partial
# vCPUs (e.g. 2048 MB = 1.16 vCPU) waste billed GB-s; whole-vCPU sizes are the
# efficient points. Keep CAMEL_WORKERS matched to the vCPU count below.
MEMORY=10240
TIMEOUT=900
GAMES=${CAMEL_TOTAL_GAMES:-2000}

cd "$(dirname "$0")/.."

BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
# Ship the engine + ONLY the house roster and smoke-test baselines. Contenders
# (bots/contenders/) are the private competitive lab and are never deployed;
# tournament_core discovers them at import and finds none here, so the Lambda
# runs the house roster plus whatever bots were accepted via the site.
zip -q "$BUILD/fn.zip" camelup.py playerinterface.py tournament_core.py \
  bots/__init__.py bots/house/*.py bots/test/*.py
zip -qj "$BUILD/fn.zip" lambda/handler.py lambda/sandbox.py lambda/storage.py

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
FUNCTION_ARN="arn:aws:lambda:$REGION:$ACCOUNT:function:$FUNCTION"

if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }' >/dev/null
  echo "created role $ROLE"
  sleep 10  # IAM propagation before create-function
fi

aws iam put-role-policy --role-name "$ROLE" --policy-name camel-up-tournament --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {
      \"Effect\": \"Allow\",
      \"Action\": [\"logs:CreateLogGroup\", \"logs:CreateLogStream\", \"logs:PutLogEvents\"],
      \"Resource\": \"arn:aws:logs:$REGION:$ACCOUNT:*\"
    },
    {
      \"Effect\": \"Allow\",
      \"Action\": [\"s3:GetObject\", \"s3:PutObject\"],
      \"Resource\": [
        \"arn:aws:s3:::$BUCKET/camel-up/*\",
        \"arn:aws:s3:::$BUCKET/images/camel-up/*\"
      ]
    },
    {
      \"Effect\": \"Allow\",
      \"Action\": [\"s3:ListBucket\"],
      \"Resource\": \"arn:aws:s3:::$BUCKET\",
      \"Condition\": {\"StringLike\": {\"s3:prefix\": [\"camel-up/*\", \"images/camel-up/*\"]}}
    },
    {
      \"Effect\": \"Allow\",
      \"Action\": [\"lambda:InvokeFunction\"],
      \"Resource\": \"$FUNCTION_ARN\"
    }
  ]
}"

if aws lambda get-function --function-name "$FUNCTION" --region "$REGION" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FUNCTION" --region "$REGION" \
    --zip-file "fileb://$BUILD/fn.zip" >/dev/null
  aws lambda wait function-updated --function-name "$FUNCTION" --region "$REGION"
  aws lambda update-function-configuration --function-name "$FUNCTION" --region "$REGION" \
    --runtime "$RUNTIME" --memory-size "$MEMORY" --timeout "$TIMEOUT" \
    --handler handler.handler \
    --environment "Variables={CAMEL_BUCKET=$BUCKET,CAMEL_TOTAL_GAMES=$GAMES,CAMEL_WORKERS=${CAMEL_WORKERS:-6}}" >/dev/null
  echo "updated $FUNCTION"
else
  aws lambda create-function --function-name "$FUNCTION" --region "$REGION" \
    --runtime "$RUNTIME" --memory-size "$MEMORY" --timeout "$TIMEOUT" \
    --handler handler.handler \
    --role "arn:aws:iam::$ACCOUNT:role/$ROLE" \
    --zip-file "fileb://$BUILD/fn.zip" \
    --environment "Variables={CAMEL_BUCKET=$BUCKET,CAMEL_TOTAL_GAMES=$GAMES}" >/dev/null
  echo "created $FUNCTION"
fi

aws lambda put-function-concurrency --function-name "$FUNCTION" --region "$REGION" \
  --reserved-concurrent-executions 1 >/dev/null

echo "done: $FUNCTION_ARN"
echo "seed the leaderboard with:"
echo "  aws lambda invoke --function-name $FUNCTION --region $REGION --invocation-type Event --payload '{\"op\":\"rerun\"}' --cli-binary-format raw-in-base64-out /dev/null"
