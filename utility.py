#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2008
# Released under the terms of the GNU GPL v2

# Simple utility methods


import decimal
import os
import socket
import types


def DisplayFriendlySize(bytes):
  """DisplayFriendlySize -- turn a number of bytes into a nice string"""

  t = type(bytes)
  if t != types.LongType and t != types.IntType and t != decimal.Decimal:
    return 'NotANumber(%s=%s)' %(t, bytes)

  if bytes < 1024:
    return '%d bytes' % bytes

  if bytes < 1024 * 1024:
    return '%d kb (%d bytes)' %((bytes / 1024), bytes)

  if bytes < 1024 * 1024 * 1024:
    return '%d mb (%d bytes)' %((bytes / (1024 * 1024)), bytes)

  return '%d gb (%d bytes)' %((bytes / (1024 * 1024 * 1024)), bytes)


def DisplayFriendlyTime(seconds):
  """DisplayFriendlyTime -- turn a number of seconds into a nice string"""

  if seconds < 60:
    return '%d seconds' % seconds

  if seconds < 60 * 60:
    minutes = seconds / 60
    return '%d minutes, %d seconds' %(minutes, seconds - (minutes * 60))

  hours = seconds / (60 * 60)
  minutes = (seconds - (hours * 60 * 60)) / 60
  seconds = seconds - (hours * 60 * 60) - (minutes * 60)
  return '%d hours, %d minutes, %d seconds' %(hours, minutes, seconds)


class FilenameException(Exception):
  """ Errors with filenames """


# The following is a way of simplifying the lookup code for video directoies.
# The tuple format is (tablename, where, column)
_VIDEODIRPATH = [('storagegroup', 'groupname="MythNetTV"', 'dirname'),
                 ('storagegroup', 'groupname="Default"', 'dirname'),
                 ('settings', 'value="RecordFilePrefix"', 'data')]

def GetVideoDir(db):
  """GetVideoDir -- return the directory to store video in"""
  # Video directory lookup changes for the introduction of storage groups
  # in MythTV 0.21
  # TODO(mikal): I wonder if this works with 0.21 properly? I should test.
  videodir = None

  for (table, where, column) in _VIDEODIRPATH:
    if db.TableExists(table):
      try:
        videodir = db.GetOneRow('select * from %s where '
                                '%s and hostname = "%s";'
                                %(table, where,
                                  socket.gethostname()))[column]
      except:
        pass

    if videodir:
      break

  # Check we ended up with a video directory
  if videodir == None:
    raise FilenameException(db, 'Could not determine the video '
                            'directory for this machine. Please report '
                            'this to mythnettv@stillhq.com')
  
  # Check that it exists as well
  if not os.path.exists(videodir):
    raise FilenameException(db, 'MythTV is misconfigured. The video '
                            'directory "%s" does not exist. Please create '
                            'it, and then rerun MythNetTV.'
                            % videodir)

  return videodir


def ExplainVideoDir(db):
  """ExplainVideoDir -- return the directory to store video in"""

  videodir = None

  for (table, where, column) in _VIDEODIRPATH:
    if db.TableExists(table):
      try:
        print 'Checking %s for an entry where %s' %(table, where)
        for row in db.GetRows('select * from %s where %s;'
                              %(table, where)):
          print 'Found %s for %s' %(row[column], row['hostname'])
          if row['hostname'] == socket.gethostname():
            videodir = row[column]
            print 'Using this value'
                         
      except Exception, e:
        print '  DB error: %s' % e

    else:
      print 'Skipped using table %s as it doesn\'t exist' % table

    if videodir:
      print 'Will use: %s' % videodir
      print
      print '** All entries below here are informational only **'
      print

  # Check we ended up with a video directory
  if videodir == None:
    print 'Found no video directory'
    return
  
  # Check that it exists as well
  if not os.path.exists(videodir):
    print 'Video directory does not exist on disk!'

  print 'End of checks'


class LoggingException(Exception):
  """ Log exceptions to the database as well as returning them as exceptions
  """

  def __init__(self, db, error):
    if db:
      try:
        db.Log(error)
      except:
        pass

    Exception.__init__(self, error)
