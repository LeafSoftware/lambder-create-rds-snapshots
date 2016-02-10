#!/bin/bash
lambder events add \
  --name RdsBackups \
  --function-name Lambder-create-rds-snapshots \
  --cron 'cron(0 6 ? * * *)'
