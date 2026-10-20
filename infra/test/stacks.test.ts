// Offline checks of the synthesized templates: no AWS account is touched (the account is a dummy, nothing is looked up).
import * as cdk from 'aws-cdk-lib/core';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { NetworkStack } from '../lib/network-stack';
import { DataStack } from '../lib/data-stack';
import { ComputeStack } from '../lib/compute-stack';
import { ObservabilityStack } from '../lib/observability-stack';

const env = { account: '123456789012', region: 'ap-south-1' };

function build(logGroupsExist = false) {
  const app = new cdk.App();
  const network = new NetworkStack(app, 'N', { env, myIpCidr: '203.0.113.7/32' });
  const data = new DataStack(app, 'D', { env, logGroupsExist });
  const compute = new ComputeStack(app, 'C', { env, vpc: network.vpc, routerSg: network.routerSg, shardSg: network.shardSg, bucket: data.bucket, ingestQueue: data.ingestQueue, deadLetterQueue: data.deadLetterQueue });
  const obs = new ObservabilityStack(app, 'O', { env, logGroups: data.logGroups, ingestQueue: data.ingestQueue, deadLetterQueue: data.deadLetterQueue, hosts: compute.hosts });
  return { network: Template.fromStack(network), data: Template.fromStack(data), compute: Template.fromStack(compute), obs: Template.fromStack(obs) };
}

const t = build();

test('the shard hosts accept only the router host, and only on the four shard ports', () => {
  const ingress = t.network.findResources('AWS::EC2::SecurityGroupIngress');
  const rules = Object.values(ingress).map((r: any) => r.Properties);
  expect(rules).toHaveLength(1);
  expect(rules[0]).toMatchObject({ IpProtocol: 'tcp', FromPort: 9101, ToPort: 9104 });
  expect(rules[0].SourceSecurityGroupId).toEqual({ 'Fn::GetAtt': [expect.stringMatching(/^RouterSg/), 'GroupId'] });
  expect(rules[0].CidrIp).toBeUndefined();
});

test('the router host is reachable only from the owner IP, on 9100', () => {
  t.network.hasResourceProperties('AWS::EC2::SecurityGroup', {
    GroupDescription: Match.stringLikeRegexp('router host'),
    SecurityGroupIngress: [{ CidrIp: '203.0.113.7/32', FromPort: 9100, ToPort: 9100, IpProtocol: 'tcp' }],
  });
});

test('the bucket blocks all public access, is encrypted and refuses plain http', () => {
  t.data.hasResourceProperties('AWS::S3::Bucket', {
    PublicAccessBlockConfiguration: { BlockPublicAcls: true, BlockPublicPolicy: true, IgnorePublicAcls: true, RestrictPublicBuckets: true },
    BucketEncryption: Match.objectLike({}),
  });
  t.data.hasResourceProperties('AWS::S3::BucketPolicy', {
    PolicyDocument: { Statement: Match.arrayWith([Match.objectLike({ Effect: 'Deny', Condition: { Bool: { 'aws:SecureTransport': 'false' } } })]) },
  });
});

test('every machine requires IMDSv2 and an encrypted disk', () => {
  const lts = Object.values(t.compute.findResources('AWS::EC2::LaunchTemplate')) as any[];
  expect(lts.length).toBe(3);
  for (const lt of lts) expect(lt.Properties.LaunchTemplateData.MetadataOptions.HttpTokens).toBe('required');
  const instances = Object.values(t.compute.findResources('AWS::EC2::Instance')) as any[];
  expect(instances.length).toBe(3);
  for (const i of instances) expect(i.Properties.BlockDeviceMappings[0].Ebs.Encrypted).toBe(true);
});

test('the shard token is a generated secret that both roles may read, and the user data never holds its value', () => {
  t.compute.hasResourceProperties('AWS::SecretsManager::Secret', { GenerateSecretString: Match.objectLike({ PasswordLength: 48, ExcludePunctuation: true }) });
  const policies = Object.values(t.compute.findResources('AWS::IAM::Policy')) as any[];
  const readers = policies.filter((p) => JSON.stringify(p.Properties.PolicyDocument).includes('secretsmanager:GetSecretValue'));
  const roles = readers.flatMap((p) => p.Properties.Roles.map((r: any) => r.Ref));
  expect(roles.some((r: string) => r.startsWith('ShardRole'))).toBe(true);
  expect(roles.some((r: string) => r.startsWith('RouterRole'))).toBe(true);
  const userData = JSON.stringify(t.compute.findResources('AWS::EC2::Instance'));
  expect(userData).toContain('GENKART_SHARD_TOKEN');
  expect(userData).not.toContain('{{');                       // every placeholder was filled in
  expect(userData).not.toMatch(/resolve:secretsmanager/);      // the secret is fetched on the machine, not baked into the template
});

