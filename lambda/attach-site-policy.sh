#!/usr/bin/env bash
#
# Allow the tylerbarron.com site Lambda to invoke camel-up-tournament.
#
#   ./lambda/attach-site-policy.sh <site-lambda-function-name>
#
# Find the site function name with:
#   aws lambda list-functions --query "Functions[?contains(FunctionName, 'WebsiteRemix')].FunctionName"
#
# Note: this attaches an inline policy to the Architect-generated role. If
# `arc deploy` ever recreates that role, re-run this script.

set -euo pipefail

SITE_FUNCTION=${1:?usage: attach-site-policy.sh <site-lambda-function-name>}
REGION=${AWS_REGION:-us-west-2}
FUNCTION=camel-up-tournament

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ROLE_ARN=$(aws lambda get-function --function-name "$SITE_FUNCTION" --region "$REGION" \
  --query 'Configuration.Role' --output text)
ROLE_NAME=${ROLE_ARN##*/}

aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name camel-up-invoke --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{
    \"Effect\": \"Allow\",
    \"Action\": [\"lambda:InvokeFunction\"],
    \"Resource\": \"arn:aws:lambda:$REGION:$ACCOUNT:function:$FUNCTION\"
  }]
}"

echo "attached camel-up-invoke to $ROLE_NAME"
