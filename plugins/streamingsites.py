#!/usr/bin/python

# Copyright (C) Elkin Fricke (managementboy@gmail.com) 2011
# Released under the terms of the GNU GPL v2

#from videodownloader import providers
import sys
import os
import urllib2
import program
import subprocess

def Download(site, identifier, datadir):
  """Download a video from common video streaming sites

     Args:
        site:             (string)   name of the website (Vimeo, Youtube)
        identifyer:       (string)   unique identifier of the video (5720832 or tgbNymZ7vqY)
        tmpname:          (string)   where to put download
  """
  download_ok = False
  print 'Downloading "%s"...\n' % identifier
  filename = "" 
  filename = '%s/%s.flv' %(datadir, file)

  os.chdir(datadir)
  download = subprocess.Popen(['/usr/bin/youtube-dl', identifier], stdout=subprocess.PIPE)
  while download_ok == False:
    out = download.stdout.read(1)
    if out == '' and download.poll() != None:
      download_ok = True
    if out != '':
      sys.stdout.write(out)
      sys.stdout.flush()
 
  if not download_ok:
    return 0

  print 'New destination will be %s\n' % filename
  return os.path.basename(filename)
