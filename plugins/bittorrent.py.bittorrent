#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008, 2009
# Released under the terms of the GNU GPL v2

import commands
import datetime
import gflags
import os
import subprocess
import sys
import tempfile


FLAGS = gflags.FLAGS
gflags.DEFINE_string('uploadrate', '',
                     'Override the default upload rate for bittorrent for '
                     'just this one download')


class BitTorrentDownloadException(Exception):
  """Raised when download fails."""
  pass


def Download(torrent_filename, tmpname, info_func,
             upload_rate=1000000, verbose=False, out=sys.stdout):
  """Download a bittorrent

  Args:
     torrent_filename: (string)   path to the .torrent file
     tmpname:          (string)   where to put download
     info_func:        (function) called every now and then with status
     upload_rate:      (int)      limit the upload speed
     verbose:          (boolean)  dump a bunch of debug info as well
  """

  out.write('Now fetching the bittorrent data\n')
  download_ok = False
  try:
    cmd = '/usr/bin/btdownloadheadless.bittornado ' \
          '--max_upload_rate %s ' \
          '--display_interval 5 --spew 1 --saveas %s %s ' \
          %(upload_rate, tmpname, torrent_filename)
    po = subprocess.Popen(cmd, shell=True, bufsize=1,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    out.write('Executing: %s (pid %d)\n' %(cmd, po.pid))
    start_time = datetime.datetime.now()

    line = po.stdout.readline()
    while line:
      line = line.rstrip('\n')
      line = line.rstrip(' ')

      if verbose:
        print line

      if line.startswith('time left'):
        info_func(line)

        if line.endswith('Download Failed!'):
          out.write('Detected failed download\n')
          break
        elif line.endswith(':'):
          wait_time = datetime.datetime.now() - start_time
          out.write('Have waited %s (%d seconds)\n'
                    %(wait_time, wait_time.seconds))
          if wait_time.seconds > 600:
            out.write('Waited %s for download to start. Giving up.\n'
                      % wait_time)
            break
        elif line.endswith('Download Succeeded!'):
          out.write('Done!\n')
          download_ok = True
          break
        elif line.endswith('<unknown>'):
          out.write('Download got stuck. Giving up.\n')
          break

      line = po.stdout.readline()

  except IOError, e:
    raise BitTorrentDownloadException('Error downloading bittorrent data: %s'
                                      % e)

  out.write('Bittorrent download finished, kill download processes\n')
  commands.getoutput('for pid in `ps -ef | grep %s | grep -v grep | '
                     'tr -s " " | cut -f 2 -d " "`; do kill -9 $pid; done'
                     % po.pid)
  if not download_ok:
    return 0
    
  video_size = 0
  try:
    video_size = os.stat(tmpname).st_size
  except Exception, e:
    raise Exception('Error: %s\n' % e)

  return video_size
