#!/usr/bin/env python

import argparse
import logging
import subprocess
import json
import datetime
import dateutil.parser
import nagiosplugin

_log = logging.getLogger('nagiosplugin')


class Restic(nagiosplugin.Resource):

    restic_cmd = 'restic'

    def __init__(self, restic_args=[]):
        self.restic_args = restic_args

    def probe(self):
        cmd = [self.restic_cmd, 'snapshots', '--json', '--no-lock'] + self.restic_args
        try:
            restic_result = subprocess.check_output(cmd)
        except:
            raise nagiosplugin.CheckError('Failed to run %s' % cmd)
        snapshots = json.loads(restic_result)
        if not snapshots:
            raise nagiosplugin.CheckError('Could not find snapshots')
        snapshots.sort(key=lambda snapshot: dateutil.parser.parse(snapshot['time']))
        last_snapshot = dateutil.parser.parse(snapshots[-1]['time']).replace(tzinfo=None)
        last_snapshot_age = datetime.datetime.utcnow() - last_snapshot
        last_snapshot_age = last_snapshot_age.total_seconds() / (60*60)
        return nagiosplugin.Metric('last_snapshot_age', last_snapshot_age, uom='h')


@nagiosplugin.guarded
def main():
    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument('-w', '--warning', metavar='HOURS', type=int, default=24,
                      help='Snapshots older than HOURS are WARNING (default: %(default)s)')
    argp.add_argument('-c', '--critical', metavar='HOURS', type=int, default=48,
                      help='Snapshots older than HOURS are CRITICAL (default: %(default)s)')
    argp.add_argument('-H', '--host', metavar='HOST',
                      help='only consider snapshots for this host')
    argp.add_argument('--path', metavar='PATH',
                      help='only consider snapshots for this path')
    argp.add_argument('-r', '--repo', metavar='REPO',
                      help='repository to check backups (default: $RESTIC_REPOSITORY)')
    argp.add_argument('-p', '--password-file', metavar='PASSWORD_FILE',
                      help='read the repository password from a file (default: $RESTIC_PASSWORD_FILE)')
    argp.add_argument('-v', '--verbose', action='count', default=0,
                      help='increase output verbosity (use up to 3 times)')
    args = argp.parse_args()

    restic_args = []
    if args.host:
        restic_args.extend(['--host', args.host])
    if args.path:
        restic_args.extend(['--path', args.path])
    if args.repo:
        restic_args.extend(['--repo', args.repo])
    if args.password_file:
        restic_args.extend(['--password-file', args.password_file])

    check = nagiosplugin.Check(
        Restic(restic_args),
        nagiosplugin.ScalarContext('last_snapshot_age', args.warning, args.critical),
        )

    check.main(verbose=args.verbose)


if __name__ == '__main__':
    main()
