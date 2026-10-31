from aws_cdk import CfnOutput, CfnParameter, Duration, Fn, Size, Stack
from aws_cdk import aws_cloudfront as cf, aws_cloudfront_origins as origins
from aws_cdk import aws_ec2 as ec2, aws_ecs as ecs, aws_iam as iam
from aws_cdk import aws_lambda as lam, aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct


class AppStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, data, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        image = CfnParameter(self, "ImageRepositoryName", description="ECR repository name containing the Lambda-compatible image tagged latest")
        image_tag = CfnParameter(self, "ImageTag", description="Immutable image tag for this deployment")
        vpc_id = CfnParameter(self, "VpcId", description="Default VPC ID")
        subnet_ids = CfnParameter(self, "PublicSubnetIds", type="List<AWS::EC2::Subnet::Id>", description="Public subnets in the default VPC")
        public_url = CfnParameter(self, "PublicUrl", default="", description="CloudFront HTTPS URL, filled in after first deploy")
        vpc = ec2.Vpc.from_vpc_attributes(self, "Vpc", vpc_id=vpc_id.value_as_string, availability_zones=Fn.get_azs(), public_subnet_ids=subnet_ids.value_as_list)
        sg = ec2.SecurityGroup(self, "WorkerSecurityGroup", vpc=vpc, allow_all_outbound=True)
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)
        task_role = iam.Role(self, "WorkerRole", role_name="BobWorkerTaskRole", assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"))
        execution_role = iam.Role(self, "ExecutionRole", assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"), managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonECSTaskExecutionRolePolicy")])
        api_role = iam.Role(self, "ApiRole", role_name="BobApiRole", assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"), managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")])
        for role in (api_role, task_role):
            data.table.grant_read_write_data(role)
            data.data_bucket.grant_read_write(role)
            data.secret.grant_read(role)
            role.add_to_policy(iam.PolicyStatement(actions=["sts:AssumeRole"], resources=[f"arn:{self.partition}:iam::*:role/BobBedrockAccess*"]))
        data.key.grant_encrypt_decrypt(api_role)
        data.key.grant_decrypt(task_role)
        task = ecs.FargateTaskDefinition(self, "Task", cpu=2048, memory_limit_mib=4096, task_role=task_role, execution_role=execution_role, runtime_platform=ecs.RuntimePlatform(cpu_architecture=ecs.CpuArchitecture.X86_64, operating_system_family=ecs.OperatingSystemFamily.LINUX))
        common = {"BOB_ENV": "aws", "BOB_AUTH": "none", "BOB_BEDROCK_AUTH": "assume_role", "BOB_RUNS_DIR": "/tmp/runs", "BOB_TABLE": data.table.table_name, "BOB_BUCKET": data.data_bucket.bucket_name, "BOB_SECRET_ARN": data.secret.secret_arn, "BOB_KMS_KEY_ID": data.key.key_arn, "BOB_ACCOUNT_ID": self.account, "BOB_COGNITO_REGION": self.region, "BOB_COGNITO_USER_POOL_ID": data.pool.user_pool_id, "BOB_COGNITO_CLIENT_ID": data.client.user_pool_client_id, "BOB_COGNITO_DOMAIN": data.domain.domain_name, "BOB_PUBLIC_URL": public_url.value_as_string, "BOB_EMBED_MODEL_PATH": "/opt/models/potion-base-8M"}
        log_group = logs.LogGroup(self, "WorkerLogs", retention=logs.RetentionDays.ONE_WEEK)
        repository = ecs_repository(self, image.value_as_string)
        task.add_container("worker", image=ecs.ContainerImage.from_ecr_repository(repository, tag=image_tag.value_as_string), environment=common, logging=ecs.LogDrivers.aws_logs(stream_prefix="worker", log_group=log_group))
        api_role.add_to_policy(iam.PolicyStatement(actions=["ecs:RunTask"], resources=[task.task_definition_arn], conditions={"ArnEquals": {"ecs:cluster": cluster.cluster_arn}}))
        api_role.add_to_policy(iam.PolicyStatement(actions=["ecs:StopTask", "ecs:DescribeTasks"], resources=[f"arn:{self.partition}:ecs:{self.region}:{self.account}:task/{cluster.cluster_name}/*"]))
        api_role.add_to_policy(iam.PolicyStatement(actions=["iam:PassRole"], resources=[task_role.role_arn, execution_role.role_arn], conditions={"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}))
        api_env = dict(common, BOB_ECS_CLUSTER=cluster.cluster_name, BOB_TASK_DEF=task.task_definition_arn, BOB_SUBNETS=Fn.join(",", subnet_ids.value_as_list), BOB_SECURITY_GROUP=sg.security_group_id, AWS_LWA_INVOKE_MODE="response_stream", AWS_LWA_READINESS_CHECK_PATH="/api/ping", PORT="8080")
        api = lam.DockerImageFunction(self, "Api", code=lam.DockerImageCode.from_ecr(repository, tag_or_digest=image_tag.value_as_string), role=api_role, memory_size=2048, timeout=Duration.seconds(900), ephemeral_storage_size=Size.mebibytes(2048), architecture=lam.Architecture.X86_64, environment=api_env)
        url = api.add_function_url(auth_type=lam.FunctionUrlAuthType.NONE, invoke_mode=lam.InvokeMode.RESPONSE_STREAM)
        rewrite = cf.Function(self, "SpaRewrite", code=cf.FunctionCode.from_inline("function handler(event) { var r=event.request; if (!r.uri.split('/').pop().includes('.')) r.uri='/index.html'; return r; }"))
        frontend = s3.Bucket.from_bucket_name(self, "ImportedFrontend", data.frontend_bucket.bucket_name)
        distribution = cf.Distribution(self, "Distribution", default_root_object="index.html", default_behavior=cf.BehaviorOptions(origin=origins.S3BucketOrigin.with_origin_access_control(frontend), viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS, function_associations=[cf.FunctionAssociation(function=rewrite, event_type=cf.FunctionEventType.VIEWER_REQUEST)]), additional_behaviors={"/api/*": cf.BehaviorOptions(origin=origins.FunctionUrlOrigin(url, read_timeout=Duration.seconds(60)), cache_policy=cf.CachePolicy.CACHING_DISABLED, origin_request_policy=cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER, allowed_methods=cf.AllowedMethods.ALLOW_ALL, viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS)})
        CfnOutput(self, "Url", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "DistributionId", value=distribution.distribution_id)


def ecs_repository(scope, repository_name):
    # Lambda image sources must be ECR; both services use the same tag.
    from aws_cdk import aws_ecr as ecr
    return ecr.Repository.from_repository_attributes(scope, "ImageRepository", repository_arn=Fn.sub("arn:${AWS::Partition}:ecr:${AWS::Region}:${AWS::AccountId}:repository/${Repo}", {"Repo": repository_name}), repository_name=repository_name)
