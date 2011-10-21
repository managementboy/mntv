#!/usr/bin/python

# Copyright (C) Elkin Fricke (managementboy@gmail.com) 2011
# Released under the terms of the GNU GPL v2

from videodownloader import providers
import sys
import os
import urllib2


def Download(site, identifier, datadir):
  """Download a video from common video streaming sites

     Args:
        site:             (string)   name of the website (Vimeo, Youtube)
        identifyer:       (string)   unique identifier of the video (5720832 or tgbNymZ7vqY)
        tmpname:          (string)   where to put download
  """
  #initialize the provider from py-videodownloader
  provider = getattr(providers, site)
  #initialize the video we want to download
  video = provider(identifier)
  download_ok = False
  print 'Downloading "%s"...\n' % video.title
  video.filename = '%s/%s' %(datadir, video.filename)
  print 'New destination will be %s\n' % video.filename
  try:
    video.run()
    download_ok = True
  except (urllib2.HTTPError, IOError) as e:
    print e
  
  
  if not download_ok:
    return 0
  
  return os.path.basename(video.full_filename)
