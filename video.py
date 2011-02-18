#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008, 2009
# Released under the terms of the GNU GPL v2
import commands
import datetime
import os
import re
import sys

from stat import *

import gflags
import utility

# Define command line flags
gflags.DEFINE_boolean('verbose_transcode', False,
                      'Output verbose debugging information')
FLAGS = gflags.FLAGS


# Exceptions returned by this module
class TranscodeException(utility.LoggingException):
  """ Transcoding problems """

class LengthException(Exception):
  """ Exception while determining the length of a video """

class ParseException(Exception):
  """ Exception while trying to parse video characteristics """


class MythNetTvVideo:
  """MythNetTvVideo -- video handling methods

  This uses mplayer to determine the length of the video. Specifically, this
  command line does the trick:

  mplayer -frames 0 -identify <filename> 2>&1 | grep ID_LENGTH
  """

  def __init__(self, db, filename):
    """__init__ -- prime the pump to answer questions about the video"""

    self.db = db
    self.filename = filename
    self.values = {}

    if not os.path.exists(self.filename):
      raise ParseException('Video file missing')

    out = commands.getoutput('mplayer -vo null -frames 0 -identify "%s" '
                             '2>&1 | grep "="' \
                             % self.filename)
    for line in out.split('\n'):
      try:
        (key, value) = line.split('=')
        self.values[key] = value
      except:
        pass

    if len(self.values) == 0:
      raise ParseException('Could not parse video characteristics')

  def Length(self):
    """Length -- return the length of the video in seconds"""
    if 'ID_LENGTH' in self.values:
      return float(self.values['ID_LENGTH'])
    
    raise LengthException('Could not determine length of %s. '
                          'Attributes found = %s'
                          %(self.filename, self.values))

  def Audioprop(self):
    """Audioprop -- return the the audioproperties of a video"""
    if 'ID_AUDIO_NCH' in self.values:
      if self.values['ID_AUDIO_NCH'] == '1':
        return str('MONO')
      if self.values['ID_AUDIO_NCH'] == '2':
        return str('STEREO')
      if self.values['ID_AUDIO_NCH'] == '6':
        return str('SURROUND')
      else:
        return str('')
    #FIXME:Dolby detection needs to be added

  def Videoprop (self):
    """Videoprop  -- return the Videoproperties of a video"""
    if 'ID_VIDEO_WIDTH' in self.values:
      if float(self.values['ID_VIDEO_HEIGHT']) >= 1080:
        return str('1080')
      elif float(self.values['ID_VIDEO_HEIGHT']) >= 720:
        return str('720')
      elif float(self.values['ID_VIDEO_WIDTH']) >= 1280:
        return str('HDTV')
      elif float(self.values['ID_VIDEO_WIDTH']) / float(self.values['ID_VIDEO_HEIGHT']) >= 1.4:
        return str('WIDESCREEN')
      else:
        return str('')
    #FIXME:How can we guess more types?
    
