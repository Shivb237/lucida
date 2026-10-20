# GenKart on AWS (CDK)

The sharded search (encoder, router, 4 shard workers with 2 copies each, ingest worker) on three EC2 machines in `ap-south-1` (Mumbai).
Everything here is code: the user deploys it from their own machine. CI only runs `npm run build`, `npm test` and `cdk synth`, never a deploy.

**Cost warning.** While the stacks exist they cost money every hour, used or not: three machines (2 x t4g.small, 1 x m6g.large), their disks
and public IPv4 addresses, one Secrets Manager secret, CloudWatch logs, metrics, alarms and a dashboard. A rough estimate is about $2 a day
(check current AWS prices; this is not a quote). There is no NAT gateway and no load balancer on purpose. Tear down when you are done (below).

## The stacks

| Stack | What it holds | Depends on |
|---|---|---|
| `GenkartNetwork` | VPC (2 zones, public subnets only, free S3 gateway endpoint). `RouterSg`: port 9100 from your IP only. `ShardSg`: ports 9101-9104 from `RouterSg` only. No SSH anywhere (shells through SSM). | - |
| `GenkartData` | S3 bucket (private, encrypted, https only, emptied and deleted with the stack). SQS FIFO `ingest` queue and its dead-letter queue (8 tries). The four log groups `/genkart/{router,encoder,ingest,shard}`, kept 7 days. | - |
| `GenkartCompute` | Shard host A (zone a) and B (zone b), each with all 4 shards on 9101-9104; the router host (zone b): encoder, router, ingest worker. IMDSv2 required, encrypted disks. The shard token secret. | Network, Data |
| `GenkartObservability` | Metric filters (from `cloudwatch/metric-filters.json`), alarms (including one status check per machine), the `GenKart` dashboard, optional e-mail alerts. | Data, Compute |

Why the log groups are in `GenkartData`: the CloudWatch agent on a machine creates a missing log group on its own (with no expiry) a few
minutes after boot, and `GenkartObservability` can only be deployed after the machines. If that stack made the groups, it would fail with
"already exists". `GenkartData` is deployed before any machine, so the groups always exist first, with their expiry. If an agent made the
groups anyway (a machine started without this stack), add `-c logGroupsExist=true` and they are looked up by name instead of created.

