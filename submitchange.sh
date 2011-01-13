#!/bin/bash -e

# $1: Submit message, as well as changelog entry
# $2: If 'notest', then don't run unit tests

if [ "%$SUBMIT_USER%" == "%%" ]
then
  user=$USER
else
  user=$SUBMIT_USER
fi

if [ "%$2%" == "%notest%" ]
then
  echo "Skipping unit tests"
else
  time ./runtests.sh
fi

svn --username $user commit --message "Mikal: $1" | tee submitchange.out
revision=`grep "Committed revision" submitchange.out | sed -e 's/.*revision //' -e 's/\.$//'`

echo "  - r$revision: $1" > ChangeLog.new
cat ChangeLog >> ChangeLog.new
mv ChangeLog.new ChangeLog

svn --username $user commit --message "Submit script: update ChangeLog"
head ChangeLog