#    raise LengthException('Could not determine the Audioproperties of %s. '
#                          'Attributes found = %s'
#                          %(self.filename, self.values))

  def Subtitletypes (self):
    """Subtitletypes  -- return the the subtitletypes of a video"""
    if 'ID_SUBTITLE_ID' in self.values:
      return str('NORMAL')
    else:
      return str('')
    #FIXME:How can we guess more types?


  def NeedsTranscode(self, out=sys.stdout):
    """NeedsTranscode -- decide if a video needs transcoding before import"""

    # Doesn't need transcoding
    return_false = ['mp4v', '0x10000002', 'divx', 'DIVX', 'XVID',
                    'DX50']

    # Does need transcoding
    # Note that some avc1 videos work, and some don't -- so all get transcoded
    return_true = ['FLV1','jpeg','WMV2']

    if self.values['ID_VIDEO_FORMAT'] in return_false:
      out.write('Files in format %s don\'t need transcoding\n'
                % self.values['ID_VIDEO_FORMAT'])
      return False

    if self.values['ID_VIDEO_FORMAT'] in return_true:
      out.write('Files in format %s do need transcoding\n'
                % self.values['ID_VIDEO_FORMAT'])
      return True

    else:
      out.write("""
****************************************************************
I don't know if we need to transcode videos in %s format
I'm going to give it a go without, and it if doesn't work
please report it to mikal@stillhq.com
****************************************************************
"""
                % self.values['ID_VIDEO_FORMAT'])
      return False

  def NewFilename(self, datadir, extn, out=sys.stdout):
    """NewFilename -- determine what filename to use after transcoding"""

    # We only return the filename portion, not the path
    re_filename = re.compile('^(.+)/(.+?)$')
    m = re_filename.match(self.filename)
    if m:
      file = m.group(2)
    else:
      file = self.filename

    # Try changing the extension to extn
    re_extension = re.compile('(.*)\.(.*?)')
    m = re_extension.match(file)
    if m:
      count = 1
      proposed_filename = '%s.%s' % (m.group(1), extn)
      while os.path.exists('%s/%s' %(datadir, proposed_filename)):
        out.write('Rejected %s as it already exists\n' % proposed_filename)
        count += 1
        proposed_filename = '%s_%d.%s' %(m.group(1), count, extn)

      return proposed_filename

    return 'new-%s' % file

  def Transcode(self, datadir, out=sys.stdout):
    """Transcode -- transcode the video to a better format. Returns the new
    filename.
    """

    # If the file is small, go for a format which will hopefully look nicer
    out.write('Transcoding\n')
    format = '-ovc lavc -oac lavc -lavcopts abitrate=128 -ffourcc DX50'
    newfilename = self.NewFilename(datadir, 'avi', out=out)
    start_size = os.stat(self.filename)[ST_SIZE]

    command = 'ffmpeg -i "%s" %s "%s/%s"' %(self.filename, format,
                                              datadir, newfilename)
    (status, output) = commands.getstatusoutput(command)

    if status != 0:
      raise TranscodeException(self.db,
                               'Transcode failed: %s\n%s\nCommand: %s'
                               %(status, output, command))

    # mencoder sometimes just returns junk data instead of doing the transcoding
    # -- the one example of this I have seen is when the file in question was
    # encumbered with DRM
    if os.stat('%s/%s' %(datadir, newfilename)).st_size < 10000:
      raise TranscodeException(self.db,
                               'Transcode failed: an impossibly small file '
                               'was returned')

    if FLAGS.verbose_transcode:
      out.write('----------\nmencoder output:\n%s\n----------\n\n' % output)

    # Log the file growth
    if self.db:
      self.db.Log('Transcoding changed size of file from %d to %d' \
                   %(start_size,
                   os.stat('%s/%s' %(datadir, newfilename))[ST_SIZE]))

    return newfilename

  def Remux(self, datadir, out=sys.stdout):
    """Remux -- Remux the video to MKV. Returns the new
    filename.
    """

    # If the file is small, go for a format which will hopefully look nicer
    out.write('Remuxing\n')
    format = '-acodec copy -vcodec copy'
    newfilename = self.NewFilename(datadir, 'avi', out=out)
    start_size = os.stat(self.filename)[ST_SIZE]

    command = 'ffmpeg -i "%s" %s "%s/%s"' %(self.filename, format,
                                              datadir, newfilename)
    (status, output) = commands.getstatusoutput(command)

    if status != 0:
      raise TranscodeException(self.db,
                               'Transcode failed: %s\n%s\nCommand: %s'
                               %(status, output, command))

    # mencoder sometimes just returns junk data instead of doing the transcoding
    # -- the one example of this I have seen is when the file in question was
    # encumbered with DRM
    if os.stat('%s/%s' %(datadir, newfilename)).st_size < 10000:
      raise TranscodeException(self.db,
                               'Transcode failed: an impossibly small file '
                               'was returned')

    if FLAGS.verbose_transcode:
      out.write('----------\nmencoder output:\n%s\n----------\n\n' % output)

    # Log the file change
    if self.db:
      self.db.Log('Remuxing changed size of file from %d to %d' \
                   %(start_size,
                   os.stat('%s/%s' %(datadir, newfilename))[ST_SIZE]))

    return newfilename



def Usage():
  print """Unknown command line. Try one of:'

The MythNetTV video subsystem may be queried directly. This
can be useful if you want to perform simple operations such
as asking if a given video file needs to be transcoded before
being imported into MythTV, or actually performing the
transcode.

length <path>       : return the length of a video in seconds
info <path>         : return all available information for a
                      given video
needstranscode <path>
                    : determine if a given file needs to be
                      transcoded before being imported into
                      MythTV
transcode <path> <output path>
                    : transcode the file into a format
                      suitable for MythTV
"""

  print '\n\nAdditionally, you can use these global flags:%s' % FLAGS
  sys.exit(1)


if __name__ == '__main__':
  # Parse flags
  try:
    argv = FLAGS(sys.argv)
  except gflags.FlagsError, e:
    out.write('%s\n' % e)
    Usage(out)

  # Present a simple user interface to query the video subsystem
  filename = None
  try:
    filename = argv[2]
    if not os.path.exists(filename):
      print '%s: file not found' % filename
      Usage()
  except:
    print 'Could not find a file argument'
    Usage()

  # Construct a video object
  vid = None
  try:
    vid = MythNetTvVideo(None, filename)
  except Exception, e:
    print 'Video processing error: %s' % e
    sys.exit(1)

  if argv[1] == 'length':
    try:
      print 'Length of %s: %s' %(sys.argv[2],
                                 utility.DisplayFriendlyTime(vid.Length()))
    except Exception, e:
      print 'Length error: %s' % e
      sys.exit(1)

  elif argv[1] == 'info':
    for key in vid.values:
      print '%s: %s' %(key, vid.values[key])

  elif argv[1] == 'needstranscode':
    print 'Needs transcoding: %s' % vid.NeedsTranscode()

  elif argv[1] == 'transcode':
    if vid.NeedsTranscode():
      print ('Created output file: %s/%s'
             %(argv[3], vid.Transcode(argv[3])))
             
  else:
    print 'Unknown command'
    Usage()
