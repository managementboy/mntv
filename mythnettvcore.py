#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008, 2009
# Released under the terms of the GNU GPL v2

# This file is the core of MythNetTV. It is intended that user interfaces call
# into this module to get things done, and then present their own interface in
# whatever manner makes sense to them

import gflags
import sys
import traceback

import database
import program
import proxyhandler
import syndication


gflags.DEFINE_boolean('oldestfirst', False,
                      'Download the oldest programs first')
gflags.DEFINE_boolean('newestfirst', False,
                      'Download the newest programs first')

gflags.DEFINE_boolean('verbose', False,
                      'Output verbose debugging information')
FLAGS = gflags.FLAGS

def NextDownloads(count, filter, subtitle, out=sys.stdout):
  """NextDownloads -- return a list of the GUIDs to download next. Optionally
     filter based on an exact match of title string.
  """

  db = database.MythNetTvDatabase()
  
  remaining = int(count)
  if FLAGS.oldestfirst and FLAGS.newestfirst:
    out.write('Cannot download both oldest and newest first!\n')
    return []

  old_target = remaining / 2
  if FLAGS.oldestfirst:
    old_target = remaining
  elif FLAGS.newestfirst:
    old_target = 0

  guids = []

  if filter == None:
    title = 'is not NULL'
  else:
    title = '= "%s"' % filter
    out.write('Download constrained to "%s"\n' % filter)

  if subtitle == None:
    subtitle_filter = '.*'
  else:
    subtitle_filter = subtitle

  subscription_titles = []
  inactive_titles = []
  for row in db.GetRows('select * from mythnettv_subscriptions'):
    if not row['inactive']:
      subscription_titles.append(row['title'])
      if FLAGS.verbose:
        out.write('  %s is active\n' % row['title'])

    else:
      inactive_titles.append(row['title'])
      if FLAGS.verbose:
        out.write('  %s is inactive\n' % row['title'])

  for row in db.GetRows('select * from mythnettv_programs where '
                        'download_finished is NULL and title %s '
                        'and subtitle rlike "%s" and inactive is null '
                        'order by date asc limit %d;'
                        %(title, subtitle_filter, old_target)):
    # We should only download shows we are _currently_ subscribed to
    if not row['title'] in inactive_titles:
      guids.append(row['guid'])
      remaining -= 1
      if FLAGS.verbose:
        print '  Adding %s : %s to the list of downloads' %(row['title'],
                                                            row['subtitle'])

  if FLAGS.verbose:
    out.write('\n')

  for row in db.GetRows('select * from mythnettv_programs where '
                        'download_finished is NULL and title %s '
                        'and subtitle rlike "%s" '
                        'and inactive is null '
                        'and guid not in ("%s") '
                        'order by date desc limit %d;'
                        %(title, subtitle_filter,
                          '", "'.join(guids), remaining)):
    # We should only download shows we are _currently_ subscribed to
    if not row['title'] in inactive_titles:
      guids.append(row['guid'])
      if FLAGS.verbose:
        print '  Adding %s : %s to the list of downloads' %(row['title'],
                                                            row['subtitle'])

  if FLAGS.verbose:
    out.write('\n')

  out.write('%d matches\n' % len(guids))
  return guids


def DownloadAndImport(db, guid, out=sys.stdout):
  """DownloadAndImport -- perform all the steps to download and import a
     given guid.
  """

  prog = program.MythNetTvProgram(db)
  try:
    out.write('\nDownloading %s\n' % guid)
    prog.Load(guid)
    if prog.Download(db.GetSettingWithDefault('datadir', FLAGS.datadir),
                     out=out) == True:
      out.write('Download OK\n')
      prog.Import(out=out)
      return True

  except proxyhandler.DownloadBudgetExceededException, e:
    out.write('Download Error (budget exceeded): %s\n' % e)
    if 'attempts' in prog.persistant and prog.persistant['attempts']:
      prog.persistant['attempts'] -= 1
      prog.Store()

  except Exception, e:
    out.write('Download Error: %s\n' % e)
    out.write(traceback.format_exc())

  return False


def Subscribe(url, title, inetref, chanid):
  """Subscribe -- subscribe to a new RSS or ATOM feed"""
  
  db = database.MythNetTvDatabase()
  db.WriteOneRow('mythnettv_subscriptions', 'url', {'url':url,
                                                    'title':title,
                                                    'inactive':None,
                                                    'inetref':inetref,
                                                    'chanid':chanid})
  
def Update(out, title=None):
  """Update -- download updates for all feeds"""

  db = database.MythNetTvDatabase()
  title_sql = ''
  if title:
    title_sql = 'and title = "%s"' % title

  for row in db.GetRows('select * from mythnettv_subscriptions '
                        'where inactive is null %s'
                        % title_sql):
    if FLAGS.verbose:
      out.write('Updating: %s\n' % row['url'])

    try:
      proxy = proxyhandler.HttpHandler(db)
      xmlfile = proxy.Open(row['url'], out=out)
      syndication.Sync(db, xmlfile, row['title'], out=out)

    except Exception, e:
      out.write('Failed to update %s: %s\n' %(row['url'], e))
