#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { NetworkStack } from '../lib/network-stack';
import { DataStack } from '../lib/data-stack';
import { ComputeStack } from '../lib/compute-stack';
import { ObservabilityStack } from '../lib/observability-stack';

const app = new cdk.App();

// Everything lives in one account (the logged-in profile) and one region (Mumbai).
const env = { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'ap-south-1' };   // the account comes from the logged-in AWS profile

// Your own IP, passed on the command line:  npx cdk diff -c myIp=203.0.113.7/32
const myIpCidr = app.node.tryGetContext('myIp');
if (!myIpCidr || !/^\d{1,3}(\.\d{1,3}){3}\/32$/.test(myIpCidr)) {
  throw new Error('Pass your public IP as a /32: npx cdk diff -c myIp=203.0.113.7/32');
}

const network = new NetworkStack(app, 'GenkartNetwork', { env, myIpCidr });
const data = new DataStack(app, 'GenkartData', { env });
const compute = new ComputeStack(app, 'GenkartCompute', { env, vpc: network.vpc, routerSg: network.routerSg, shardSg: network.shardSg, bucket: data.bucket, ingestQueue: data.ingestQueue, deadLetterQueue: data.deadLetterQueue });

// Monitoring: it now names the computers (status-check alarms), so ALWAYS deploy GenkartCompute first, then GenkartObservability. Optional: -c alarmEmail=you@example.com to also get alarm emails.
new ObservabilityStack(app, 'GenkartObservability', { env, ingestQueue: data.ingestQueue, deadLetterQueue: data.deadLetterQueue, hosts: compute.hosts, alarmEmail: app.node.tryGetContext('alarmEmail') });
