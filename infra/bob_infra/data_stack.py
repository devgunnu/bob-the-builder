from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_cognito as cognito, aws_dynamodb as dynamodb, aws_kms as kms
from aws_cdk import aws_s3 as s3, aws_secretsmanager as secretsmanager
from aws_cdk import aws_iam as iam
from constructs import Construct


class DataStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        self.table = dynamodb.Table(self, "Table", table_name="bob", partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING), sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING), billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST, time_to_live_attribute="expires_at", removal_policy=RemovalPolicy.DESTROY)
        self.data_bucket = s3.Bucket(self, "DataBucket", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True, removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True)
        self.frontend_bucket = s3.Bucket(self, "FrontendBucket", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True, removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True)
        self.frontend_bucket.add_to_resource_policy(iam.PolicyStatement(actions=["s3:GetObject"], resources=[self.frontend_bucket.arn_for_objects("*")], principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")], conditions={"ArnLike": {"AWS:SourceArn": f"arn:{self.partition}:cloudfront::{self.account}:distribution/*"}}))
        self.secret = secretsmanager.Secret(self, "Keys", secret_name="bob/keys", removal_policy=RemovalPolicy.DESTROY)
        self.key = kms.Key(self, "UserKeys", alias="alias/bob-user-keys", enable_key_rotation=True, removal_policy=RemovalPolicy.DESTROY)
        self.pool = cognito.UserPool(self, "Users", sign_in_aliases=cognito.SignInAliases(email=True), self_sign_up_enabled=False, removal_policy=RemovalPolicy.DESTROY)
        self.client = self.pool.add_client("WebClient", generate_secret=False, auth_flows=cognito.AuthFlow(user_srp=True))
        self.domain = self.pool.add_domain("Domain", cognito_domain=cognito.CognitoDomainOptions(domain_prefix=f"bob-{self.account}-{self.region}"))
        for name, value in {"TableName": self.table.table_name, "DataBucket": self.data_bucket.bucket_name, "FrontendBucket": self.frontend_bucket.bucket_name, "SecretArn": self.secret.secret_arn, "UserPoolId": self.pool.user_pool_id, "ClientId": self.client.user_pool_client_id, "CognitoDomain": self.domain.domain_name}.items():
            CfnOutput(self, f"Output{name}", value=value)
