import * as fs from 'fs';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';

export interface ComputeStackProps extends cdk.StackProps {
  readonly vpc: ec2.IVpc;
  readonly routerSg: ec2.ISecurityGroup;
  readonly shardSg: ec2.ISecurityGroup;
  readonly bucket: s3.IBucket;
  readonly ingestQueue: sqs.IQueue;
  readonly deadLetterQueue: sqs.IQueue;
}

/** What a CloudWatch agent config (infra/cloudwatch/<file>) writes to: its log groups and its metric namespace. The role gets exactly these,
 *  read from the same file the machine uses, so the two cannot drift apart. */
export function agentTargets(file: string): { groups: string[]; namespace: string } {
  const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'cloudwatch', file), 'utf8'));
  const groups = [...new Set<string>((cfg.logs?.logs_collected?.files?.collect_list ?? []).map((f: { log_group_name: string }) => f.log_group_name))];
  const namespace = cfg.metrics?.namespace;
  if (typeof namespace !== 'string' || !namespace || groups.length === 0) throw new Error(`cloudwatch/${file} names no metrics.namespace or no log group`);
  return { groups, namespace };
}

/** Reads a startup script from infra/userdata and fills in {{PLACEHOLDERS}}. */
function render(file: string, vars: Record<string, string>): ec2.UserData {
  let script = fs.readFileSync(path.join(__dirname, '..', 'userdata', file), 'utf8');
  for (const [k, v] of Object.entries(vars)) script = script.split(`{{${k}}}`).join(v);
  return ec2.UserData.custom(script);
}

/**
 * The computers (all in the public subnets, no inbound doors except the security-group rules):
 *  - shard host A (zone a) and shard host B (zone b): each holds a full copy of the 4 shards. Two copies = failover.
 *  - router host (zone b since 2026-10-16, same zone as shard host B): the encoder and the router. The only machine you talk to (port 9100, from your IP only).
 * Every machine configures itself on first boot from a script in infra/userdata (changing the script replaces the machine).
 * Badges (IAM roles): both get SSM (a shell without any open SSH port), the CloudWatch agent's rights, and read access to the shard token.
 * The agent's rights are written out here instead of AWS's CloudWatchAgentServerPolicy (which may write to ANY log group and metric
 * namespace, create log groups, and read SSM parameters): streams and events in this host's own /genkart/* groups only (the groups
 * themselves come from the data stack, so the agent cannot make one without an expiry), and metrics only in the namespace its config file
 * (infra/cloudwatch/*-agent.json) names. No ec2:DescribeTags / DescribeVolumes: the configs use only ${aws:InstanceId}, which comes from the
 * instance metadata. S3 is granted per prefix, not with grantRead (which allows s3:List* and s3:GetBucket* on the whole bucket):
 * Shard hosts read shards/* (files and code). The router host reads shards/code/* (code packages) and ingest-photos/* (new product photos),
 * takes jobs from the ingest queue and sends to the dead-letter queue. Listing is allowed under those prefixes only (`aws s3 sync` needs it,
 * and with it a missing photo is a 404, which the ingest worker treats as permanent, rather than a 403).
 * Shard token: a random shared secret (Secrets Manager) the router and the ingest worker send as x-genkart-token; a shard worker refuses
 * /ingest without it. Each machine reads it at first boot into a root:genkart 0640 env file; it is never printed to a log.
 */
export class ComputeStack extends cdk.Stack {
  public readonly hosts: Record<string, ec2.Instance> = {};   // for the monitoring stack (status-check alarms)

