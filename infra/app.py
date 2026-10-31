import aws_cdk as cdk
from bob_infra.data_stack import DataStack
from bob_infra.app_stack import AppStack

app = cdk.App()
env = cdk.Environment(account=app.node.try_get_context("account"), region=app.node.try_get_context("region"))
data = DataStack(app, "BobData", env=env)
AppStack(app, "BobApp", data=data, env=env)
app.synth()
