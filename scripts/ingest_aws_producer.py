"""Put NEW (test) products on the AWS ingest queue, from your Mac, using YOUR AWS login (the "genkart" profile). Claude never runs this.
Each product reuses a photo that is already in the local catalogue under a NEW id (900000001...) and a title that says TEST, so nothing here
pretends to be real catalogue data. The photo goes to S3 (ingest-photos/<id>.jpg); the message carries its s3:// address.

  python scripts/ingest_aws_producer.py send   --bucket B --queue-url Q [--n 20] [--start 0]   upload photos + send n messages (dedup id = product id)
  python scripts/ingest_aws_producer.py resend --bucket B --queue-url Q [--n 20] [--start 0]   send the SAME messages again (SQS should drop them: 5-minute window)
  python scripts/ingest_aws_producer.py poison --bucket B --queue-url Q [--k 2]      send k messages whose photo does NOT exist in S3 (permanent error -> DLQ)
  python scripts/ingest_aws_producer.py fix-poison --bucket B [--k 2]                upload those missing photos (so a redrive can succeed)
Needs boto3 (in requirements.txt). Photos are chosen with a fixed seed, so every command agrees on which photo belongs to which id.
"""
import argparse
import glob
import json
import random

import boto3

BASE_ID, POISON_ID = 900_000_001, 900_000_901

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["send", "resend", "poison", "fix-poison"])
ap.add_argument("--bucket", required=True)
ap.add_argument("--queue-url", default=None)
ap.add_argument("--n", type=int, default=20, help="how many products")
ap.add_argument("--start", type=int, default=0, help="first product index: the ids are 900000001+start ... so each test can use fresh ids")
ap.add_argument("--k", type=int, default=2)
ap.add_argument("--profile", default="genkart")
ap.add_argument("--region", default="ap-south-1")
a = ap.parse_args()

session = boto3.Session(profile_name=a.profile, region_name=a.region)
s3, sqs = session.client("s3"), session.client("sqs")
photos = sorted(glob.glob("data/images/*.jpg"))
pick = random.Random(7).sample(photos, 200)             # fixed order of 200 photos: index i always means the same photo, whatever n/k/start are


def message(pid: int, i: int) -> dict:
    return {"id": str(pid), "source": "marqo", "gender": "", "cluster": 9_000_000 + (pid - BASE_ID), "title": f"TEST ingest product {pid} (reuses an existing photo)",
            "image": f"s3://{a.bucket}/ingest-photos/{pid}.jpg"}


def send(m: dict) -> None:
    sqs.send_message(QueueUrl=a.queue_url, MessageBody=json.dumps(m), MessageGroupId=m["id"], MessageDeduplicationId=m["id"])


if a.cmd == "send":
    for i in range(a.start, a.start + a.n):
        pid = BASE_ID + i
        s3.upload_file(pick[i], a.bucket, f"ingest-photos/{pid}.jpg")
        send(message(pid, i))
    print(f"uploaded {a.n} photos and sent {a.n} messages (ids {BASE_ID + a.start}..{BASE_ID + a.start + a.n - 1})")
elif a.cmd == "resend":
    for i in range(a.start, a.start + a.n):
        send(message(BASE_ID + i, i))
    print(f"re-sent the same {a.n} messages: SQS should drop them as duplicates (same dedup id within 5 minutes)")
elif a.cmd == "poison":
    for j in range(a.k):
        send(message(POISON_ID + j, j))                   # no photo uploaded on purpose
    print(f"sent {a.k} messages whose photos are NOT in S3 (ids {POISON_ID}..{POISON_ID + a.k - 1})")
elif a.cmd == "fix-poison":
    for j in range(a.k):
        s3.upload_file(pick[100 + j], a.bucket, f"ingest-photos/{POISON_ID + j}.jpg")
    print(f"uploaded the {a.k} missing photos; now redrive the dead-letter queue")