  constructor(scope: Construct, id: string, props: ComputeStackProps) {
    super(scope, id, props);

    const shardToken = new secretsmanager.Secret(this, 'ShardToken', {
      description: 'GenKart shard token: shared secret between the router host (router, ingest worker) and the shard workers (x-genkart-token)',
      generateSecretString: { passwordLength: 48, excludePunctuation: true, includeSpace: false },   // letters and digits only: safe in a systemd env file
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const ssm = iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore');
    // the CloudWatch agent: write into the given log groups (streams and events, never new groups) and put metrics in one namespace
    const cloudwatchAgent = (role: iam.Role, agentConfig: string) => {
      const { groups, namespace } = agentTargets(agentConfig);
      const groupArn = (g: string) => this.formatArn({ service: 'logs', resource: 'log-group', resourceName: g, arnFormat: cdk.ArnFormat.COLON_RESOURCE_NAME });
      role.addToPolicy(new iam.PolicyStatement({
        sid: 'AgentLogs',
        actions: ['logs:CreateLogStream', 'logs:PutLogEvents', 'logs:DescribeLogStreams'],
        resources: groups.flatMap((g) => [groupArn(g), `${groupArn(g)}:log-stream:*`]),
      }));
      role.addToPolicy(new iam.PolicyStatement({
        sid: 'AgentMetrics',
        actions: ['cloudwatch:PutMetricData'],
        resources: ['*'],                                                     // PutMetricData has no resource: the namespace condition is the limit
        conditions: { StringEquals: { 'cloudwatch:namespace': namespace } },
      }));
    };
    // S3: read objects under the given prefixes, and list only under them
    const readPrefixes = (role: iam.Role, prefixes: string[]) => {
      role.addToPolicy(new iam.PolicyStatement({ sid: 'ReadObjects', actions: ['s3:GetObject'], resources: prefixes.map((p) => props.bucket.arnForObjects(`${p}*`)) }));
      role.addToPolicy(new iam.PolicyStatement({
        sid: 'ListPrefixes',
        actions: ['s3:ListBucket'],
        resources: [props.bucket.bucketArn],
        conditions: { StringLike: { 's3:prefix': prefixes.flatMap((p) => [p, `${p}*`]) } },
      }));
    };
    const shardRole = new iam.Role(this, 'ShardRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      description: 'GenKart shard hosts: shell through SSM, read shard files from S3, write logs and metrics to CloudWatch',
      managedPolicies: [ssm],
    });
    cloudwatchAgent(shardRole, 'shard-agent.json');            // /genkart/shard
    readPrefixes(shardRole, ['shards/']);
    shardToken.grantRead(shardRole);
    const routerRole = new iam.Role(this, 'RouterRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      description: 'GenKart router host: shell through SSM, read the code packages from S3, write logs and metrics to CloudWatch',
      managedPolicies: [ssm],
    });
    cloudwatchAgent(routerRole, 'router-agent.json');          // /genkart/router, /genkart/encoder, /genkart/ingest
    // shards/code/: the code packages; ingest-photos/: the product photos the ingest worker (on this host) embeds
    readPrefixes(routerRole, ['shards/code/', 'ingest-photos/']);
    shardToken.grantRead(routerRole);
    // the ingest worker: take jobs from the queue, park failed ones in the dead-letter queue
    props.ingestQueue.grantConsumeMessages(routerRole);
    props.deadLetterQueue.grantSendMessages(routerRole);

    const host = (name: string, subnetIndex: number, type: string, diskGb: number, role: iam.IRole, sg: ec2.ISecurityGroup, userData: ec2.UserData, tag: string) => {
      const instance = new ec2.Instance(this, name, {
        vpc: props.vpc,
        vpcSubnets: { subnets: [props.vpc.publicSubnets[subnetIndex]] },
        instanceType: new ec2.InstanceType(type),
        machineImage: ec2.MachineImage.latestAmazonLinux2023({ cpuType: ec2.AmazonLinuxCpuType.ARM_64 }),
        securityGroup: sg,
        role,
        userData,
        userDataCausesReplacement: true,           // a changed startup script = a fresh machine built from it
        requireImdsv2: true,
        associatePublicIpAddress: true,            // needed to reach S3/SSM/PyPI without a NAT gateway; the firewall still blocks inbound
        blockDevices: [{ deviceName: '/dev/xvda', volume: ec2.BlockDeviceVolume.ebs(diskGb, { volumeType: ec2.EbsDeviceVolumeType.GP3, encrypted: true, deleteOnTermination: true }) }],
      });
      cdk.Tags.of(instance).add('Project', 'genkart');
      cdk.Tags.of(instance).add('Role', tag);
      new cdk.CfnOutput(this, `${name}Id`, { value: instance.instanceId });
      new cdk.CfnOutput(this, `${name}Zone`, { value: instance.instanceAvailabilityZone });
      this.hosts[name] = instance;
      return instance;
    };

    const shardScript = () => render('shard-host.sh', { BUCKET: props.bucket.bucketName, SHARD_TOKEN_SECRET: shardToken.secretArn });
    const shardHostA = host('ShardHostA', 0, 't4g.small', 16, shardRole, props.shardSg, shardScript(), 'shard-host-a');
    const shardHostB = host('ShardHostB', 1, 't4g.small', 16, shardRole, props.shardSg, shardScript(), 'shard-host-b');

    // router -> shards: for each of the 4 shards, copy on A | copy on B (the router fails over between them). Ports 9101-9104 only (network-stack.ts)
    const shardUrls = [0, 1, 2, 3].map((i) => `http://${shardHostA.instancePrivateIp}:${9101 + i}|http://${shardHostB.instancePrivateIp}:${9101 + i}`).join(',');
    // 2026-10-16: moved from zone a (subnet 0) to zone b (subnet 1): the stopped router could not be started in zone a (InsufficientInstanceCapacity), zone b had room.
    // 2026-10-16 (later): t4g.large was also out of capacity in zone b; switched to m6g.large (same 2 vCPU / 8 GB Graviton, a different capacity pool).
    // Earlier measurements (overload, failover, load test) were taken on t4g.large: do not mix them with numbers from this machine.
    const routerHost = host('RouterHost', 1, 'm6g.large', 24,   // was t4g.medium; moved to large by hand on 2026-10-15 because AWS had no free t4g.medium slot in zone a (InsufficientInstanceCapacity)
      routerRole, props.routerSg,
      render('router-host.sh', { BUCKET: props.bucket.bucketName, SHARD_URLS: shardUrls, QUEUE_URL: props.ingestQueue.queueUrl, DLQ_URL: props.deadLetterQueue.queueUrl, SHARD_TOKEN_SECRET: shardToken.secretArn }), 'router-host');

    new cdk.CfnOutput(this, 'RouterPublicIp', { value: routerHost.instancePublicIp });
    new cdk.CfnOutput(this, 'ShardHostAPrivateIp', { value: shardHostA.instancePrivateIp });
    new cdk.CfnOutput(this, 'ShardHostBPrivateIp', { value: shardHostB.instancePrivateIp });
    new cdk.CfnOutput(this, 'ShardTokenSecretArn', { value: shardToken.secretArn });   // the address of the secret, not the secret: for deploy/apply-*-update.sh
  }
}
