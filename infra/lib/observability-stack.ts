import * as fs from 'fs';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib/core';
import * as cw from 'aws-cdk-lib/aws-cloudwatch';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as cwActions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as subs from 'aws-cdk-lib/aws-sns-subscriptions';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';

export interface ObservabilityStackProps extends cdk.StackProps {
  readonly ingestQueue: sqs.IQueue;
  readonly deadLetterQueue: sqs.IQueue;
  /** The computers, for their health-check alarms. If given, this stack depends on the compute stack: deploy the computers FIRST. */
  readonly hosts?: Record<string, ec2.IInstance>;
  /** If given, every alarm also sends an email here (you must click the confirmation link AWS sends). */
  readonly alarmEmail?: string;
}

type FilterSpec = { id: string; group: string; pattern: string; metric: string; value: string; unit: string };

/**
 * What you look at to know the system is healthy:
 *  - four log groups (the agents on the machines write into them), kept 7 days
 *  - metric filters: turn numbers inside the JSON log lines into CloudWatch metrics (the patterns live in infra/cloudwatch/metric-filters.json,
 *    which scripts/test_metric_filters.py checks against real-shaped lines BEFORE deploying)
 *  - one dashboard, and alarms
 * This stack names no computer, so deploying it can never rebuild one. Alarms on the computers' own health checks come with the final rebuild.
 */
export class ObservabilityStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ObservabilityStackProps) {
    super(scope, id, props);
    const NS = 'GenKart';

    const groups: Record<string, logs.LogGroup> = {};
    for (const g of ['router', 'encoder', 'ingest', 'shard']) {
      groups[g] = new logs.LogGroup(this, `Logs-${g}`, {
        logGroupName: `/genkart/${g}`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,   // a learning project: destroying the stack removes the logs too
      });
    }

