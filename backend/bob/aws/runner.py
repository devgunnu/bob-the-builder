"""Fargate runner with DynamoDB reservations shared across API instances."""

import asyncio
import time
import uuid

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from bob.config import get_settings
from bob.core.runner import RunMode, RunnerBusy


class EcsRunner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.cluster = self.settings.ecs_cluster
        self.task_def = self.settings.task_def
        if not all((self.cluster, self.task_def, self.settings.subnets, self.settings.security_group)):
            raise ValueError("ECS cluster, task definition, subnets and security group are required")
        self.table = boto3.resource("dynamodb").Table(self.settings.table)
        self.ddb = boto3.client("dynamodb")
        self.ecs = boto3.client("ecs")
        self.ser = TypeSerializer()

    def _av(self, value: dict) -> dict:
        return {k: self.ser.serialize(v) for k, v in value.items()}

    async def _slots(self) -> list[dict]:
        def query() -> list[dict]:
            args = {"KeyConditionExpression": Key("pk").eq("CAPACITY"), "ConsistentRead": True}
            result = []
            while True:
                page = self.table.query(**args)
                result.extend(page.get("Items", []))
                if "LastEvaluatedKey" not in page:
                    return result
                args["ExclusiveStartKey"] = page["LastEvaluatedKey"]

        return await asyncio.to_thread(query)

    async def _task(self, job_id: str) -> dict | None:
        meta = await asyncio.to_thread(
            self.table.get_item, Key={"pk": f"JOB#{job_id}", "sk": "META"}, ConsistentRead=True
        )
        arn = meta.get("Item", {}).get("task_arn")
        if not arn:
            return None
        result = await asyncio.to_thread(self.ecs.describe_tasks, cluster=self.cluster, tasks=[arn])
        tasks = result.get("tasks", [])
        if not tasks and result.get("failures"):
            raise RuntimeError(f"ECS could not describe task: {result['failures']}")
        return tasks[0] if tasks else None

    async def release(self, job_id: str) -> None:
        slots = [item for item in await self._slots() if item.get("job_id") == job_id]
        if not slots:
            return
        items = [
            {
                "Delete": {
                    "TableName": self.settings.table,
                    "Key": self._av({"pk": "CAPACITY", "sk": item["sk"]}),
                    "ConditionExpression": "attribute_not_exists(pk) OR #token=:token",
                    "ExpressionAttributeNames": {"#token": "token"},
                    "ExpressionAttributeValues": self._av({":token": item["token"]}),
                }
            }
            for item in slots
        ]
        try:
            await asyncio.to_thread(self.ddb.transact_write_items, TransactItems=items)
        except ClientError as exc:
            reasons = exc.response.get("CancellationReasons", [])
            if exc.response.get("Error", {}).get("Code") != "TransactionCanceledException" or not any(
                r.get("Code") == "ConditionalCheckFailed" for r in reasons
            ):
                raise

    async def _reap(self) -> list[dict]:
        slots = await self._slots()
        # A task may still be starting before its ARN is saved. Leave it alone for two minutes.
        for item in slots:
            if item["sk"].startswith("WORKER#") and time.time() - int(item["created"]) > 120:
                task = await self._task(item["job_id"])
                if task is None or task.get("lastStatus") == "STOPPED":
                    await self.release(item["job_id"])
        return await self._slots()

    async def check_capacity(self, owner_id: str) -> None:
        slots = await self._reap()
        if (
            sum(x["sk"].startswith("WORKER#") for x in slots) >= self.settings.max_workers
            or sum(x.get("owner_id") == owner_id and x["sk"].startswith("OWNER#") for x in slots)
            >= self.settings.max_active_jobs_per_user
        ):
            raise RunnerBusy("too many running jobs")

    async def reserve(self, job_id: str, owner: str) -> None:
        await self._reap()
        token = uuid.uuid4().hex
        acquired = False
        for worker in range(self.settings.max_workers):
            for user_slot in range(self.settings.max_active_jobs_per_user):
                common = {
                    "pk": "CAPACITY",
                    "job_id": job_id,
                    "owner_id": owner,
                    "token": token,
                    "created": int(time.time()),
                }
                keys = [f"WORKER#{worker}", f"OWNER#{owner}#{user_slot}"]
                items = [
                    {
                        "Put": {
                            "TableName": self.settings.table,
                            "Item": self._av(dict(common, sk=key)),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    }
                    for key in keys
                ]
                try:
                    await asyncio.to_thread(self.ddb.transact_write_items, TransactItems=items)
                    acquired = True
                    break
                except ClientError as exc:
                    if exc.response.get("Error", {}).get("Code") != "TransactionCanceledException":
                        raise
                    reasons = exc.response.get("CancellationReasons", [])
                    if not any(
                        r.get("Code") in ("ConditionalCheckFailed", "TransactionConflict") for r in reasons
                    ):
                        raise
            if acquired:
                break
        if not acquired:
            raise RunnerBusy("too many running jobs")

    async def start(self, job_id: str, mode: RunMode) -> None:
        from bob.core.backends import get_store

        owner = (await get_store().get_job(job_id)).owner_id
        if not any(item.get("job_id") == job_id for item in await self._slots()):
            await self.reserve(job_id, owner)
        try:
            worker_env = {
                "BOB_ECS_CLUSTER": self.cluster,
                "BOB_TASK_DEF": self.task_def,
                "BOB_SUBNETS": ",".join(self.settings.subnets),
                "BOB_SECURITY_GROUP": self.settings.security_group,
            }
            response = await asyncio.to_thread(
                self.ecs.run_task,
                cluster=self.cluster,
                taskDefinition=self.task_def,
                launchType="FARGATE",
                count=1,
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": self.settings.subnets,
                        "securityGroups": [self.settings.security_group],
                        "assignPublicIp": "ENABLED",
                    }
                },
                overrides={
                    "containerOverrides": [
                        {
                            "name": self.settings.container_name,
                            "command": ["python", "-m", "bob.worker", job_id, mode],
                            "environment": [{"name": k, "value": v} for k, v in worker_env.items()],
                        }
                    ]
                },
            )
            if not response.get("tasks"):
                raise RuntimeError(f"ECS could not start task: {response.get('failures', [])}")
            arn = response["tasks"][0]["taskArn"]
            await asyncio.to_thread(
                self.table.update_item,
                Key={"pk": f"JOB#{job_id}", "sk": "META"},
                UpdateExpression="SET task_arn=:arn",
                ConditionExpression="attribute_exists(pk)",
                ExpressionAttributeValues={":arn": arn},
            )
        except Exception:
            if "arn" in locals():
                await asyncio.to_thread(
                    self.ecs.stop_task, cluster=self.cluster, task=arn, reason="Bob failed to record task"
                )
            await self.release(job_id)
            raise

    async def stop(self, job_id: str) -> None:
        task = await self._task(job_id)
        if task and task.get("lastStatus") != "STOPPED":
            await asyncio.to_thread(
                self.ecs.stop_task, cluster=self.cluster, task=task["taskArn"], reason="Bob job stopped"
            )

    async def is_running(self, job_id: str) -> bool:
        task = await self._task(job_id)
        if task:
            return task.get("lastStatus") != "STOPPED"
        # The API may observe a reservation while RunTask is still in flight.
        return any(
            item.get("job_id") == job_id and time.time() - int(item["created"]) < 120
            for item in await self._slots()
        )

    async def stopped_reason(self, job_id: str) -> str | None:
        task = await self._task(job_id)
        return (
            task.get("stoppedReason", "task stopped")
            if task and task.get("lastStatus") == "STOPPED"
            else None
        )
