#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { ConnectVanityNumbersStack } from '../lib/connect-vanity-numbers-stack';

const app = new cdk.App();
new ConnectVanityNumbersStack(app, 'ConnectVanityNumbersStack', {});