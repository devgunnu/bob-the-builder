#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 1 ]]; then echo "Usage: $0 [aws-profile]" >&2; exit 2; fi
if [[ $# -eq 1 ]]; then export AWS_PROFILE="$1"; fi
export AWS_PAGER=""
read -r -p "AWS region: " AWS_REGION
export AWS_REGION AWS_DEFAULT_REGION="$AWS_REGION"
read -r -p "GitHub repository URL (https://github.com/owner/repo.git): " repo
read -r -p "Deployment branch [main]: " branch
branch=${branch:-main}
[[ "$repo" =~ ^https://github\.com/[^/]+/[^/]+(\.git)?$ ]] || { echo "Enter a GitHub HTTPS repository URL without credentials." >&2; exit 2; }
[[ "$branch" =~ ^[a-zA-Z0-9_/-]+$ ]] || { echo "Use a branch containing only letters, numbers, underscore, slash or hyphen." >&2; exit 2; }
read -r -s -p "GitHub personal access token: " token; echo
[[ -n "$token" ]] || { echo "Token is required." >&2; exit 2; }
account=$(aws sts get-caller-identity --query Account --output text)
echo "Creating CodeBuild in account $account, region $AWS_REGION. Its role has AdministratorAccess."
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Pass the token via stdin, not a command-line argument or a repository file.
printf '%s' "$token" | python3 -c 'import boto3,sys; boto3.client("codebuild").import_source_credentials(serverType="GITHUB", authType="PERSONAL_ACCESS_TOKEN", token=sys.stdin.read(), shouldOverwrite=False)'
unset token
aws cloudformation deploy --stack-name bob-codebuild --template-file "$script_dir/codebuild.yaml" --capabilities CAPABILITY_IAM --parameter-overrides "RepositoryUrl=$repo" "Branch=$branch" --no-fail-on-empty-changeset
aws codebuild start-build --project-name bob-infrastructure-deploy --source-version "$branch" --query 'build.{id:id,logs:logs.deepLink}' --output json
echo "Future pushes to $branch trigger the project. The GitHub branch must contain these infra files."
