#!/bin/bash

# $1 is something like "release 6"

if [ `grep -ic "$1" mythnettv` -lt 1 ]
then
  echo "You need to update the release number in the mythnettv source file"
  exit 1
fi

svn --force delete *~ *.pyc
mkdir -p mythnettv-$1

for item in ChangeLog *.py mythnettv README* DEVELOPERS TODO COPYING TESTS-MISSING *.1 runtests.sh
do
  cp $item mythnettv-$1/
done

tar cvzf mythnettv-$1.tgz mythnettv-$1
mv mythnettv-$1.tgz ../releases/mythnettv-$1.tgz

cd ../releases
svn add mythnettv-$1.tgz
svn commit --message "Release script: Preparing $1"

cd ..
svn copy trunk branches/mythnettv-$1
svn commit --message "Release script: Branching $1 for release"
