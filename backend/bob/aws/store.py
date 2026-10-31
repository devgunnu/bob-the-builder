"""DynamoDB indexes and S3 job documents for the Store protocol."""

import asyncio
import time
import uuid
from typing import Literal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from bob.aws.blobs import S3Blobs
from bob.config import get_settings
from bob.core.models import Control, Job, JobStatus, Plan, Row, UserProfile


def _conditional(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


class DynamoStore:
    def __init__(self) -> None:
        self.table = boto3.resource("dynamodb").Table(get_settings().table)
        self.blobs = S3Blobs()

    async def _query(self, pk: str, prefix: str) -> list[dict]:
        def query() -> list[dict]:
            args = {
                "KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(prefix),
                "ConsistentRead": True,
            }
            out = []
            while True:
                page = self.table.query(**args)
                out.extend(page.get("Items", []))
                if "LastEvaluatedKey" not in page:
                    return out
                args["ExclusiveStartKey"] = page["LastEvaluatedKey"]

        return await asyncio.to_thread(query)

    async def _meta(self, job_id: str) -> dict:
        result = await asyncio.to_thread(
            self.table.get_item, Key={"pk": f"JOB#{job_id}", "sk": "META"}, ConsistentRead=True
        )
        if "Item" not in result:
            raise KeyError(job_id)
        return result["Item"]

    async def _put_job(self, job: Job, expected: JobStatus | None = None) -> bool:
        # Immutable object keys make the conditional META update the commit point.
        key = f"runs/{job.id}/jobs/{uuid.uuid4().hex}.json"
        await self.blobs.put(key, job.model_dump_json().encode(), "application/json")
        args = dict(
            Key={"pk": f"JOB#{job.id}", "sk": "META"},
            UpdateExpression="SET #status=:status, job_key=:key, owner_id=:owner, updated_at=:updated, expires_at=:ttl",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": job.status.value,
                ":key": key,
                ":owner": job.owner_id,
                ":updated": job.updated_at.isoformat(),
                ":ttl": int(job.created_at.timestamp()) + 7 * 86400,
            },
        )
        if expected is not None:
            args["ConditionExpression"] = "#status = :expected"
            args["ExpressionAttributeValues"][":expected"] = expected.value
        try:
            await asyncio.to_thread(self.table.update_item, **args)
        except ClientError as exc:
            if expected is not None and _conditional(exc):
                return False
            raise
        index = {
            "pk": f"USER#{job.owner_id}",
            "sk": f"JOB#{job.created_at.isoformat()}#{job.id}",
            "job_id": job.id,
        }
        await asyncio.to_thread(self.table.put_item, Item=index)
        return True

    async def put_job(self, job: Job) -> None:
        await self._put_job(job)

    async def put_job_if_status(self, job: Job, expected: JobStatus) -> bool:
        return await self._put_job(job, expected)

    async def get_job(self, job_id: str) -> Job:
        meta = await self._meta(job_id)
        return Job.model_validate_json(await self.blobs.get(meta["job_key"]))

    async def list_jobs(self, owner_id: str) -> list[Job]:
        entries = await self._query(f"USER#{owner_id}", "JOB#")
        jobs = []
        for entry in reversed(entries):
            try:
                job = await self.get_job(entry["job_id"])
            except KeyError:
                continue  # a job can expire before its persistent user index
            if job.owner_id == owner_id:
                jobs.append(job)
        return jobs

    async def put_rows(self, job_id: str, rows: list[Row]) -> None:
        for row in rows:
            if row.job_id != job_id:
                raise ValueError("row belongs to another job")
            key = {"pk": f"JOB#{job_id}", "sk": f"ROW#{row.id}"}
            counter = await asyncio.to_thread(
                self.table.update_item,
                Key={"pk": key["pk"], "sk": "META"},
                UpdateExpression="ADD row_seq :one",
                ExpressionAttributeValues={":one": 1},
                ConditionExpression="attribute_exists(pk)",
                ReturnValues="UPDATED_NEW",
            )
            number = counter["Attributes"]["row_seq"]
            await asyncio.to_thread(
                self.table.update_item,
                Key=key,
                UpdateExpression="SET #body=:body, verdict=:verdict, cell_id=:cell, #n=if_not_exists(#n,:n), expires_at=:ttl",
                ExpressionAttributeNames={"#body": "body", "#n": "n"},
                ExpressionAttributeValues={
                    ":body": row.model_dump_json(),
                    ":verdict": row.verdict,
                    ":cell": row.cell_id,
                    ":n": number,
                    ":ttl": int(time.time()) + 7 * 86400,
                },
            )

    async def list_rows(
        self,
        job_id: str,
        verdict: Literal["kept", "rejected"] | None = None,
        cell_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[int, list[Row]]:
        items = await self._query(f"JOB#{job_id}", "ROW#")
        items = sorted(
            (
                x
                for x in items
                if (verdict is None or x["verdict"] == verdict)
                and (cell_id is None or x["cell_id"] == cell_id)
            ),
            key=lambda x: x["n"],
        )
        return len(items), [Row.model_validate_json(x["body"]) for x in items[offset : offset + limit]]

    async def get_row(self, job_id: str, row_id: str) -> Row:
        result = await asyncio.to_thread(
            self.table.get_item, Key={"pk": f"JOB#{job_id}", "sk": f"ROW#{row_id}"}, ConsistentRead=True
        )
        if "Item" not in result:
            raise KeyError(row_id)
        return Row.model_validate_json(result["Item"]["body"])

    async def set_control(
        self, job_id: str, control: Literal["approved", "cancel"], plan: Plan | None = None
    ) -> None:
        values = {":state": control}
        expression = "SET #control=:state"
        if control == "approved":
            if plan is None:
                raise ValueError("approved control requires a plan")
            key = f"runs/{job_id}/plans/{uuid.uuid4().hex}.json"
            await self.blobs.put(key, plan.model_dump_json().encode(), "application/json")
            expression += ", plan_key=:plan"
            values[":plan"] = key
        await asyncio.to_thread(
            self.table.update_item,
            Key={"pk": f"JOB#{job_id}", "sk": "META"},
            UpdateExpression=expression,
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeNames={"#control": "control"},
            ExpressionAttributeValues=values,
        )

    async def get_control(self, job_id: str) -> Control:
        meta = await self._meta(job_id)
        plan = (
            Plan.model_validate_json(await self.blobs.get(meta["plan_key"])) if meta.get("plan_key") else None
        )
        return Control(state=meta.get("control"), plan=plan)

    async def get_user(self, user_id: str) -> UserProfile | None:
        result = await asyncio.to_thread(
            self.table.get_item, Key={"pk": f"USER#{user_id}", "sk": "PROFILE"}, ConsistentRead=True
        )
        return UserProfile.model_validate_json(result["Item"]["body"]) if "Item" in result else None

    async def put_user(self, user: UserProfile) -> None:
        # Update only the profile field, preserving any separately encrypted API keys.
        await asyncio.to_thread(
            self.table.update_item,
            Key={"pk": f"USER#{user.id}", "sk": "PROFILE"},
            UpdateExpression="SET #body=:body",
            ExpressionAttributeNames={"#body": "body"},
            ExpressionAttributeValues={":body": user.model_dump_json()},
        )
