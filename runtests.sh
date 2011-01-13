#!/bin/bash -e

for item in *_test.py
do
  echo
  echo "Running $item"
  echo

  ./$item
done

cd plugins
./runtests.sh
cd ..

echo "All tests passed"
