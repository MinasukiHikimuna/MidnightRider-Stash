#!/bin/bash

# This script has been specially modified to exclude the branch, in order to maintain backwards compatibility
# feederbox826//2024-04-06

# builds a repository of scrapers
# outputs to _site with the following structure:
# index.yml
# <scraper_id>.zip
# Each zip file contains the scraper.yml file and any other files in the same directory

outdir="$1"
if [ -z "$outdir" ]; then
    outdir="_site"
fi

rm -rf "$outdir"
mkdir -p "$outdir"

buildPlugin() 
{
    f=$1

    if grep -q "^#pkgignore" "$f"; then
        return
    fi
    
    # get the scraper id from the directory
    dir=$(dirname "$f")
    plugin_id=$(basename "$f" .yml)

    echo "Processing $plugin_id"

    # create a directory for the version
    version=$(git log -n 1 --pretty=format:%h -- "$dir"/*)
    updated=$(TZ=UTC0 git log -n 1 --date="format-local:%F %T" -- "$dir"/*)
    
    # create the zip file
    # copy other files
    zipfile=$(realpath "$outdir/$plugin_id.zip")
    
    pushd "$dir" > /dev/null
    
    # Check for .manifestignore file
    if [ -f ".manifestignore" ]; then
        # Use .manifestignore to exclude files
        zip -r "$zipfile" . -x@.manifestignore > /dev/null
    else
        # If .manifestignore doesn't exist, include all files
        zip -r "$zipfile" . > /dev/null
    fi
    
    popd > /dev/null

    name=$(grep "^name:" "$f" | head -n 1 | cut -d' ' -f2- | sed -e 's/\r//' -e 's/^"\(.*\)"$/\1/')
    description=$(grep "^description:" "$f" | head -n 1 | cut -d' ' -f2- | sed -e 's/\r//' -e 's/^"\(.*\)"$/\1/')
    ymlVersion=$(grep "^version:" "$f" | head -n 1 | cut -d' ' -f2- | sed -e 's/\r//' -e 's/^"\(.*\)"$/\1/')
    version="$ymlVersion-$version"
    # set IFS
    IFS=$'\n' dep=$(grep "^# requires:" "$f" | cut -c 12- | sed -e 's/\r//')

    # write to spec index
    echo "- id: $plugin_id
  name: $name
  metadata:
    description: $description
  version: $version
  date: $updated
  path: $plugin_id.zip
  sha256: $(sha256sum "$zipfile" | cut -d' ' -f1)" >> "$outdir"/index.yml

    # handle dependencies
    if [ ! -z "$dep" ]; then
        echo "  requires:" >> "$outdir"/index.yml
        for d in ${dep//,/ }; do
            echo "    - $d" >> "$outdir"/index.yml
        done
    fi

    echo "" >> "$outdir"/index.yml
}

find ./plugins -mindepth 1 -name *.yml | while read file; do
    buildPlugin "$file"
done
find ./themes -mindepth 1 -name *.yml | while read file; do
    buildPlugin "$file"
done