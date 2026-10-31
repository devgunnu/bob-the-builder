# AWS infrastructure

The two Python CDK stacks implement the architecture in `.agents/CONTRACTS.md` section 13. They are intended for the planned short-lived demo environment: deleting the stacks deletes the buckets and their contents, the table, and the user pool. The stacks use fixed names and are intended for one installation per AWS account and region.

## Create the deployment project

Commit and push the infrastructure files to the GitHub branch first. From a checkout in AWS CloudShell, run `bash infra/deploy.sh PROFILE`. Enter the hosting region, GitHub HTTPS repository URL, branch, and a personal access token. The token must be able to read the repository and create a webhook. The script imports it as the regional CodeBuild GitHub source credential without overwriting an existing credential, creates the `bob-codebuild` CloudFormation stack, and starts a build. Pushes to the chosen branch trigger subsequent builds. If a GitHub credential already exists for CodeBuild, the import fails rather than replacing it; resolve the existing credential deliberately before retrying.

The CodeBuild role has AdministratorAccess as requested. Anyone who can push to the selected branch can run deployment code with that access. Protect the branch and restrict repository access. CodeBuild uses the default VPC and its default subnets, with public IPs for workers. The job build uses Docker in privileged mode. CDK bootstrapping and AWS resources incur charges.

The first deployment creates an empty Secrets Manager secret named `bob/keys`. Set its JSON value separately using Secrets Manager; do not commit keys. The stack creates an invite-only Cognito pool. The function URL is publicly reachable and relies on the application to verify Cognito tokens, as specified in the plan.

## Current blockers

The checkout still needs `backend/bob/api/app.py` and the frontend. The build stops before deployment until the required inputs exist. Other application integrations must also be complete for the service to work. The Dockerfile includes the Lambda Web Adapter and uses the same image for API and worker. A frontend lockfile is required for `npm ci`.

AWS storage uses immutable S3 job snapshots referenced by DynamoDB, and DynamoDB reservations coordinate Fargate worker limits. The API reserves capacity before saving a new job. A reservation left behind by a stopped worker is reclaimed during a later capacity check after the startup grace period.

`BobApp` receives the CloudFront URL in a second deploy to avoid a circular dependency. The script publishes the built frontend to S3 and invalidates CloudFront. API keys are not placed in build environment variables. CDK synthesis is not an end-to-end deployment test.