    const specs: FilterSpec[] = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'cloudwatch', 'metric-filters.json'), 'utf8'));
    for (const f of specs) {
      new logs.MetricFilter(this, `Filter-${f.id}`, {
        logGroup: groups[f.group],
        filterPattern: logs.FilterPattern.literal(f.pattern),
        metricNamespace: NS,
        metricName: f.metric,
        metricValue: f.value,
        unit: cw.Unit[f.unit.toUpperCase() as keyof typeof cw.Unit],
      });
    }

    const m = (name: string, statistic: string, minutes = 1) => new cw.Metric({ namespace: NS, metricName: name, statistic, period: cdk.Duration.minutes(minutes) });
    const dlqDepth = props.deadLetterQueue.metricApproximateNumberOfMessagesVisible({ statistic: 'Maximum', period: cdk.Duration.minutes(5) });
    const queueDepth = props.ingestQueue.metricApproximateNumberOfMessagesVisible({ statistic: 'Maximum', period: cdk.Duration.minutes(5) });

    // ---- alarms ----
    const topic = props.alarmEmail ? new sns.Topic(this, 'AlarmTopic') : undefined;
    if (topic && props.alarmEmail) topic.addSubscription(new subs.EmailSubscription(props.alarmEmail));
    const alarm = (idName: string, metric: cw.IMetric, threshold: number, description: string, evaluationPeriods = 1, datapointsToAlarm = 1) => {
      const a = new cw.Alarm(this, idName, {
        alarmName: `genkart-${idName}`, metric, threshold, evaluationPeriods, datapointsToAlarm, alarmDescription: description,
        comparisonOperator: cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        treatMissingData: cw.TreatMissingData.NOT_BREACHING,       // no log lines at all is not an emergency by itself
      });
      if (topic) { a.addAlarmAction(new cwActions.SnsAction(topic)); a.addOkAction(new cwActions.SnsAction(topic)); }
      return a;
    };
    const hostAlarms = Object.entries(props.hosts ?? {}).map(([name, instance]) =>
      alarm(`status-${name}`, new cw.Metric({ namespace: 'AWS/EC2', metricName: 'StatusCheckFailed', dimensionsMap: { InstanceId: instance.instanceId }, statistic: 'Maximum', period: cdk.Duration.minutes(1) }),
        1, `EC2 status checks are failing on ${name} (the machine or its network is unhealthy) for 2 of the last 3 minutes (watching ${instance.instanceId}).`, 3, 2));
    const alarms = [
      alarm('dlq-not-empty', dlqDepth, 1, 'A product is in the dead-letter queue: it failed too often or can never succeed. Read its reason, fix the cause, redrive.'),
      alarm('partial-answers', m('PartialAnswers', 'Sum', 5), 1, 'A search was answered without all shards (partial).'),
      alarm('search-p95-slow', m('SearchMs', 'p95'), 1000, 'Search p95 latency is at least 1 second (healthy is about 350 ms) for 3 of the last 5 minutes.', 5, 3),
      alarm('router-errors', m('ServerErrors', 'Sum', 5), 1, 'The router answered 5xx (no shard answered, or the encoder failed).'),
      alarm('router-shedding', m('ShedRequests', 'Sum', 5), 10, 'The router refused 10 or more searches in 5 minutes (HTTP 429 busy): demand is above what the encoder can serve.'),
      alarm('ingest-near-dlq', m('IngestNearDlq', 'Sum', 5), 1, 'An ingest message was received 6 or more times (the queue dead-letters at 8): something keeps failing.'),
      alarm('ingest-worker-errors', m('IngestStepErrors', 'Sum', 5), 1, 'The ingest worker hit an unexpected error in a batch.'),
      ...hostAlarms,
    ];

    // ---- dashboard ----
    const dash = new cw.Dashboard(this, 'Dashboard', { dashboardName: 'GenKart', defaultInterval: cdk.Duration.hours(3) });
    const search = (expr: string, label: string, period = 300) => new cw.MathExpression({ expression: `SEARCH('${expr}', 'Average', ${period})`, label, period: cdk.Duration.seconds(period), usingMetrics: {} });
    dash.addWidgets(
      new cw.AlarmStatusWidget({ title: 'Alarms (green = fine)', alarms, width: 24, height: 3 }),
    );
    dash.addWidgets(
      new cw.GraphWidget({ title: 'Search latency (ms)', width: 12, height: 6, left: [m('SearchMs', 'p50'), m('SearchMs', 'p95'), m('SearchMs', 'p99')], leftYAxis: { min: 0 } }),
      new cw.GraphWidget({ title: 'Searches per minute, and what went wrong', width: 12, height: 6,
        left: [m('Searches', 'Sum')], right: [m('PartialAnswers', 'Sum'), m('FailoverRequests', 'Sum'), m('ServerErrors', 'Sum'), m('ShedRequests', 'Sum'), m('EncoderDropped', 'Sum')], leftYAxis: { min: 0 }, rightYAxis: { min: 0 } }),
    );
    dash.addWidgets(
      new cw.GraphWidget({ title: 'Where the time goes (average ms)', width: 12, height: 6, left: [m('EncodeMs', 'Average'), m('ShardsMs', 'Average'), m('ShardRequestMs', 'Average'), m('EncoderRequestMs', 'Average')], leftYAxis: { min: 0 } }),
      new cw.GraphWidget({ title: 'Ingestion: products acknowledged vs failed attempts', width: 12, height: 6, left: [m('IngestAcked', 'Sum', 5), m('IngestFailed', 'Sum', 5)], leftYAxis: { min: 0 } }),
    );
    dash.addWidgets(
      new cw.GraphWidget({ title: 'Queue depth: waiting to be ingested, and dead letters', width: 12, height: 6, left: [queueDepth, dlqDepth], leftYAxis: { min: 0 } }),
      new cw.GraphWidget({ title: 'CPU % of every machine', width: 12, height: 6, left: [search('{AWS/EC2,InstanceId} MetricName="CPUUtilization"', 'cpu')], leftYAxis: { min: 0, max: 100 } }),
    );
    dash.addWidgets(
      new cw.GraphWidget({ title: 'Memory used % of every machine (CloudWatch agent)', width: 12, height: 6, left: [search('{GenKart/Host,InstanceId} MetricName="mem_used_percent"', 'memory')], leftYAxis: { min: 0, max: 100 } }),
      new cw.GraphWidget({ title: 'Disk used % of every machine (CloudWatch agent)', width: 12, height: 6, left: [search('{GenKart/Host,InstanceId,device,fstype,path} MetricName="disk_used_percent"', 'disk')], leftYAxis: { min: 0, max: 100 } }),
    );

    new cdk.CfnOutput(this, 'DashboardUrl', { value: `https://ap-south-1.console.aws.amazon.com/cloudwatch/home?region=ap-south-1#dashboards:name=GenKart` });
  }
}
