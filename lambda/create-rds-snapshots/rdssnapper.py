import boto3
import logging
import pprint
import os
import os.path
import json
from datetime import datetime

class RdsSnapper:

  TAG_NAME = "LambderBackup"

  def __init__(self):
    self.rds = boto3.client('rds')
    logging.basicConfig()
    self.logger = logging.getLogger()
    script_dir = os.path.dirname(__file__)
    config_file = script_dir + '/config.json'

    # if there is a config file in place, load it in. if not, bail.
    if not os.path.isfile(config_file):
      self.logger.error(config_file + " does not exist")
      exit(1)
    else:
      config_data=open(config_file).read()
      config_json = json.loads(config_data)
      self.AWS_REGION=config_json['AWS_REGION']
      self.ACCOUNT_ID=config_json['ACCOUNT_ID']

  def get_db_snapshot_arn(self, snapshotid):
    return "arn:aws:rds:{0}:{1}:snapshot:{2}".format(self.AWS_REGION,self.ACCOUNT_ID,snapshotid)

  def get_cluster_snapshot_arn(self, snapshotid):
    return "arn:aws:rds:{0}:{1}:cluster-snapshot:{2}".format(self.AWS_REGION,self.ACCOUNT_ID,snapshotid)

  def get_db_arn(self, dbid):
    return "arn:aws:rds:{0}:{1}:db:{2}".format(self.AWS_REGION,self.ACCOUNT_ID,dbid)

  def get_cluster_arn(self, clusterid):
    return "arn:aws:rds:{0}:{1}:cluster:{2}".format(self.AWS_REGION,self.ACCOUNT_ID,clusterid)

  def get_databases_to_backup(self):
    all_databases = self.rds.describe_db_instances()['DBInstances']
    backup_databases=[]

    for database in all_databases:
      dbarn=self.get_db_arn(database['DBInstanceIdentifier'])
      tags=self.rds.list_tags_for_resource(ResourceName=dbarn)['TagList']

      if any(d['Key'] == self.TAG_NAME for d in tags):
        backup_databases.append(database)

    return backup_databases

  def get_clusters_to_backup(self):
    all_clusters = self.rds.describe_db_clusters()['DBClusters']
    backup_clusters=[]

    for cluster in all_clusters:
      clusterarn=self.get_cluster_arn(cluster['DBClusterIdentifier'])
      tags=self.rds.list_tags_for_resource(ResourceName=clusterarn)['TagList']

      if any(d['Key'] == self.TAG_NAME for d in tags):
        backup_clusters.append(cluster)

    return backup_clusters

  # make a purdy name for the backup that is sortable
  def backup_name(self, source_name):
    time_str = datetime.utcnow().isoformat() + 'Z'
    time_str = time_str.replace(':', '').replace('+', '').replace('.', '')
    return source_name + '-' + time_str

  # Takes an snapshot, returns the backup source
  def get_db_backup_source(self, snapshot):
    snaparn=self.get_db_snapshot_arn(snapshot['DBSnapshotIdentifier'])
    snaptags=self.rds.list_tags_for_resource(ResourceName=snaparn)['TagList']
    tags = filter(lambda x: x['Key'] == self.TAG_NAME, snaptags)

    if len(tags) < 1:
      return None
    return tags[0]['Value']

  # Takes an snapshot, returns the backup source
  def get_cluster_backup_source(self, snapshot):
    snaparn=self.get_cluster_snapshot_arn(snapshot['DBClusterSnapshotIdentifier'])
    snaptags=self.rds.list_tags_for_resource(ResourceName=snaparn)['TagList']
    tags = filter(lambda x: x['Key'] == self.TAG_NAME, snaptags)

    if len(tags) < 1:
      return None
    return tags[0]['Value']

  # return a Dict() of {backupsource: list_of_snapshots}
  def get_db_snapshots_by_backup_source(self):
    all_snapshots = self.rds.describe_db_snapshots()['DBSnapshots']
    pp = pprint.PrettyPrinter()
    results={}

    for snapshot in all_snapshots:
      if snapshot['Status'] != "available":
        continue

      snaparn=self.get_db_snapshot_arn(snapshot['DBSnapshotIdentifier'])
      tags=self.rds.list_tags_for_resource(ResourceName=snaparn)['TagList']

      if any(d['Key'] == self.TAG_NAME for d in tags):
        tag=self.get_db_backup_source(snapshot)

        if tag in results:
          results[tag].append(snapshot)
        else:
          results[tag] = [snapshot]

    # sort snapshots by backup source
    for key in results.keys():
      results[key] = sorted(results[key], key=lambda x: x['SnapshotCreateTime'])

    return results

  # return a Dict() of {backupsource: list_of_snapshots}
  def get_cluster_snapshots_by_backup_source(self):
    all_snapshots = self.rds.describe_db_cluster_snapshots()['DBClusterSnapshots']
    pp = pprint.PrettyPrinter()
    results={}

    for snapshot in all_snapshots:
      if snapshot['Status'] != "available":
        continue

      snaparn=self.get_cluster_snapshot_arn(snapshot['DBClusterSnapshotIdentifier'])
      tags=self.rds.list_tags_for_resource(ResourceName=snaparn)['TagList']

      if any(d['Key'] == self.TAG_NAME for d in tags):
        tag=self.get_cluster_backup_source(snapshot)

        if tag in results:
          results[tag].append(snapshot)
        else:
          results[tag] = [snapshot]

    # sort snapshots by backup source
    for key in results.keys():
      results[key] = sorted(results[key], key=lambda x: x['SnapshotCreateTime'])

    return results

  def get_snapshots_to_delete(self, snapshots, max_to_keep=3):
    snapshots_to_delete = []

    if len(snapshots) >= max_to_keep:
      # remove one extra to make room for the next snapshot
      number_to_delete = len(snapshots) - max_to_keep + 1
      snapshots_to_delete = snapshots[0:number_to_delete]

    return snapshots_to_delete

  def prune_db_snapshots(self):
    pp = pprint.PrettyPrinter()
    db_snapshots_by_source = self.get_db_snapshots_by_backup_source()

    self.logger.debug('db_snapshots_by_source: ' + pp.pformat(db_snapshots_by_source))

    for source in db_snapshots_by_source.keys():
      all_db_snapshots = db_snapshots_by_source[source]
      to_delete = self.get_snapshots_to_delete(all_db_snapshots)
      self.logger.debug('db_snapshots_to_delete: ' + pp.pformat(to_delete))

      for condemned in to_delete:
        condemnedid=condemned['DBSnapshotIdentifier']
        self.logger.info("deleting " + condemnedid)
        self.rds.delete_db_snapshot(DBSnapshotIdentifier=condemnedid)

  def prune_cluster_snapshots(self):
    pp = pprint.PrettyPrinter()
    cluster_snapshots_by_source = self.get_cluster_snapshots_by_backup_source()

    self.logger.debug('cluster_snapshots_by_source: ' + pp.pformat(cluster_snapshots_by_source))

    for source in cluster_snapshots_by_source.keys():
      all_cluster_snapshots = cluster_snapshots_by_source[source]
      to_delete = self.get_snapshots_to_delete(all_cluster_snapshots)
      self.logger.debug('cluster_snapshots_to_delete: ' + pp.pformat(to_delete))

      for condemned in to_delete:
        condemnedid=condemned['DBClusterSnapshotIdentifier']
        self.logger.info("deleting cluster snapshot " + condemnedid)
        self.rds.delete_db_cluster_snapshot(DBClusterSnapshotIdentifier=condemnedid)

  def run(self):

    # prune old db snapshots if needed
    self.prune_db_snapshots()

    # prune old cluster snapshots if needed
    self.prune_cluster_snapshots()

    # create new backups
    databases = self.get_databases_to_backup()
    database_count = len(list(databases))

    self.logger.info("Found {0} databases to be backed up".format(database_count))

    for database in databases:
      if database['DBInstanceStatus'] != "available":
        continue

      databasename=database['DBInstanceIdentifier']
      snapname = self.backup_name(databasename)

      self.logger.info("Backing up {0}".format(databasename))
      self.rds.create_db_snapshot(
        DBSnapshotIdentifier=snapname,
        DBInstanceIdentifier=databasename,
        Tags=[{'Key': self.TAG_NAME, 'Value': databasename}]
      )

    databases = self.get_databases_to_backup()
    database_count = len(list(databases))

    # create new backups
    clusters = self.get_clusters_to_backup()
    cluster_count = len(list(clusters))

    self.logger.info("Found {0} clusters to be backed up".format(cluster_count))

    for cluster in clusters:
      if cluster['Status'] != "available":
        continue

      clustername=cluster['DBClusterIdentifier']
      snapname = self.backup_name(clustername)

      self.logger.info("Backing up {0}".format(clustername))
      self.rds.create_db_cluster_snapshot(
        DBClusterSnapshotIdentifier=snapname,
        DBClusterIdentifier=clustername,
        Tags=[{'Key': self.TAG_NAME, 'Value': clustername}]
      )
