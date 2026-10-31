#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for file in backend/Dockerfile backend/bob/api/app.py backend/bob/worker.py frontend/package.json; do
  [[ -f "$file" ]] || { echo "Missing $file: application implementation must be merged before deployment." >&2; exit 1; }
done
account=$(aws sts get-caller-identity --query Account --output text)
region=${AWS_DEFAULT_REGION:?}
vpc=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
[[ "$vpc" != None ]] || { echo "No default VPC found." >&2; exit 1; }
subnets=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$vpc" Name=default-for-az,Values=true --query 'Subnets[].SubnetId' --output text | tr '\t' ',')
[[ -n "$subnets" ]] || { echo "No default public subnets found." >&2; exit 1; }
repository=bob-application
aws ecr describe-repositories --repository-names "$repository" >/dev/null 2>&1 || aws ecr create-repository --repository-name "$repository" >/dev/null
registry="$account.dkr.ecr.$region.amazonaws.com"
tag=${CODEBUILD_RESOLVED_SOURCE_VERSION:?}
aws ecr get-login-password | docker login --username AWS --password-stdin "$registry"
docker build --platform linux/amd64 -f backend/Dockerfile -t "$registry/$repository:$tag" .
docker push "$registry/$repository:$tag"
npm --prefix frontend ci
npm --prefix frontend run build
cd infra
cdk bootstrap "aws://$account/$region"
cdk deploy --all --require-approval never --outputs-file outputs.json --parameters "BobApp:ImageRepositoryName=$repository" --parameters "BobApp:ImageTag=$tag" --parameters "BobApp:VpcId=$vpc" --parameters "BobApp:PublicSubnetIds=$subnets"
url=$(python3 -c 'import json; print(json.load(open("outputs.json"))["BobApp"]["Url"])')
bucket=$(python3 -c 'import json; print(json.load(open("outputs.json"))["BobData"]["OutputFrontendBucket"])')
cdk deploy BobApp --require-approval never --outputs-file outputs.json --parameters "BobApp:ImageRepositoryName=$repository" --parameters "BobApp:ImageTag=$tag" --parameters "BobApp:VpcId=$vpc" --parameters "BobApp:PublicSubnetIds=$subnets" --parameters "BobApp:PublicUrl=$url"
distribution=$(python3 -c 'import json; print(json.load(open("outputs.json"))["BobApp"]["DistributionId"])')
aws s3 sync ../frontend/dist "s3://$bucket/" --delete
aws cloudfront create-invalidation --distribution-id "$distribution" --paths '/*' >/dev/null
echo "Bob URL: $url"
