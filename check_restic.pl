#!/usr/bin/perl

use strict;
use warnings;
use POSIX 'strftime';

use Monitoring::Plugin;
use JSON;
use Date::Parse;
use Try::Tiny;

my $p = Monitoring::Plugin->new(
    usage => "Usage: %s "
      . "[ --sudo ] "
      . "[ -w|--warning=<hours> ] "
      . "[ -c|--critical=<hours> ] "
      . "[ -H|--host=<hostname>] "
      . "[ --path=<path> ] "
      . "[ -r|--repo=<repo>] "
      . "[ -p|--passwordfile=<file> ] ",
    url     => 'https://github.com/evgeni/check_restic',
    version => '1.1',
    license => 'This plugin is free software, and comes with ABSOLUTELY
NO WARRANTY. It may be used, redistributed and/or modified under
the terms of the MIT/Expat license.',
);

$p->add_arg(
    spec => 'sudo',
    help => 'Use sudo when invoking restic',
);

$p->add_arg(
    spec    => 'warning|w=i',
    help    => 'Snapshots older than INTEGER hours are WARNING (default: %s)',
    default => 24,
);

$p->add_arg(
    spec    => 'critical|c=i',
    help    => 'Snapshots older than INTEGER hours are CRITICAL (default: %s)',
    default => 48,
);

$p->add_arg(
    spec => 'host|H=s',
    help => 'only consider snapshots for this host',
);

$p->add_arg(
    spec => 'path=s',
    help => 'only consider snapshots for this path',
);

$p->add_arg(
    spec => 'repo|r=s',
    help => 'repository to check backups (default: $RESTIC_REPOSITORY)',
);

$p->add_arg(
    spec => 'passwordfile|p=s',
    help =>
'read the repository password from a file (default: $RESTIC_PASSWORD_FILE)',
);

$p->getopts;

my $restic_cmd = 'restic snapshots --json --no-lock';

if ( $p->opts->sudo ) { $restic_cmd = 'sudo ' . $restic_cmd; }
if ( $p->opts->host ) { $restic_cmd .= ' --host ' . $p->opts->host; }
if ( $p->opts->path ) { $restic_cmd .= ' --path ' . $p->opts->path; }
if ( $p->opts->repo ) { $restic_cmd .= ' --repo ' . $p->opts->repo; }
if ( $p->opts->passwordfile ) {
    $restic_cmd .= ' --password-file ' . $p->opts->passwordfile;
}

my $restic_output = qx($restic_cmd);
my $exitcode      = $? >> 8;

unless ( $exitcode eq 0 ) {
    $p->plugin_exit( UNKNOWN, "Failed to run '" . $restic_cmd . "'" );
}

my $restic_json;
try {
    $restic_json = decode_json $restic_output;
}
catch {
    $p->plugin_exit( UNKNOWN, "Could not find snapshots" );
};

my $last_snapshot = 0;

foreach my $snapshot (@$restic_json) {
    my $ts = str2time( $snapshot->{'time'} );
    if ( $ts > $last_snapshot ) { $last_snapshot = $ts }
}

my $msg =
  "last snapshot: " . strftime( '%Y-%m-%dT%H:%M:%SZ', gmtime($last_snapshot) );

my $delta = ( time() - $last_snapshot );
if ( $delta > ( $p->opts->critical * 60 * 60 ) ) {
    $p->add_message( CRITICAL, $msg );
}
elsif ( $delta > ( $p->opts->warning * 60 * 60 ) ) {
    $p->add_message( WARNING, $msg );
}
else {
    $p->add_message( OK, $msg );
}

my $code;
my $message;
( $code, $message ) = $p->check_messages;

$p->nagios_exit( $code, $message );
