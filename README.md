# lambder-create-rds-snapshots

create-rds-snapshots is an AWS Lambda function for use with Lambder.

## REQUIRES:
* python-lambder

This lambda function creates an RDS snapshot from each RDS instance
tagged with Key: 'LambderBackup'. The function will retain at most 3 snapshots
and delete the oldest snapshot to stay under this threshold.

## Installation

1. Clone this repo
2. `cp example_lambder.json  lambder.json`
3. Edit lambder.json to set your S3  bucket
4. `lambder function deploy`

## Configuration

Create a file `config.json` within `lambda/create-rds-snapshots` and define the following parameters as JSON:

* AWS_REGION: The region in which the lambda will be running
* ACCOUNT_ID: The AWS account id in which the lambda will be running

## Usage

Schedule the function with a new event. Remember that the cron expression is
based on UTC.

    lambder events add \
      --name CreateRdsSnapshots \
      --function-name Lambder-create-rds-snapshots \
      --cron 'cron(0 6 ? * * *)'

## TODO

* Parameterize the tag in the input event object
* Parameterize number of old snapshots to retain
