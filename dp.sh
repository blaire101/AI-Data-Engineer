#!/bin/bash

echo "start deploy my ..."

git pull && git status && git add * && git status && git commit -m "add or modify article" && git push

echo "successful commit."
