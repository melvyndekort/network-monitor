#!/usr/bin/env python3
"""Restore device 'name' values lost to the 2026-10-02 TTL mass-purge.

Root cause: the devices table's TTL feature was enabled 2026-03-23 and every
device had a `ttl` attribute refreshed to now+14d on every activity ping.
Commit 09da53f (2026-09-18 19:39 UTC) stopped writing/refreshing `ttl` in
code, but never disabled the TTL *feature* on the table in Terraform/AWS.
Every device that was actively pinging right up to that deploy had its last
`ttl` value frozen at 19:39 UTC + 14 days = 2026-10-02 19:39 UTC. DynamoDB's
background TTL sweeper (no CloudTrail trail) then hard-deleted essentially
the entire device roster in that single window. Every device was then
recreated - unnamed - on its next ping. This is a one-time restore for that
incident: pull the device records as they existed just before the purge via
Point-in-Time Recovery (PITR), and backfill `name` into the live table by
MAC address. Identity/lookup is MAC-only throughout, matching the app's
design - no hostname matching is used.

Usage:
    python3 restore_device_names.py --dry-run     # show what would change
    python3 restore_device_names.py --apply       # actually update names
    python3 restore_device_names.py --apply --cleanup   # + delete the temp table after

Requires credentials with, on network-monitor-devices (account 844347863910,
eu-west-1): dynamodb:RestoreTableToPointInTime (on the restore target),
dynamodb:Scan, dynamodb:DescribeTable, dynamodb:UpdateItem, and (with
--cleanup) dynamodb:DeleteTable. Your own AWS CLI credentials/profile, not
the Hermes read-only role, which cannot create/restore/write tables.
"""
import argparse
import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION = "eu-west-1"
LIVE_TABLE = "network-monitor-devices"
RESTORE_TABLE = "network-monitor-devices-pre-purge-restore"

# Just before the frozen-ttl value (2026-09-18T19:39:32Z + 14d = 2026-10-02T19:39:32Z)
# came due. 30 minutes of slack before the purge window started.
RESTORE_POINT = "2026-10-02T19:00:00Z"


def get_client(profile=None):
    session = boto3.Session(profile_name=profile, region_name=REGION)
    return session.client("dynamodb"), session.resource("dynamodb")


def wait_for_table_active(client, table_name, timeout=600):
    print(f"Waiting for {table_name} to become ACTIVE...")
    waiter = client.get_waiter("table_exists")
    waiter.wait(TableName=table_name, WaiterConfig={"Delay": 5, "MaxAttempts": timeout // 5})
    while True:
        desc = client.describe_table(TableName=table_name)["Table"]
        status = desc["TableStatus"]
        print(f"  status={status}")
        if status == "ACTIVE":
            return
        time.sleep(10)


def restore_table(client):
    try:
        client.describe_table(TableName=RESTORE_TABLE)
        print(f"{RESTORE_TABLE} already exists, reusing it.")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    print(f"Restoring {LIVE_TABLE} to {RESTORE_POINT} as {RESTORE_TABLE} ...")
    client.restore_table_to_point_in_time(
        SourceTableName=LIVE_TABLE,
        TargetTableName=RESTORE_TABLE,
        RestoreDateTime=RESTORE_POINT,
    )
    wait_for_table_active(client, RESTORE_TABLE)


def scan_all(resource, table_name):
    table = resource.Table(table_name)
    items = []
    kwargs = {}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return {item["mac"]: item for item in items}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Actually write name updates (default: dry-run)")
    parser.add_argument("--cleanup", action="store_true", help="Delete the temp restored table when done")
    parser.add_argument("--profile", default=None, help="AWS CLI profile to use")
    args = parser.parse_args()

    client, resource = get_client(args.profile)

    identity = boto3.client("sts", region_name=REGION).get_caller_identity()
    print(f"Running as: {identity['Arn']}")
    if "844347863910" not in identity["Account"]:
        print(f"WARNING: not in account 844347863910 (got {identity['Account']}) - aborting.", file=sys.stderr)
        sys.exit(1)

    restore_table(client)

    print("Scanning live table...")
    live = scan_all(resource, LIVE_TABLE)
    print(f"  {len(live)} live devices")

    print("Scanning restored (pre-purge) table...")
    restored = scan_all(resource, RESTORE_TABLE)
    print(f"  {len(restored)} devices in pre-purge snapshot")

    to_update = []
    for mac, old in restored.items():
        old_name = old.get("name")
        if not old_name:
            continue
        current = live.get(mac)
        if current is None:
            continue  # device no longer tracked at all - nothing to restore onto
        if current.get("name"):
            continue  # already has a name (never lost, or already fixed) - never overwrite
        to_update.append((mac, old_name, old.get("device_type"), old.get("notify")))

    print(f"\n{len(to_update)} device(s) eligible for name restoration (matched by MAC, currently unnamed):")
    for mac, name, device_type, notify in to_update:
        print(f"  {mac}  ->  name={name!r}" + (f" device_type={device_type!r}" if device_type else ""))

    if not to_update:
        print("Nothing to do.")
    elif not args.apply:
        print("\nDry run only - rerun with --apply to write these updates.")
    else:
        live_table = resource.Table(LIVE_TABLE)
        for mac, name, device_type, notify in to_update:
            update_expr = "SET #n = :n"
            names = {"#n": "name"}
            values = {":n": name}
            if device_type:
                update_expr += ", device_type = :dt"
                values[":dt"] = device_type
            live_table.update_item(
                Key={"mac": mac},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
            )
            print(f"  updated {mac} -> {name!r}")
        print(f"\nDone. Restored {len(to_update)} name(s).")

    if args.cleanup:
        print(f"\nDeleting temp table {RESTORE_TABLE} ...")
        client.delete_table(TableName=RESTORE_TABLE)
        print("Deleted.")
    else:
        print(f"\n{RESTORE_TABLE} left in place. Delete it yourself when done:")
        print(f"  aws dynamodb delete-table --table-name {RESTORE_TABLE} --region {REGION}")


if __name__ == "__main__":
    main()
