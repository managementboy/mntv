#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008
# Released under the terms of the GNU GPL v2

# Unit tests for mythnettv's video module


import gflags
import os
import sys
import unittest

import database
import testsetup
import video


FLAGS = gflags.FLAGS


class VideoTest(unittest.TestCase):
  def setUp(self):
    """ Download required testing files """
    
    for filename in ['video_length_fail.mov', 'video_length_works.avi',
                     'video_notavideo.mp4']:
      testsetup.DownloadTestData(filename)
    
  def testVideoInit(self):
    vid = video.MythNetTvVideo(None, '/tmp/testdata/video_length_fail.mov')

  def testVideoLengthError(self):
    """ Make sure the right thing happens when we fail to get the length
        of a video
    """
    
    try:
      vid = video.MythNetTvVideo(None, '/tmp/testdata/video_length_fail.mov')
      vid.Length()
    except video.LengthException, e:
      # This is the exception we want
      return

    self.fail()

  def testVideoLengthNotAVideo(self):
    """ Some sites don't return a video file, for example when your IP isn't
        in the country they allow downloads from. Make sure the right thing.
    """
      
    try:
      vid = video.MythNetTvVideo(None, '/tmp/testdata/video_notavideo.mp4')
      vid.Length()
    except video.LengthException, e:
      # This is the exception we want
      return

    self.fail()

  def testVideoLengthWorks(self):
    """ This one should work """
    
    vid = video.MythNetTvVideo(None, '/tmp/testdata/video_length_works.avi')
    len = vid.Length()
    self.assertEquals(int(len), 161)

  def testNeedsTranscode(self):
    """ A very simple test of whether to transcode a file """
    
    vid = video.MythNetTvVideo(None, '/tmp/testdata/video_length_works.avi')
    needs = vid.NeedsTranscode()
    self.assertEquals(needs, False)

  def testNewNeedsTranscode(self):
    """ Ensure that the new algorithm for deciding to transcode is consistent
        with the old one.
    """

    db = database.MythNetTvDatabase(dbname='mythnettv_tests',
                                    dbuser='test',
                                    dbpassword='test',
                                    dbhost='localhost')
    vid = video.MythNetTvVideo(db, '/tmp/testdata/video_length_works.avi')

    # Doesn't need transcoding
    return_false = ['mp4v', '0x10000002', 'divx', 'DIVX', 'XVID',
                    'DX50']

    # Does need transcoding
    # Note that some avc1 videos work, and some don't -- so all get transcoded
    return_true = ['avc1', 'theo', 'WMV2', 'FLV1']

    for format in return_false:
      vid.values['ID_VIDEO_FORMAT'] = format
      self.assertEquals(vid.NeedsTranscode(), False,
                        '%s should not be transcoded' % format)

    for format in return_true:
      vid.values['ID_VIDEO_FORMAT'] = format
      self.assertEquals(vid.NeedsTranscode(), True, 
                        '%s should not be transcoded' % format)

  def testEnsureNewFilenameUnique(self):
    """ When we generate a new filename, it should not be the same as an
        existing filename
    """

    vid = video.MythNetTvVideo(None, '/tmp/testdata/video_length_works.avi')
    new_name = vid.NewFilename('/tmp/testdata', 'avi')
    if os.path.exists('/tmp/testdata/%s' % new_name):
      self.fail()

  def testTranscode(self):
    """ Do a sample transcode """
    
    vid = video.MythNetTvVideo(None, '/tmp/testdata/video_length_works.avi')
    vid.Transcode('/tmp/testdata')
    

if __name__ == "__main__":
  # Parse flags
  try:
    argv = FLAGS(sys.argv)
  except gflags.FlagsError, e:
    out.write('%s\n' % e)
    Usage(out)

  unittest.main()
