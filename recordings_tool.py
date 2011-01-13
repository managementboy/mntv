#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2008
# Released under the terms of the GNU GPL v2

# Helpers for manipulating the MythTV recordings table. Useful for testing
# MythNetTV

import datetime
import os
import sys

import database
import gflags
import utility

# Define command line flags
FLAGS = gflags.FLAGS
gflags.DEFINE_boolean('keep', 5, 'Keep this number of episodes in deleteoldest')
gflags.DEFINE_boolean('prompt', True, 'Prompt before deleting')


def Usage():
  print """Unknown command line. Try one of:'

This is a helper script for the MythTV recordings table. Its useful for
cleanup and inspection when testing MythNetTV.

delete <title>       : delete all of the recordings with this title
deleteoldest <title> : delete the oldest versions of a title, keeping --keep
                       episodes
list                 : list all titles
list <title>         : list all the recordings with this title
summary              : print a summary of all recordings
unowned              : list all unknowned recording files

previously <title>   : list previous recordings for this title
rerecord <title>     : allow re-records of this title
rerecord <title> <subtitle>
                     : allow re-records of this title / subtitle combination
"""

  print '\n\nAdditionally, you can use these global flags:%s' % FLAGS
  sys.exit(1)


if __name__ == '__main__':
  # Parse flags
  try:
    argv = FLAGS(sys.argv)
  except gflags.FlagsError, e:
    Usage()

  if len(argv) < 2:
    Usage()

  db = database.MythNetTvDatabase()

  if argv[1] == 'list':
    if len(argv) > 2:
      for row in db.GetRows('select * from recorded where title="%s" '
                            'order by subtitle;'
                            % argv[2]):
        start = row['starttime']
        end = row['endtime']
        length = end - start
        
        print row['subtitle']
        print '  Recorded: %s' % start
        print '  Length: %.02f minutes' % (length.seconds / 60)
        print '  Video filename: %s' % row['basename']
        print ('  Video size: %s'
               % utility.DisplayFriendlySize(row['filesize']))
        print
    else:
      for row in db.GetRows('select distinct(title), count(*), sum(filesize) '
                            'from recorded group by title;'):
        print ('%s (%d recordings taking %s)'
               %(row['title'], row['count(*)'],
                 utility.DisplayFriendlySize(row['sum(filesize)'])))

  elif argv[1] == 'delete':
    for row in db.GetRows('select * from recorded where title="%s" '
                          'order by subtitle;'
                          % argv[2]):
      print 'Deleting %s : %s' %(row['title'], row['subtitle'])
      if FLAGS.prompt:
        print 'Are you sure you want to delete this show?\n'
        confirm = raw_input('Type yes to do this: ')
      else:
        confirm = 'yes'

      if confirm == 'yes':
        db.ExecuteSql('delete from recorded where chanid=%s and starttime=%s;'
                      %(row['chanid'],
                        db.FormatSqlValue('starttime', row['starttime'])))
        try:
          os.unlink('%s/%s' %(utility.GetVideoDir(db), row['basename']))
        except Exception, e:
          print 'Failed to remove recording file: %s' % e
      print

  elif argv[1] == 'deleteoldest':
    keep = FLAGS.keep
    print 'Keeping %d episodes' % keep
    for row in db.GetRows('select * from recorded where title="%s" '
                          'order by starttime desc;'
                          % argv[2]):
      keep -= 1
      if keep < 0:
        print 'Deleting %s : %s' %(row['title'], row['subtitle'])
        if FLAGS.prompt:
          print 'Are you sure you want to delete this show?\n'
          confirm = raw_input('Type yes to do this: ')
        else:
          confirm = 'yes'

          if confirm == 'yes':
            db.ExecuteSql('delete from recorded where chanid=%s and '
                          'starttime=%s;'
                          %(row['chanid'],
                            db.FormatSqlValue('starttime', row['starttime'])))
            os.unlink('%s/%s' %(utility.GetVideoDir(db), row['basename']))
      print

  elif argv[1] == 'summary':
    for row in db.GetRows('select distinct(title), count(*), sum(filesize) '
                          'from recorded group by title;'):
      print row['title']
      size = utility.DisplayFriendlySize(row['sum(filesize)'])
      print '  %d recordings, %s' %(row['count(*)'], size)
      print

  elif argv[1] == 'previously':
    for row in db.GetRows('select distinct(subtitle) from oldrecorded '
                          'where title="%s" order by subtitle;'
                          % argv[2]):
      print row['subtitle']
      allow_record = True
      for subrow in db.GetRows('select * from oldrecorded where title="%s" '
                               'and subtitle="%s" order by starttime;'
                               %(argv[2], row['subtitle'])):
        if subrow['duplicate'] != 0:
          allow_record = False
        print '  %s' % subrow['starttime']

      if allow_record:
        print '  Re-record allowed'
      print

  elif argv[1] == 'rerecord':
    if len(argv) > 4:
      db.ExecuteSql('update oldrecorded set duplicate=0 where title="%s" '
                    'and subtitle="%s";'
                    %(argv[2], argv[3]))
    else:
      db.ExecuteSql('update oldrecorded set duplicate=0 where title="%s";'
                    % argv[2])

  elif argv[1] == 'unowned':
    # TODO(mikal): handle users with more than one storage group
    videos = []
    dir = utility.GetVideoDir(db)
    for ent in os.listdir(dir):
      if not ent.endswith('.png') and os.path.isfile('%s/%s' %(dir, ent)):
        videos.append(ent)

    for row in db.GetRows('select * from recorded;'):
      if row['basename'] in videos:
        videos.remove(row['basename'])

    print 'Unowned videos: %s' % videos

  else:
    print 'Unknown command'
    Usage()