**Do not use `logGroupsExist` to move from the older layout** (before 2026-10-18 `GenkartObservability` owned the groups, with "delete on
removal"). Updating that stack would delete the groups, their logs and the metric filters, and the alarms would go quiet. Instead tear the
old stacks down first (`npx cdk destroy --all`, then `scripts/teardown_check.sh`) and deploy this layout from nothing. The project's own
account was already torn down on 2026-10-16, so a fresh deploy there is the normal case.

**Shard token.** `GenkartCompute` makes a random 48-character secret in Secrets Manager. At first boot each machine reads it into a file that
only root and the `genkart` user can read: `/etc/genkart/shard.env` (`GENKART_SHARD_TOKEN`, shard workers), `/etc/genkart/router.env`
(`SHARD_TOKEN`, router) and `/etc/genkart/ingest.env` (`GENKART_SHARD_TOKEN`, ingest worker). Callers send it as `x-genkart-token`; a shard
refuses `/ingest` without it. The template holds only the secret's ARN, and the startup scripts turn shell tracing off while they handle it.

**Router.** It ships compiled (`services/router/dist`, plain JavaScript), so the router host needs Node 22 or newer (`nodejs24`, else `nodejs22`).

**Services.** Each systemd unit (`deploy/*.service`) runs as `genkart` in a sandbox: the file system read-only (`ProtectSystem=strict`; the
code and the venv belong to root) except the folders it writes (encoder: `/opt/genkart/.cache`; shard workers: `/opt/genkart/shards/n4`,
their write-ahead logs; ingest worker: `/opt/genkart/data/ingest-photos`; all: `/var/log/genkart`), no capabilities, no devices. Router,
encoder and shard workers cannot reach the instance metadata service (so not the machine's role); the ingest worker can, it needs the role
for SQS and S3. Each shard worker is capped at 420 MB (`MemoryMax`, 4 of them on a 2 GB t4g.small).

## Deploy (in this order)

Prerequisites: an AWS profile (`source scripts/aws_env.sh`), Node 22+, `npm ci` in this folder, and the shard files built locally
(`data/shards/n4/`, see `scripts/build_shards.py`). Every `cdk` command needs your public IP: `-c myIp=<your ip>/32`.

1. Once per account and region: `npx cdk bootstrap -c myIp=<ip>/32`.
2. Check offline first: `npm run build && npm test && npx cdk synth -c myIp=<ip>/32`. Also `.venv/bin/python scripts/test_metric_filters.py`.
3. Network and data: `npx cdk deploy GenkartNetwork GenkartData -c myIp=<ip>/32`. Save the `BucketName` output in `data/aws-bucket.txt`
   (git-ignored), then `source scripts/aws_env.sh` again so `$B` is set.
4. Package and upload what the machines read at boot:
   - `scripts/package_shard_code.sh` (runs the Python and router tests, builds the router, writes `data/deploy/*.tgz`, the CPU torch lock
     `requirements-torch-cpu.txt` and `MANIFEST.sha256`)
   - `aws s3 cp data/shards/n4/ s3://$B/shards/n4/ --recursive`
   - `aws s3 cp data/deploy/ s3://$B/shards/code/ --recursive --exclude '*' --include '*.tgz' --include requirements-torch-cpu.txt --include MANIFEST.sha256`
   - `for f in deploy/requirements-*.txt deploy/*.service deploy/genkart-logrotate.conf deploy/genkart-tmpfiles.conf infra/cloudwatch/*-agent.json; do aws s3 cp "$f" s3://$B/shards/code/; done`
5. Machines: `npx cdk deploy GenkartCompute -c myIp=<ip>/32`. Then `scripts/wait_bootstrap.sh <instance-id>` for each of the three
   (the router host needs about 10 minutes: torch and the model) and `scripts/verify_fleet.sh <routerId> <shardAId> <shardBId>`.
6. Monitoring: `npx cdk deploy GenkartObservability -c myIp=<ip>/32` (add `-c alarmEmail=you@example.com` for e-mails, then confirm the
   link AWS sends).

A changed startup script (`userdata/*.sh`) replaces the machine on the next deploy. To update code on running machines instead, upload the
new packages and run `deploy/apply-router-update.sh <bucket> [<ShardTokenSecretArn>]` / `deploy/apply-shard-update.sh <bucket> [<ShardTokenSecretArn>]`
on them through SSM (pass the ARN from the `GenkartCompute` output to write the token on machines built before it existed; do the shard
hosts and the router host together).

## Teardown

1. `npx cdk destroy --all -c myIp=<ip>/32` (removes the stacks in reverse order: monitoring, machines, then network and data; the bucket is
   emptied and deleted, the log groups go with `GenkartData`).
2. `source scripts/aws_env.sh; scripts/teardown_check.sh`: read-only listing of everything that could still cost money. Zero everywhere
   (except CDK's own bootstrap stack and bucket) means nothing of ours is left. The shard token secret then stays "scheduled for deletion"
   for 30 days: CloudFormation deletes it with Secrets Manager's default recovery window (30 days; the stack sets no shorter one). It costs
   nothing in that state, and its generated name never clashes with the next deploy's. To end it at once:
   `aws secretsmanager delete-secret --secret-id <arn> --force-delete-without-recovery`.

## Commands

- `npm run build`: type-check (no output files; `cdk.json` runs `bin/infra.ts` through `tsx`)
- `npm test`: jest checks of the synthesized templates (`test/stacks.test.ts`: shard ports open only to the router, bucket not public,
  IMDSv2, the token secret and who can read it, log-group ownership, the CloudWatch agent's narrow rights (own log groups, one metric
  namespace), S3 read per prefix only, and the startup scripts' failure marker and hash-checked torch). Offline: no account is contacted.
- `npx cdk synth -c myIp=<ip>/32`: the CloudFormation templates; `npx cdk diff -c myIp=<ip>/32` against what is deployed.