test('the router host runs the compiled router on Node 22+', () => {
  const userData = JSON.stringify(t.compute.findResources('AWS::EC2::Instance'));
  expect(userData).toContain('nodejs24');
  expect(userData).not.toMatch(/dnf install -y nodejs(\s|\\n|$)/);   // the old plain-nodejs fallback (too old for the router) is gone
});

test('the log groups belong to the data stack (created before any machine), with a 7-day expiry; the monitoring stack makes none', () => {
  t.data.resourceCountIs('AWS::Logs::LogGroup', 4);
  t.data.hasResourceProperties('AWS::Logs::LogGroup', { LogGroupName: '/genkart/router', RetentionInDays: 7 });
  t.obs.resourceCountIs('AWS::Logs::LogGroup', 0);
  expect(Object.keys(t.obs.findResources('AWS::Logs::MetricFilter')).length).toBeGreaterThan(0);
});

test('with -c logGroupsExist=true the log groups are looked up by name, not created', () => {
  const again = build(true);
  again.data.resourceCountIs('AWS::Logs::LogGroup', 0);
  again.obs.hasResourceProperties('AWS::Logs::MetricFilter', { LogGroupName: '/genkart/router' });
});

const policiesOf = (role: string) => (Object.values(t.compute.findResources('AWS::IAM::Policy')) as any[])
  .filter((p) => p.Properties.Roles.some((r: any) => r.Ref.startsWith(role)))
  .flatMap((p) => p.Properties.PolicyDocument.Statement);

test('no AWS-managed CloudWatch agent policy: logs only into the host\'s own /genkart groups, metrics only in GenKart/Host', () => {
  const roles = Object.values(t.compute.findResources('AWS::IAM::Role')) as any[];
  expect(JSON.stringify(roles)).not.toContain('CloudWatchAgentServerPolicy');
  for (const [role, groups] of [['ShardRole', ['/genkart/shard']], ['RouterRole', ['/genkart/router', '/genkart/encoder', '/genkart/ingest']]] as const) {
    const st = policiesOf(role);
    const logsSt = st.find((s: any) => s.Sid === 'AgentLogs');
    expect([...logsSt.Action].sort()).toEqual(['logs:CreateLogStream', 'logs:DescribeLogStreams', 'logs:PutLogEvents']);
    const res = JSON.stringify(logsSt.Resource);
    for (const g of groups) expect(res).toContain(`log-group:${g}`);
    expect(res).not.toMatch(/log-group:\*|\/genkart\/\*/);                 // never every group
    expect(JSON.stringify(st)).not.toMatch(/logs:CreateLogGroup|ssm:GetParameter|ec2:Describe/);
    const metrics = st.find((s: any) => s.Sid === 'AgentMetrics');
    expect(metrics).toMatchObject({ Action: 'cloudwatch:PutMetricData', Resource: '*', Condition: { StringEquals: { 'cloudwatch:namespace': 'GenKart/Host' } } });
  }
});

test('S3: objects and listing only under each role\'s prefixes, nothing bucket-wide', () => {
  for (const [role, prefixes] of [['ShardRole', ['shards/']], ['RouterRole', ['shards/code/', 'ingest-photos/']]] as const) {
    const st = policiesOf(role).filter((s: any) => JSON.stringify(s.Action).includes('s3:'));
    expect(st.map((s: any) => s.Action).sort()).toEqual(['s3:GetObject', 's3:ListBucket']);
    const get = st.find((s: any) => s.Action === 's3:GetObject');
    const resources = [get.Resource].flat().map((r: any) => JSON.stringify(r));
    expect(resources).toHaveLength(prefixes.length);
    for (const p of prefixes) expect(resources.some((r) => r.includes(`/${p}*`))).toBe(true);
    const list = st.find((s: any) => s.Action === 's3:ListBucket');
    expect([...list.Condition.StringLike['s3:prefix']].sort()).toEqual(prefixes.flatMap((p) => [p, `${p}*`]).sort());
    expect(JSON.stringify(st)).not.toMatch(/s3:List\*|s3:GetBucket/);
  }
});

test('startup scripts: any failure leaves the marker, torch is hash-checked, code stays root-owned', () => {
  const userData = JSON.stringify(t.compute.findResources('AWS::EC2::Instance'));
  expect(userData.match(/trap 'touch \/opt\/genkart\/\.bootstrap-failed' ERR/g)).toHaveLength(3);   // two shard hosts and the router host
  expect(userData).toContain('--require-hashes --no-deps --index-url https://download.pytorch.org/whl/cpu -r requirements-torch-cpu.txt');
  expect(userData).not.toContain('torch==2');                                    // no unpinned-by-hash torch install left
  expect(userData).not.toContain('chown -R genkart:genkart /opt/genkart\\n');    // only the writable folders go to genkart
});
