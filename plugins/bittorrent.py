#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008, 2009
# Copyright (C) Elkin Fricke (managementboy@gmail.com) 2011
# Released under the terms of the GNU GPL v2

import commands
import datetime
import gflags
import os
import subprocess
import sys
import tempfile
import time
import re
import stat

#TransmisionClient
#import TransmissionClient
import transmissionrpc
from transmissionrpc.utils import *

#needed for hashing 
import base64 
import bencode
import hashlib

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
  tkey = -1  
  dir = tmpname
  out.write('Create new temporary directory... ')  
  if not os.path.exists(dir):
    os.makedirs(dir)
    os.chmod(dir,0o777)
    out.write('done!\n')
  else:
    out.write('Strange, it is already there! Please fix.\n') 
#    return 0

  out.write('Now fetching the bittorrent data\n')
  download_ok = False
  exit = False
  
  tc = transmissionrpc.Client('localhost', port=9091, user='admin', password='admin')

  torrent_file = open(torrent_filename)
  metainfo = bencode.bdecode(torrent_file.read())
  info = metainfo['info']

  #check if torrent is already being downloaded
  for keys in tc.info():
    if tc.info(keys)[keys].fields['hashString'] == hashlib.sha1(bencode.bencode(info)).hexdigest():
      out.write('The torrent is being downloaded by transmission. No need to add it again.\n')
      tkey = keys
  if tkey == -1:
    try:
      torrent = tc.add_uri(torrent_filename, download_dir=dir)
      out.write('Added torrent...')
      tkey = torrent.keys()[0]
    except transmissionrpc.TransmissionError, e:
      out.write('Failed to add torrent "%s"' % e)
      return 0

  tc.change(tkey, uploadLimit=upload_rate, uploadLimited=True)
  stalecounter = 0
  try:
    start_time = datetime.datetime.now()
    while not download_ok or not exit:
      time.sleep(5)
      oldprogress = tc.info(tkey)[tkey].progress
      #out.write('%s... ' % tc.info(tkey)[tkey].status)
      #if tc.info(tkey)[tkey].status == 'seeding':
      if tc.info(tkey)[tkey].progress == 100:
        #out.write('Seeding torrent...')
        download_ok = True
        break
      
      # kill download if it does not start after a few minutes
      if tc.info(tkey)[tkey].progress == 0:
        wait_time = datetime.datetime.now() - start_time
        out.write('\nHave waited %s for download to start\n'
                  %(time.strftime('%H:%M:%S', time.gmtime(wait_time.seconds))))
        if wait_time.seconds > 600:
          out.write('Waited %s for download to start. Giving up.\n'
                    % wait_time)
          exit = True
      # print the percent of download done if download started
      if tc.info(tkey)[tkey].progress >= 0:
        out.write('%.2f%% downloaded' % tc.info(tkey)[tkey].progress)
        out.write('\t%.2f %s left' % format_size(tc.info(tkey)[tkey].leftUntilDone))
        out.write('\t\tETA %- 13s\r' % tc.info(tkey)[tkey].format_eta())
        out.flush()
        if tc.info(tkey)[tkey].format_eta() == 'unknown' or tc.info(tkey)[tkey].format_eta() == 'not available':
          stalecounter = stalecounter + 1
      if stalecounter >= 600:
        out.write('Download has gone stale... stopping and removing')
        return 0
        exit = True
        
  except IOError, e:
    raise BitTorrentDownloadException('Error downloading bittorrent data: %s'
                                      % e)

  out.write('Bittorrent download finished\n')
  tc.remove(tkey, delete_data=False, timeout=None)
  out.write('Torrent stopped, waiting a few seconds...\n')

  if not download_ok:
    return 0
  time.sleep(5)  
  video_size = 0
  
  try:
    video_size = os.stat(tmpname).st_size
  except Exception, e:
    raise Exception('Error: %s\n' % e)

  return video_size
