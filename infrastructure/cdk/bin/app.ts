#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { ArtifactStorageStack } from '../lib/artifact-storage-stack';

const app = new cdk.App();

new ArtifactStorageStack(app, 'Intent2Data-ArtifactStorageStack', {
  description: 'Intent2Data artifact storage foundation - S3 bucket for canonical runtime artifacts',
  /*
   * Environment-agnostic: deployable to any AWS account/region target
   * without hardcoded IDs.
   */
  runtimePrefix: 'runtime/',
});

app.synth();
