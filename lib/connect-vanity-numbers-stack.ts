import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import * as iam from "aws-cdk-lib/aws-iam";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as path from "path";
import { aws_connect as connect } from "aws-cdk-lib";
const flowContent = require(path.join(__dirname, "..", "connect", "flow.json"));

export class ConnectVanityNumbersStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create a parameter for the Connect instance ARN
    const connectInstanceArn = new cdk.CfnParameter(
      this,
      "ConnectInstanceArn",
      {
        type: "String",
        description: "The ARN of the Amazon Connect instance",
        default: "",
      }
    );

    // Create DynamoDB table to store vanity number results
    const vanityResultsTable = new dynamodb.Table(this, "VanityResultsTable", {
      tableName: "vanity-number-results",
      partitionKey: {
        name: "phoneNumber",
        type: dynamodb.AttributeType.STRING,
      },
      removalPolicy: cdk.RemovalPolicy.DESTROY, // Use RETAIN for production
    });

    const vanityNumberLambda = new PythonFunction(
      this,
      "VanityNumberFunction",
      {
        entry: path.join(__dirname, "..", "vanity-number-lambda"),
        runtime: lambda.Runtime.PYTHON_3_13,
        index: "app.py",
        handler: "lambda_handler",
        timeout: cdk.Duration.minutes(5),
        memorySize: 512,
        environment: {
          DYNAMODB_TABLE_NAME: vanityResultsTable.tableName,
        },
      }
    );

    // Add IAM permissions for Bedrock
    vanityNumberLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ],
        resources: ["*"],
      })
    );

    // Grant Lambda permissions to read/write to DynamoDB table
    vanityResultsTable.grantReadWriteData(vanityNumberLambda);

    // Add resource-based policy to allow Amazon Connect to invoke the Lambda function
    vanityNumberLambda.addPermission("connect-access", {
      principal: new iam.ServicePrincipal("connect.amazonaws.com"),
      action: "lambda:InvokeFunction",
      sourceArn: connectInstanceArn.valueAsString,
    });

    // Replace tokens in flow content with actual Lambda function details
    const flowContentWithLambda = JSON.stringify(flowContent)
      .replace(/{LambdaFunctionARN}/g, vanityNumberLambda.functionArn)
      .replace(/{LambdaFunctionDisplayName}/g, vanityNumberLambda.functionName);

    // Create a Connect Contact Flow for vanity number lookup
    new connect.CfnContactFlow(this, "VanityNumberContactFlow", {
        content: flowContentWithLambda,
        instanceArn: connectInstanceArn.valueAsString,
        name: "Vanity Number Lookup Flow",
        description: "Contact flow for vanity number lookup using Lambda",
        type: "CONTACT_FLOW",
      }
    );
  }
}
