import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';

export interface NetworkStackProps extends cdk.StackProps {
  /** Your own public IP as a /32, e.g. "203.0.113.7/32". Only this address may reach the router. */
  readonly myIpCidr: string;
}

/**
 * The private network GenKart runs in.
 *  - one VPC, two availability zones, public subnets only (no NAT gateway: it costs money every hour)
 *  - a free S3 gateway endpoint, so shard files travel inside AWS
 *  - two security groups (firewalls): one for the router host, one for the shard hosts
 * No SSH port is opened anywhere; shells come through SSM Session Manager.
 */
export class NetworkStack extends cdk.Stack {
  public readonly vpc: ec2.Vpc;
  public readonly routerSg: ec2.SecurityGroup;
  public readonly shardSg: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: NetworkStackProps) {
    super(scope, id, props);

    this.vpc = new ec2.Vpc(this, 'Vpc', {
      ipAddresses: ec2.IpAddresses.cidr('10.0.0.0/16'),
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24, mapPublicIpOnLaunch: true },
      ],
      gatewayEndpoints: { S3: { service: ec2.GatewayVpcEndpointAwsService.S3 } },
    });

    // Router host: the only machine you talk to. Port 9100 is the router's /search and /health.
    this.routerSg = new ec2.SecurityGroup(this, 'RouterSg', {
      vpc: this.vpc,
      description: 'GenKart router host: port 9100 from the owner IP only',
      allowAllOutbound: true, // needs to reach SQS, S3, SSM and the shard hosts
    });
    this.routerSg.addIngressRule(ec2.Peer.ipv4(props.myIpCidr), ec2.Port.tcp(9100), 'router API from my IP only');

    // Shard hosts: reachable only from the router host, on the four shard ports 9101-9104. On AWS the two copies of a shard live on two
    // machines (host A and host B, same port), so 9111-9114 (the second copy on the same machine) is used only by the laptop cluster.
    this.shardSg = new ec2.SecurityGroup(this, 'ShardSg', {
      vpc: this.vpc,
      description: 'GenKart shard hosts: shard ports from the router host only',
      allowAllOutbound: true, // needs S3 (shard files), SSM and CloudWatch
    });
    this.shardSg.addIngressRule(this.routerSg, ec2.Port.tcpRange(9101, 9104), 'shard workers 0-3, from router only');

    new cdk.CfnOutput(this, 'VpcId', { value: this.vpc.vpcId });
  }
}
