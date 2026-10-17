import * as fs from 'fs';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
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
 * Badges (IAM roles): SSM for a shell without any open SSH port; shard hosts read shards/*; the router host reads shards/code/* only.
 */
export class ComputeStack extends cdk.Stack {
  public readonly hosts: Record<string, ec2.Instance> = {};   // for the monitoring stack (status-check alarms)

  constructor(scope: Construct, id: string, props: ComputeStackProps) {
    super(scope, id, props);

    const ssm = iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore');
    const cloudwatchAgent = iam.ManagedPolicy.fromAwsManagedPolicyName('CloudWatchAgentServerPolicy');   // lets the agent write logs and metrics
    const shardRole = new iam.Role(this, 'ShardRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      description: 'GenKart shard hosts: shell through SSM, read shard files from S3, write logs and metrics to CloudWatch',
      managedPolicies: [ssm, cloudwatchAgent],
    });
    props.bucket.grantRead(shardRole, 'shards/*');
    const routerRole = new iam.Role(this, 'RouterRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      description: 'GenKart router host: shell through SSM, read the code packages from S3, write logs and metrics to CloudWatch',
      managedPolicies: [ssm, cloudwatchAgent],
    });
    props.bucket.grantRead(routerRole, 'shards/code/*');
    // the ingest worker (runs on the router host): take jobs from the queue, park failed ones in the dead-letter queue, read the product photos
    props.ingestQueue.grantConsumeMessages(routerRole);
    props.deadLetterQueue.grantSendMessages(routerRole);
    props.bucket.grantRead(routerRole, 'ingest-photos/*');

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

    const shardScript = () => render('shard-host.sh', { BUCKET: props.bucket.bucketName });
    const shardHostA = host('ShardHostA', 0, 't4g.small', 16, shardRole, props.shardSg, shardScript(), 'shard-host-a');
    const shardHostB = host('ShardHostB', 1, 't4g.small', 16, shardRole, props.shardSg, shardScript(), 'shard-host-b');

    // router -> shards: for each of the 4 shards, copy on A | copy on B (the router fails over between them)
    const shardUrls = [0, 1, 2, 3].map((i) => `http://${shardHostA.instancePrivateIp}:${9101 + i}|http://${shardHostB.instancePrivateIp}:${9101 + i}`).join(',');
    // 2026-10-16: moved from zone a (subnet 0) to zone b (subnet 1): the stopped router could not be started in zone a (InsufficientInstanceCapacity), zone b had room.
    // 2026-10-16 (later): t4g.large was also out of capacity in zone b; switched to m6g.large (same 2 vCPU / 8 GB Graviton, a different capacity pool).
    // Earlier measurements (overload, failover, load test) were taken on t4g.large: do not mix them with numbers from this machine.
    const routerHost = host('RouterHost', 1, 'm6g.large', 24,   // was t4g.medium; moved to large by hand on 2026-10-15 because AWS had no free t4g.medium slot in zone a (InsufficientInstanceCapacity)
      routerRole, props.routerSg,
      render('router-host.sh', { BUCKET: props.bucket.bucketName, SHARD_URLS: shardUrls, QUEUE_URL: props.ingestQueue.queueUrl, DLQ_URL: props.deadLetterQueue.queueUrl }), 'router-host');

    new cdk.CfnOutput(this, 'RouterPublicIp', { value: routerHost.instancePublicIp });
    new cdk.CfnOutput(this, 'ShardHostAPrivateIp', { value: shardHostA.instancePrivateIp });
    new cdk.CfnOutput(this, 'ShardHostBPrivateIp', { value: shardHostB.instancePrivateIp });
  }
}
