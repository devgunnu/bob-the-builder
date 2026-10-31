"""DynamoDB event log with atomic sequence allocation and replay."""

import asyncio
import json
import time
from collections.abc import AsyncIterator

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from bob.config import get_settings
from bob.core.models import Event


class DynamoEventLog:
    def __init__(self) -> None:
        settings = get_settings()
        self.table_name = settings.table
        self.table = boto3.resource("dynamodb").Table(self.table_name)
        self.client = boto3.client("dynamodb")
        self.poll = settings.event_poll_ms / 1000
        self.serializer = TypeSerializer()

    def _av(self, values: dict) -> dict:
        return {key: self.serializer.serialize(value) for key, value in values.items()}

    async def last_seq(self, job_id: str) -> int:
        item = await asyncio.to_thread(
            self.table.get_item, Key={"pk": f"JOB#{job_id}", "sk": "META"}, ConsistentRead=True
        )
        if "Item" not in item:
            raise KeyError(job_id)
        return int(item["Item"].get("last_seq", 0))

    async def append(self, job_id: str, type: str, data: dict) -> int:
        pk = f"JOB#{job_id}"
        payload = json.dumps(data, default=str)
        for attempt in range(20):
            previous = await self.last_seq(job_id)
            seq = previous + 1
            event = {
                "pk": pk,
                "sk": f"EVT#{seq:020d}",
                "type": type,
                "data": payload,
                "expires_at": int(time.time()) + 7 * 86400,
            }
            items = [
                {
                    "Update": {
                        "TableName": self.table_name,
                        "Key": self._av({"pk": pk, "sk": "META"}),
                        "UpdateExpression": "SET last_seq=:next",
                        "ConditionExpression": "attribute_exists(pk) AND (attribute_not_exists(last_seq) OR last_seq=:prev)",
                        "ExpressionAttributeValues": self._av({":next": seq, ":prev": previous}),
                    }
                },
                {
                    "Put": {
                        "TableName": self.table_name,
                        "Item": self._av(event),
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                },
            ]
            try:
                await asyncio.to_thread(self.client.transact_write_items, TransactItems=items)
                return seq
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "TransactionCanceledException":
                    raise
                reasons = exc.response.get("CancellationReasons", [])
                if not any(
                    reason.get("Code") in ("ConditionalCheckFailed", "TransactionConflict")
                    for reason in reasons
                ):
                    raise
                await asyncio.sleep(min(0.01 * (attempt + 1), 0.2))
        raise RuntimeError("event sequence remained contended")

    async def read_after(self, job_id: str, seq: int) -> list[Event]:
        def read() -> list[Event]:
            args = {
                "KeyConditionExpression": Key("pk").eq(f"JOB#{job_id}")
                & Key("sk").between(f"EVT#{seq + 1:020d}", "EVT#~"),
                "ConsistentRead": True,
            }
            out = []
            while True:
                page = self.table.query(**args)
                out.extend(
                    Event(id=int(item["sk"][4:]), type=item["type"], data=json.loads(item["data"]))
                    for item in page.get("Items", [])
                )
                if "LastEvaluatedKey" not in page:
                    return out
                args["ExclusiveStartKey"] = page["LastEvaluatedKey"]

        return await asyncio.to_thread(read)

    async def subscribe(self, job_id: str, last_event_id: int | None) -> AsyncIterator[Event]:
        seq = last_event_id or 0
        while True:
            for event in await self.read_after(job_id, seq):
                seq = event.id
                yield event
            await asyncio.sleep(self.poll)
