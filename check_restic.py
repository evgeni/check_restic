#!/usr/bin/env python

import argparse
import logging
import subprocess
import json
import datetime
import dateutil.parser
import nagiosplugin
import os

_log = logging.getLogger('nagiosplugin')


class Restic(nagiosplugin.Resource):

    def __init__(self, restic_bin='restic', host=None, path=None, repo=None,
                 password_file=None, sudo=False):
        self.restic_bin = restic_bin
        self.host = host
        self.path = path
        self.repo = repo
        self.password_file = password_file
        self.sudo = sudo

    def probe(self):
        """
        Run restic and parse its output

        :return:
        """

        # For some reason, check.main() is the only place where exceptions are
        # printed nicely
        if not self.repo and not os.environ.get('RESTIC_REPOSITORY'):
            raise nagiosplugin.CheckError(
                'Please specify repository location (-r, --repo or '
                '$RESTIC_REPOSITORY)')
        if not self.password_file and \
           not (os.environ.get('RESTIC_PASSWORD') or
                os.environ.get('RESTIC_PASSWORD_FILE')):
            raise nagiosplugin.CheckError(
                'Please specify password or its location (-p, --password-file,'
                ' $RESTIC_PASSWORD or $RESTIC_PASSWORD_FILE)')

        cmd = [self.restic_bin, 'snapshots', '--json', '--no-lock']

        if self.sudo:
            cmd = ['sudo'] + cmd

        if self.host:
            cmd.extend(['--host', self.host])
        if self.path:
            cmd.extend(['--path', self.path])
        if self.repo:
            cmd.extend(['--repo', self.repo])
        if self.password_file:
            cmd.extend(['--password-file', self.password_file])

        _log.info('Using command: %s' % ' '.join(cmd))

        try:
            restic_result = subprocess.check_output(cmd,
                                                    stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            raise nagiosplugin.CheckError('Failed to run %s: %s' % (
                ' '.join(cmd), e.output.decode()))
        except IOError as e:
            raise nagiosplugin.CheckError('Failed to run %s: %s' % (
                ' '.join(cmd), e))
        _log.debug('Got output: %s' % restic_result)

        try:
            snapshots = json.loads(restic_result)
        except json.decoder.JSONDecodeError as e:
            raise nagiosplugin.CheckError(
                'Unable to parse restic output: %s' % e)
        _log.debug('Output decoded to: %s' % snapshots)

        if not snapshots:
            raise nagiosplugin.CheckError('Could not find snapshots')
        snapshots.sort(
            key=lambda snapshot: dateutil.parser.parse(snapshot['time']),
            reverse=True)
        last_snapshots = {}

        while True:
            try:
                e = next(e for e in snapshots if '_'.join(e['paths']) not in
                         last_snapshots.keys())
                last_snapshots['_'.join(e['paths'])] = e
            except StopIteration:
                break

        for path, snapshot in last_snapshots.items():
            snapshot_age = datetime.datetime.now(None) - \
                dateutil.parser.parse(snapshot['time']).replace(tzinfo=None)
            snapshot_age = snapshot_age.total_seconds() / (60*60)
            yield nagiosplugin.Metric(path, snapshot_age, uom='h',
                                      context='last_snapshot_age')


class ResticSummary(nagiosplugin.Summary):
    def ok(self, results):
        """
        Show all results in the output

        :param results:
        :return:
        """
        ret = ['%s is %.2f hours old' % (
            r.metric.name, r.metric.value) for r in results]
        return 'Snapshot %s' % ', '.join(ret)

    def problem(self, results):
        """
        Show only the results that have crossed the threshold

        :param results:
        :return:
        """
        if results.results[0].state == nagiosplugin.Unknown:
            return results.results[0].hint

        ret = ['%s is %.2f hours old' % (r.metric.name, r.metric.value)
               for r in results if r.state != nagiosplugin.Ok]
        return 'Snapshot %s' % ', '.join(ret)


@nagiosplugin.guarded
def main():
    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument(
        '--sudo', action='store_true',
        help='Use "sudo" when invoking restic (default: %(default)s)')
    argp.add_argument(
        '--restic-bin', type=str, metavar='RESTIC-BIN', default='restic',
        help='Path to the restic binary, or the name of restic in $PATH '
             '(default: %(default)s)')
    argp.add_argument(
        '-w', '--warning', metavar='HOURS', type=int, default=24,
        help='Snapshots older than HOURS are WARNING (default: %(default)s)')
    argp.add_argument(
        '-c', '--critical', metavar='HOURS', type=int, default=48,
        help='Snapshots older than HOURS are CRITICAL (default: %(default)s)')
    argp.add_argument('-H', '--host', metavar='HOST',
                      help='only consider snapshots for this host')
    argp.add_argument('--path', metavar='PATH',
                      help='only consider snapshots for this path')
    argp.add_argument(
        '-r', '--repo', metavar='REPO',
        help='repository to check backups (default: $RESTIC_REPOSITORY)')
    argp.add_argument(
        '-p', '--password-file', metavar='PASSWORD_FILE',
        help='read the repository password from a file (default: '
             '$RESTIC_PASSWORD_FILE)')
    argp.add_argument('-v', '--verbose', action='count', default=0,
                      help='increase output verbosity (use up to 3 times)')
    argp.add_argument(
        '-t', '--timeout', metavar='SECONDS', type=int, default=10,
        help='Plugin timeout in seconds (default: %(default)s)')
    args = argp.parse_args()

    check = nagiosplugin.Check(
        Restic(restic_bin=args.restic_bin, host=args.host, path=args.path,
               repo=args.repo, password_file=args.password_file,
               sudo=args.sudo),
        nagiosplugin.ScalarContext('last_snapshot_age',
                                   args.warning, args.critical),
        ResticSummary(),
        )

    check.main(verbose=args.verbose, timeout=args.timeout)


if __name__ == '__main__':
    main()
